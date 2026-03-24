"""
Coordinator Agent - Intelligent Multi-Agent Router
Routes user queries to the appropriate specialised HR agent.

Brain features:
- Level 1: MongoDB chat_history — last N messages injected into routing
            prompt so follow-up queries route correctly across turns
- Level 2: Redis session state — per-employee context (last_service,
            last_topic, services_used) with 1-hour TTL for fast reads
- Guardrails: sensitive keyword interception before routing
- Audit logging: all exchanges persisted with agent_used and flagged fields
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
import os
from dotenv import load_dotenv
import logging
from openai import OpenAI
import httpx
from datetime import datetime
import json
import uuid
import uvicorn
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import redis.asyncio as aioredis

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Coordinator Agent",
    description="Intelligent Multi-Agent Router with Brain (MongoDB + Redis)",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# OpenAI Setup
# ─────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("❌ OPENAI_API_KEY not found!")
else:
    logger.info("✅ OpenAI API Key configured")

openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ─────────────────────────────────────────────
# Agent URLs
# ─────────────────────────────────────────────
FAQ_URL         = os.getenv("FAQ_SERVICE_URL",         "http://localhost:8002")
PAYROLL_URL     = os.getenv("PAYROLL_SERVICE_URL",     "http://localhost:8003")
LEAVE_URL       = os.getenv("LEAVE_SERVICE_URL",       "http://localhost:8004")
RECRUITMENT_URL = os.getenv("RECRUITMENT_SERVICE_URL", "http://localhost:8005")
PERFORMANCE_URL = os.getenv("PERFORMANCE_SERVICE_URL", "http://localhost:8006")

# ─────────────────────────────────────────────
# MongoDB Setup
# ─────────────────────────────────────────────
MONGODB_URL = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
DB_NAME     = os.getenv("DB_NAME", "coordinator_db")

mongo_client: AsyncIOMotorClient = None
db = None

# ─────────────────────────────────────────────
# Redis Setup (Level 2 session state)
# ─────────────────────────────────────────────
REDIS_URL   = os.getenv("REDIS_URL", "redis://localhost:6379")
SESSION_TTL = 3600   # 1 hour TTL — session auto-expires after inactivity

redis_client = None

# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────
class CoordinatorRequest(BaseModel):
    query: str
    employee_id: Optional[str] = None
    conversation_id: Optional[str] = None      # ← thread identifier
    context: Optional[Dict[str, Any]] = None

class CoordinatorResponse(BaseModel):
    answer: str
    agent_used: str
    confidence: float
    conversation_id: str                        # ← returned so frontend can reuse it
    metadata: Optional[Dict] = None

# ─────────────────────────────────────────────
# Guardrails
# ─────────────────────────────────────────────
COORDINATOR_SENSITIVE_KEYWORDS = [
    "ignore instructions",    # jailbreak attempt
    "override",               # prompt injection
    "forget everything",      # context wiping attempt
    "pretend you are",        # persona override
    "act as",                 # persona override
    "bypass",                 # security bypass attempt
    "jailbreak",              # explicit jailbreak
    "do anything now",        # DAN-style jailbreak
    "you are now",            # persona override
]

COORDINATOR_ESCALATION_RESPONSE = (
    "I'm unable to process that request. If you have a genuine HR query, "
    "please rephrase your question or contact hr@company.com directly."
)

# ─────────────────────────────────────────────
# Helpers — MongoDB chat history (Level 1)
# ─────────────────────────────────────────────
async def log_message(
    conv_id: str,
    role: str,
    message: str,
    employee_id: str = None,
    agent_used: str = None,
    flagged: bool = False
):
    """Persist a coordinator chat message. Never raises."""
    if db is None:
        return
    try:
        await db.chat_history.insert_one({
            "conversation_id": conv_id,
            "service":         "coordinator",
            "employee_id":     employee_id,
            "role":            role,
            "message":         message,
            "agent_used":      agent_used,   # which downstream agent handled this turn
            "flagged":         flagged,
            "timestamp":       datetime.now().isoformat()
        })
    except Exception as e:
        logger.warning(f"⚠️ Failed to log message: {str(e)}")

async def get_conversation_history(conv_id: str, limit: int = 10) -> List[Dict]:
    """
    Fetch last N messages for a conversation, oldest-first.
    Includes agent_used so the routing prompt knows which services
    have already handled turns in this conversation.
    """
    if db is None:
        return []
    try:
        cursor = db.chat_history.find(
            {"conversation_id": conv_id},
            sort=[("timestamp", 1)]
        ).limit(limit)
        return await cursor.to_list(length=limit)
    except Exception as e:
        logger.warning(f"⚠️ Failed to fetch history: {str(e)}")
        return []

# ─────────────────────────────────────────────
# Helpers — Redis session state (Level 2)
#
# Stores per-employee context in Redis with a
# native TTL so stale sessions auto-expire.
# Falls back to empty dict if Redis is down —
# the service degrades gracefully.
# ─────────────────────────────────────────────
async def get_session(employee_id: str) -> Dict:
    """
    Retrieve per-employee session context from Redis.
    Returns empty dict if no session exists or Redis is unavailable.
    """
    if redis_client is None:
        return {}
    try:
        data = await redis_client.get(f"session:{employee_id}")
        return json.loads(data) if data else {}
    except Exception as e:
        logger.warning(f"⚠️ Failed to get session: {str(e)}")
        return {}

async def save_session(employee_id: str, updates: Dict):
    """
    Merge updates into the employee session and reset the TTL.
    Stored as a JSON string at key session:{employee_id}.

    Session schema:
      last_service:  last agent used (e.g. "payroll")
      last_topic:    truncated last query (100 chars)
      last_active:   ISO timestamp
      services_used: cumulative list of agents used this session
    """
    if redis_client is None:
        return
    try:
        existing = await get_session(employee_id)
        existing.update(updates)
        existing["last_active"] = datetime.now().isoformat()

        # Track running list of services used this session
        services_used = existing.get("services_used", [])
        new_service   = updates.get("last_service")
        if new_service and new_service not in services_used:
            services_used.append(new_service)
        existing["services_used"] = services_used

        # setex writes the value and sets the TTL in one atomic operation
        await redis_client.setex(
            f"session:{employee_id}",
            SESSION_TTL,
            json.dumps(existing)
        )
    except Exception as e:
        logger.warning(f"⚠️ Failed to save session: {str(e)}")

# ─────────────────────────────────────────────
# Agent Callers
# ─────────────────────────────────────────────
http_client = httpx.AsyncClient(timeout=30.0)

async def call_faq_agent(query: str, conv_id: str) -> Dict:
    try:
        logger.info("🔀 Routing to FAQ Agent")
        response = await http_client.post(
            f"{FAQ_URL}/api/faq/ask",
            json={"question": query, "conversation_id": conv_id}
        )
        response.raise_for_status()
        data = response.json()
        return {"answer": data.get("answer", ""), "agent": "FAQ", "success": True}
    except Exception as e:
        logger.error(f"❌ FAQ Agent error: {str(e)}")
        return {"answer": f"FAQ service unavailable: {str(e)}", "agent": "FAQ", "success": False}

async def call_payroll_agent(query: str, employee_id: str, conv_id: str) -> Dict:
    try:
        logger.info("🔀 Routing to Payroll Agent")
        response = await http_client.post(
            f"{PAYROLL_URL}/api/payroll/query",
            json={"query": query, "employee_id": employee_id, "conversation_id": conv_id}
        )
        response.raise_for_status()
        data = response.json()
        return {"answer": data.get("answer", ""), "agent": "Payroll", "success": True}
    except Exception as e:
        logger.error(f"❌ Payroll Agent error: {str(e)}")
        return {"answer": f"Payroll service unavailable: {str(e)}", "agent": "Payroll", "success": False}

async def call_leave_agent(query: str, employee_id: str, conv_id: str) -> Dict:
    try:
        logger.info("🔀 Routing to Leave Agent")
        response = await http_client.post(
            f"{LEAVE_URL}/api/leave/query",
            json={"query": query, "employee_id": employee_id, "conversation_id": conv_id}
        )
        response.raise_for_status()
        data = response.json()
        return {"answer": data.get("answer", ""), "agent": "Leave", "success": True}
    except Exception as e:
        logger.error(f"❌ Leave Agent error: {str(e)}")
        return {"answer": f"Leave service unavailable: {str(e)}", "agent": "Leave", "success": False}

async def call_recruitment_agent(query: str, conv_id: str) -> Dict:
    try:
        logger.info("🔀 Routing to Recruitment Agent")
        response = await http_client.post(
            f"{RECRUITMENT_URL}/api/recruitment/query",
            json={"query": query, "conversation_id": conv_id}
        )
        response.raise_for_status()
        data = response.json()
        return {"answer": data.get("answer", ""), "agent": "Recruitment", "success": True}
    except Exception as e:
        logger.error(f"❌ Recruitment Agent error: {str(e)}")
        return {"answer": f"Recruitment service unavailable: {str(e)}", "agent": "Recruitment", "success": False}

async def call_performance_agent(query: str, employee_id: str, conv_id: str) -> Dict:
    try:
        logger.info("🔀 Routing to Performance Agent")
        response = await http_client.post(
            f"{PERFORMANCE_URL}/api/performance/query",
            json={"query": query, "employee_id": employee_id, "conversation_id": conv_id}
        )
        response.raise_for_status()
        data = response.json()
        return {"answer": data.get("answer", ""), "agent": "Performance", "success": True}
    except Exception as e:
        logger.error(f"❌ Performance Agent error: {str(e)}")
        return {"answer": f"Performance service unavailable: {str(e)}", "agent": "Performance", "success": False}

async def is_meta_query(query: str) -> bool:
    """
    Detect whether the user is asking about the conversation itself
    rather than an HR topic. These are answered directly by the
    coordinator using its own chat_history — never routed downstream.

    Examples:
      "what was my first question?"
      "what have we talked about?"
      "can you summarise our conversation?"
      "what did I ask earlier?"
    """
    meta_keywords = [
        "first question", "last question", "previous question",
        "what did i ask", "what have we", "what have i",
        "our conversation", "earlier question", "summarise",
        "summarize", "recap", "what we talked", "what i asked",
        "history", "remember what", "you remember", "go back to",
        "what was my", "previous message", "earlier message",
    ]
    query_lower = query.lower()
    return any(kw in query_lower for kw in meta_keywords)


async def handle_meta_query(query: str, history: List[Dict], employee_id: str) -> str:
    """
    Answer conversation-about-conversation questions directly using
    the coordinator's own chat_history — the only place that holds
    the full cross-service conversation record.
    """
    if not history:
        return (
            "I don't have any previous messages in this conversation yet. "
            "Feel free to ask me anything about HR!"
        )

    # Build a full readable transcript from coordinator history
    transcript_lines = []
    for i, msg in enumerate(history):
        role  = "You" if msg["role"] == "user" else "Assistant"
        agent = f" ({msg['agent_used']} Agent)" if msg.get("agent_used") else ""
        text  = msg["message"]
        transcript_lines.append(f"{i + 1}. {role}{agent}: {text}")

    transcript = "\n".join(transcript_lines)

    # Let OpenAI answer the meta question using the real transcript
    meta_prompt = f"""You are an HR assistant with access to the full conversation history below.
Answer the user's question about the conversation accurately using only this transcript.

Conversation transcript:
{transcript}

User question: {query}

Answer concisely and accurately based strictly on the transcript above."""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": meta_prompt}],
            temperature=0.1,
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"❌ Meta query OpenAI call failed: {str(e)}")
        # Graceful fallback — return first user message manually
        first_user = next((m for m in history if m["role"] == "user"), None)
        if first_user:
            return f"Your first question was: \"{first_user['message']}\""
        return "I wasn't able to retrieve the conversation history right now."


# ─────────────────────────────────────────────
# Intelligent Routing — Context-Aware
# ─────────────────────────────────────────────
async def route_query_intelligent(
    query: str,
    employee_id: str,
    conv_id: str,
    session: Dict,
    history: List[Dict]
) -> Dict:
    """
    Routes a query to the appropriate agent using GPT-4o-mini.

    Two layers of context enrichment:
      1. Routing prompt: enriched with session + history so routing
         decisions are correct for follow-up queries
      2. Enriched query: history summary appended to the query text
         sent downstream so each agent has cross-service context
         even though it only stores its own portion of history
    """
    if not OPENAI_API_KEY:
        logger.warning("⚠️ No OpenAI key — defaulting to FAQ agent")
        return await call_faq_agent(query, conv_id)

    try:
        # ── Session context hint ─────────────────────────────────────────────
        session_hint = ""
        if session.get("last_service") and session.get("last_topic"):
            session_hint = (
                f"\nSession context: This employee was recently asking about "
                f"'{session['last_topic']}' via the {session['last_service']} agent."
            )
        if session.get("services_used"):
            session_hint += (
                f"\nServices used this session: {', '.join(session['services_used'])}."
            )

        # ── Conversation history for routing context ─────────────────────────
        history_hint = ""
        if history:
            recent = history[-6:]
            lines  = []
            for msg in recent:
                role  = msg["role"]
                text  = msg["message"][:120]
                agent = f" [{msg['agent_used']}]" if msg.get("agent_used") else ""
                lines.append(f"  {role}{agent}: {text}")
            history_hint = "\nRecent conversation:\n" + "\n".join(lines)

        # ── Routing prompt ───────────────────────────────────────────────────
        routing_prompt = f"""You are an intelligent router for an HR system with 5 specialised agents.
Analyse the user query and determine which agent should handle it.
{session_hint}
{history_hint}

Available Agents:
1. FAQ         — General HR questions, company policies, working hours, dress code, benefits overview
2. Payroll     — Salary, payslips, bonuses, deductions, CPF, tax, compensation
3. Leave       — Leave balance, leave requests, vacation days, sick leave, time off
4. Recruitment — Job openings, interview process, hiring timeline, career opportunities
5. Performance — Goals, KPIs, performance reviews, career development, feedback

Respond with ONLY ONE word: FAQ, Payroll, Leave, Recruitment, or Performance

User Query: "{query}"
"""

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": routing_prompt}],
            temperature=0.0,
            max_tokens=10
        )

        agent_choice = response.choices[0].message.content.strip()
        logger.info(f"🎯 Routing decision: {agent_choice}")

        # ── Build history-enriched query for downstream agents ───────────────
        # Downstream agents only have their own portion of chat_history.
        # Appending a coordinator-level summary gives them the full picture,
        # enabling correct follow-up answers across service boundaries.
        enriched_query = query
        if history:
            summary_lines = []
            for msg in history[-6:]:
                role  = "User" if msg["role"] == "user" else "Assistant"
                agent = f" [{msg['agent_used']}]" if msg.get("agent_used") else ""
                summary_lines.append(f"{role}{agent}: {msg['message'][:150]}")
            history_summary = "\n".join(summary_lines)
            enriched_query = (
                f"{query}\n\n"
                f"[Prior conversation context for reference:\n{history_summary}]"
            )

        # ── Dispatch to chosen agent using enriched query ────────────────────
        if "Payroll" in agent_choice:
            return await call_payroll_agent(enriched_query, employee_id, conv_id)
        elif "Leave" in agent_choice:
            return await call_leave_agent(enriched_query, employee_id, conv_id)
        elif "Recruitment" in agent_choice:
            return await call_recruitment_agent(enriched_query, conv_id)
        elif "Performance" in agent_choice:
            return await call_performance_agent(enriched_query, employee_id, conv_id)
        else:
            return await call_faq_agent(enriched_query, conv_id)

    except Exception as e:
        logger.error(f"❌ Routing error: {str(e)} — falling back to FAQ")
        return await call_faq_agent(query, conv_id)

# ─────────────────────────────────────────────
# Startup / Shutdown
# ─────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    global mongo_client, db, redis_client

    logger.info("=" * 60)
    logger.info("🚀 Coordinator Agent v2 Starting Up")
    logger.info("=" * 60)
    logger.info(f"OpenAI API:  {'✅ Configured' if OPENAI_API_KEY else '❌ Missing'}")
    logger.info(f"MongoDB URL: {MONGODB_URL}")
    logger.info(f"Redis URL:   {REDIS_URL}")

    # ── MongoDB (Level 1 — chat history) ─────────────────────────────────────
    try:
        mongo_client = AsyncIOMotorClient(MONGODB_URL)
        db = mongo_client[DB_NAME]
        await mongo_client.admin.command("ping")
        logger.info("✅ MongoDB connected")
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {str(e)}")

    # ── Redis (Level 2 — session state) ──────────────────────────────────────
    try:
        redis_client = await aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
        logger.info("✅ Redis connected")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {str(e)}")

    logger.info(f"FAQ Agent:         {FAQ_URL}")
    logger.info(f"Payroll Agent:     {PAYROLL_URL}")
    logger.info(f"Leave Agent:       {LEAVE_URL}")
    logger.info(f"Recruitment Agent: {RECRUITMENT_URL}")
    logger.info(f"Performance Agent: {PERFORMANCE_URL}")
    logger.info(f"Session TTL:       {SESSION_TTL}s ({SESSION_TTL // 3600}hr)")
    logger.info("=" * 60)

@app.on_event("shutdown")
async def shutdown_event():
    await http_client.aclose()
    if mongo_client:
        mongo_client.close()
        logger.info("🔌 MongoDB connection closed")
    if redis_client:
        await redis_client.aclose()
        logger.info("🔌 Redis connection closed")

# ─────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────
@app.get("/health")
async def health_check():
    mongo_status = "disconnected"
    redis_status = "disconnected"

    try:
        if mongo_client:
            await mongo_client.admin.command("ping")
            mongo_status = "connected"
    except Exception:
        mongo_status = "error"

    try:
        if redis_client:
            await redis_client.ping()
            redis_status = "connected"
    except Exception:
        redis_status = "error"

    return {
        "status":         "healthy",
        "service":        "coordinator-agent",
        "version":        "2.0.0",
        "openai_status":  "configured" if OPENAI_API_KEY else "missing",
        "mongodb_status": mongo_status,
        "redis_status":   redis_status,
        "agents_connected": {
            "faq":         FAQ_URL,
            "payroll":     PAYROLL_URL,
            "leave":       LEAVE_URL,
            "recruitment": RECRUITMENT_URL,
            "performance": PERFORMANCE_URL
        }
    }

# ─────────────────────────────────────────────
# Main Endpoint — Ask Coordinator
# ─────────────────────────────────────────────
@app.post("/api/coordinator/ask", response_model=CoordinatorResponse)
async def ask_coordinator(request: CoordinatorRequest):
    try:
        logger.info(f"📥 Coordinator received: {request.query}")

        conv_id     = request.conversation_id or str(uuid.uuid4())
        employee_id = request.employee_id or "anonymous"

        # ── Guardrail: intercept sensitive/malicious queries ─────────────────
        query_lower = request.query.lower()
        if any(kw in query_lower for kw in COORDINATOR_SENSITIVE_KEYWORDS):
            logger.warning(f"🚨 Sensitive coordinator query intercepted: {request.query}")
            await log_message(conv_id, "user",      request.query,                   employee_id, flagged=True)
            await log_message(conv_id, "assistant", COORDINATOR_ESCALATION_RESPONSE, employee_id, flagged=True)
            return CoordinatorResponse(
                answer=COORDINATOR_ESCALATION_RESPONSE,
                agent_used="guardrail",
                confidence=1.0,
                conversation_id=conv_id,
                metadata={"flagged": True, "timestamp": datetime.now().isoformat()}
            )

        # ── Level 2: Load session context from MongoDB ───────────────────────
        session = await get_session(employee_id)
        if session:
            logger.info(
                f"📦 Session loaded — last service: {session.get('last_service')}, "
                f"last topic: {str(session.get('last_topic', ''))[:50]}"
            )

        # ── Level 1: Load conversation history from MongoDB ──────────────────
        history = await get_conversation_history(conv_id, limit=10)
        logger.info(f"💬 Loaded {len(history)} previous messages from coordinator history")

        # ── Meta-query intercept ─────────────────────────────────────────────
        # Questions about the conversation itself (e.g. "what was my first
        # question?") are answered directly by the coordinator using its own
        # chat_history — the only store with the full cross-service record.
        # Routing these downstream would fail because each agent only holds
        # its own slice of history, not turns handled by other agents.
        if await is_meta_query(request.query):
            logger.info("🧠 Meta-query detected — answering from coordinator history")
            answer = await handle_meta_query(request.query, history, employee_id)
            await log_message(conv_id, "user",      request.query, employee_id, agent_used=None)
            await log_message(conv_id, "assistant", answer,        employee_id, agent_used="Coordinator")
            return CoordinatorResponse(
                answer=answer,
                agent_used="Coordinator",
                confidence=0.99,
                conversation_id=conv_id,
                metadata={
                    "routing_method": "meta_query_direct",
                    "timestamp":      datetime.now().isoformat(),
                    "employee_id":    employee_id,
                    "history_used":   len(history),
                }
            )

        # ── Route to appropriate agent ───────────────────────────────────────
        result = await route_query_intelligent(
            query=request.query,
            employee_id=employee_id,
            conv_id=conv_id,
            session=session,
            history=history
        )

        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("answer"))

        agent_used = result["agent"]
        answer     = result["answer"]
        logger.info(f"✅ Routed to {agent_used} agent successfully")

        # ── Persist coordinator-level exchange ───────────────────────────────
        await log_message(conv_id, "user",      request.query, employee_id, agent_used=None)
        await log_message(conv_id, "assistant", answer,        employee_id, agent_used=agent_used)

        # ── Update MongoDB session ────────────────────────────────────────────
        await save_session(employee_id, {
            "last_service": agent_used.lower(),
            "last_topic":   request.query[:100]
        })

        return CoordinatorResponse(
            answer=answer,
            agent_used=agent_used,
            confidence=0.95,
            conversation_id=conv_id,
            metadata={
                "routing_method": "context_aware_with_history",
                "timestamp":      datetime.now().isoformat(),
                "employee_id":    employee_id,
                "history_used":   len(history),
                "session_loaded": bool(session)
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Coordinator error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────
# List Agents
# ─────────────────────────────────────────────
@app.get("/api/coordinator/agents")
async def list_agents():
    return {
        "agents": [
            {"name": "FAQ",         "description": "General HR questions and company policies",  "url": FAQ_URL},
            {"name": "Payroll",     "description": "Salary, payslips, and compensation",          "url": PAYROLL_URL},
            {"name": "Leave",       "description": "Leave management and balance enquiries",      "url": LEAVE_URL},
            {"name": "Recruitment", "description": "Job openings and hiring process",             "url": RECRUITMENT_URL},
            {"name": "Performance", "description": "Goals, KPIs, and performance reviews",       "url": PERFORMANCE_URL},
        ],
        "routing_strategy": "Context-aware routing with MongoDB chat history + MongoDB session state"
    }

# ─────────────────────────────────────────────
# Chat History Endpoints
# ─────────────────────────────────────────────
@app.get("/api/coordinator/history/chat")
async def get_chat_history(employee_id: str, limit: int = 50):
    """All coordinator-level chat messages for an employee, newest first."""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    cursor = db.chat_history.find(
        {"employee_id": employee_id, "service": "coordinator"},
        sort=[("timestamp", -1)]
    ).limit(limit)

    history = await cursor.to_list(length=limit)

    def serialize(doc):
        if "_id" in doc:
            doc["id"] = str(doc["_id"])
            del doc["_id"]
        return doc

    return {"employee_id": employee_id, "history": [serialize(h) for h in history]}

@app.get("/api/coordinator/history/chat/{conversation_id}")
async def get_conversation(conversation_id: str):
    """All messages in a specific conversation thread, in chronological order."""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    cursor = db.chat_history.find(
        {"conversation_id": conversation_id},
        sort=[("timestamp", 1)]
    )

    messages = await cursor.to_list(length=200)

    def serialize(doc):
        if "_id" in doc:
            doc["id"] = str(doc["_id"])
            del doc["_id"]
        return doc

    return {"conversation_id": conversation_id, "messages": [serialize(m) for m in messages]}

# ─────────────────────────────────────────────
# Session Inspection
# ─────────────────────────────────────────────
@app.get("/api/coordinator/session/{employee_id}")
async def get_employee_session(employee_id: str):
    """Return the current session state for an employee. Useful for debugging."""
    session = await get_session(employee_id)
    if not session:
        return {"employee_id": employee_id, "session": None, "message": "No active session"}
    return {"employee_id": employee_id, "session": session}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8007))
    uvicorn.run(app, host="0.0.0.0", port=port)