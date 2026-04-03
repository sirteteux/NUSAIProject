"""
FAQ Agent - HR Knowledge Base Assistant
Upgraded to true AI agent with OpenAI tool calling.

Agentic loop: model decides which tools to call, sees results,
calls more tools if needed, then generates a grounded final answer.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import sys, os
from dotenv import load_dotenv
import logging
from openai import OpenAI
import uvicorn
import traceback
import uuid
import json
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from react_engine import run_react_loop, build_react_system_prompt

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="FAQ Agent", description="HR Knowledge Base ReAct AI Agent", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

MONGODB_URL = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
DB_NAME     = os.getenv("DB_NAME", "faq_db")
mongo_client = None
db = None

# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────
class QuestionRequest(BaseModel):
    question: str
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None

class QuestionResponse(BaseModel):
    answer: str
    question: str
    confidence: float = 0.95
    conversation_id: str
    tools_used: List[str] = []

# ─────────────────────────────────────────────
# Guardrails
# ─────────────────────────────────────────────
SENSITIVE_KEYWORDS = ['salary', 'fire', 'terminate', 'lawsuit', 'harassment', 'discrimination']
CONTEXT_MARKER     = "[Prior conversation context:"

_FAQ_BASE_PROMPT = """You are ResourcefulAI's HR Knowledge Assistant — a professional virtual assistant for employees.

You have access to tools that let you look up real company data. Always use tools to retrieve
accurate information before answering. Do not answer from memory alone when a tool can verify it.

## CAPABILITIES
- Company policies and procedures
- Working hours, remote work policies
- Leave entitlements and benefits
- Office locations and facilities
- Onboarding, training, career development

## COMPANY INFORMATION
Company: ResourcefulAI | Office: 123 Business Street, Singapore 018956
Hours: Mon-Fri 9AM-6PM SGT | HR: hr@company.com | +65 6123 4567
Dress: Business casual (smart casual Fridays)

## GUARDRAILS — NEVER DO THESE
DO NOT provide medical, legal, or financial advice
DO NOT discuss other employees' personal information or salaries
DO NOT handle harassment/discrimination complaints (escalate to HR)
DO NOT make commitments on behalf of management"""

# Wrap with ReAct instruction — forces explicit Thought/Action/Observation/Final Answer cycle
SYSTEM_PROMPT = build_react_system_prompt(_FAQ_BASE_PROMPT)

# ─────────────────────────────────────────────
# Tool Definitions
# ─────────────────────────────────────────────
FAQ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_popular_questions",
            "description": "Retrieve the most frequently asked HR questions, sorted by view count. Use this to understand what employees commonly ask about.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_faq_categories",
            "description": "Retrieve all available FAQ categories (e.g. policies, leave, benefits, office). Use this to understand the scope of HR knowledge available.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_question_logs",
            "description": "Search historical question logs to find how similar questions were handled in the past. Useful for consistency.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Keyword to search for in past questions"}
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_hr",
            "description": "Escalate a sensitive question to HR and log it. Use for harassment, discrimination, salary disputes, or legal matters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why this is being escalated"},
                    "user_id": {"type": "string", "description": "User ID if available"}
                },
                "required": ["reason"]
            }
        }
    }
]

# ─────────────────────────────────────────────
# Tool Executor
# ─────────────────────────────────────────────
async def execute_tool(tool_name: str, tool_args: dict, user_id: str = None) -> str:
    """Execute a tool call and return result as string."""
    try:
        if tool_name == "get_popular_questions":
            cursor = db.popular_questions.find({}, {"_id": 0, "question": 1}).sort("views", -1).limit(10)
            docs = await cursor.to_list(length=10)
            return json.dumps([d["question"] for d in docs])

        elif tool_name == "get_faq_categories":
            cursor = db.categories.find({}, {"_id": 0})
            cats = await cursor.to_list(length=20)
            return json.dumps(cats)

        elif tool_name == "search_question_logs":
            keyword = tool_args.get("keyword", "")
            cursor = db.question_logs.find(
                {"question": {"$regex": keyword, "$options": "i"}},
                {"_id": 0, "question": 1, "timestamp": 1}
            ).sort("timestamp", -1).limit(5)
            logs = await cursor.to_list(length=5)
            return json.dumps(logs if logs else [{"message": "No similar questions found"}])

        elif tool_name == "escalate_to_hr":
            reason  = tool_args.get("reason", "unspecified")
            uid     = tool_args.get("user_id", user_id or "anonymous")
            await db.escalations.insert_one({
                "user_id": uid, "reason": reason,
                "timestamp": datetime.now().isoformat()
            })
            return json.dumps({"status": "escalated", "message": "HR has been notified", "contact": "hr@company.com"})

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        logger.error(f"❌ Tool {tool_name} failed: {str(e)}")
        return json.dumps({"error": str(e)})

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
async def log_message(conv_id, role, message, user_id=None, flagged=False):
    if db is None:
        return
    try:
        await db.chat_history.insert_one({
            "conversation_id": conv_id, "service": "faq",
            "user_id": user_id, "role": role, "message": message,
            "flagged": flagged, "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.warning(f"⚠️ log_message failed: {str(e)}")

async def get_conversation_history(conv_id, limit=10):
    if db is None:
        return []
    try:
        cursor = db.chat_history.find({"conversation_id": conv_id}, sort=[("timestamp", 1)]).limit(limit)
        return await cursor.to_list(length=limit)
    except Exception as e:
        logger.warning(f"⚠️ get_history failed: {str(e)}")
        return []

def serialize_doc(doc):
    if doc and "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc

# ─────────────────────────────────────────────
# Seed Data
# ─────────────────────────────────────────────
SEED_POPULAR = [
    {"question": "What are the company's working hours?",    "category": "policies",  "views": 120},
    {"question": "How do I request vacation leave?",         "category": "leave",     "views": 98},
    {"question": "What is the dress code policy?",           "category": "policies",  "views": 87},
    {"question": "How many sick days do I get?",             "category": "leave",     "views": 76},
    {"question": "What benefits are available?",             "category": "benefits",  "views": 65},
    {"question": "Where is the office located?",             "category": "office",    "views": 54},
    {"question": "How do I contact HR?",                     "category": "general",   "views": 43},
    {"question": "What is the remote work policy?",          "category": "policies",  "views": 38},
]
SEED_CATEGORIES = [
    {"id": "policies",  "name": "Company Policies",       "icon": "policy"},
    {"id": "benefits",  "name": "Benefits & Perks",        "icon": "card_giftcard"},
    {"id": "leave",     "name": "Leave Policies",          "icon": "event"},
    {"id": "office",    "name": "Office & Facilities",     "icon": "business"},
    {"id": "training",  "name": "Training & Development",  "icon": "school"},
    {"id": "general",   "name": "General Inquiries",       "icon": "help"},
]

# ─────────────────────────────────────────────
# Startup / Shutdown
# ─────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    global mongo_client, db
    logger.info("🚀 FAQ Agent v2 Starting (with tool calling)")
    try:
        mongo_client = AsyncIOMotorClient(MONGODB_URL)
        db = mongo_client[DB_NAME]
        await mongo_client.admin.command("ping")
        logger.info("✅ MongoDB connected")
        if await db.popular_questions.count_documents({}) == 0:
            await db.popular_questions.insert_many(SEED_POPULAR)
        if await db.categories.count_documents({}) == 0:
            await db.categories.insert_many(SEED_CATEGORIES)
    except Exception as e:
        logger.error(f"❌ MongoDB failed: {str(e)}")

@app.on_event("shutdown")
async def shutdown_event():
    if mongo_client:
        mongo_client.close()

# ─────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────
@app.get("/health")
async def health_check():
    mongo_status = "disconnected"
    try:
        if mongo_client:
            await mongo_client.admin.command("ping")
            mongo_status = "connected"
    except Exception:
        mongo_status = "error"
    return {"status": "healthy", "service": "faq-agent", "version": "2.0.0",
            "openai_status": "configured" if OPENAI_API_KEY else "missing",
            "mongodb_status": mongo_status, "mode": "agentic-tool-calling"}

# ─────────────────────────────────────────────
# AI Ask Endpoint — Agentic Loop
# ─────────────────────────────────────────────
@app.post("/api/faq/ask", response_model=QuestionResponse)
async def ask_question(request: QuestionRequest):
    try:
        logger.info(f"📥 FAQ question: {request.question}")
        if not OPENAI_API_KEY or not client:
            raise HTTPException(status_code=500, detail="OpenAI not configured")

        conv_id = request.conversation_id or str(uuid.uuid4())

        # ── Strip coordinator context before guardrail check ──────────────────
        original_question = request.question
        if CONTEXT_MARKER in request.question:
            original_question = request.question.split(CONTEXT_MARKER)[0].strip()

        # ── Guardrail check (original question only) ──────────────────────────
        if any(kw in original_question.lower() for kw in SENSITIVE_KEYWORDS):
            logger.warning(f"🚨 Sensitive FAQ query: {original_question}")
            escalation_answer = (
                "This seems like a sensitive matter that requires direct HR support. "
                "Please contact hr@company.com or call +65 6123 4567."
            )
            await log_message(conv_id, "user",      request.question,  request.user_id, flagged=True)
            await log_message(conv_id, "assistant", escalation_answer, request.user_id, flagged=True)
            return QuestionResponse(answer=escalation_answer, question=request.question,
                                    confidence=1.0, conversation_id=conv_id, tools_used=["escalate_to_hr"])

        # ── Build messages with history ───────────────────────────────────────
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        history  = await get_conversation_history(conv_id, limit=10)
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["message"]})
        messages.append({"role": "user", "content": request.question})

        # ── Genuine ReAct loop ────────────────────────────────────────────────
        # Thought → Action → Observation → re-evaluate → Final Answer
        result = await run_react_loop(
            openai_client=client,
            messages=messages,
            tools=FAQ_TOOLS,
            tool_executor=lambda name, args: execute_tool(name, args, request.user_id),
            service_name="FAQ",
            max_iterations=8,
        )

        answer     = result["answer"]
        tools_used = result["tools_used"]

        logger.info(
            f"✅ FAQ ReAct complete — {result['iterations']} iteration(s), "
            f"tools: {tools_used}, thoughts: {len(result['thoughts'])}"
        )

        await log_message(conv_id, "user",      request.question, request.user_id)
        await log_message(conv_id, "assistant", answer,           request.user_id)

        return QuestionResponse(
            answer=answer, question=request.question,
            confidence=0.95, conversation_id=conv_id, tools_used=tools_used
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ FAQ error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────
# Supporting Endpoints
# ─────────────────────────────────────────────
@app.get("/api/faq/categories")
async def get_categories():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor = db.categories.find({}, {"_id": 0})
    return {"categories": await cursor.to_list(length=50)}

@app.get("/api/faq/popular")
async def get_popular_questions():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor = db.popular_questions.find({}, {"_id": 0, "question": 1}).sort("views", -1).limit(10)
    docs = await cursor.to_list(length=10)
    return {"questions": [d["question"] for d in docs]}

@app.get("/api/faq/history/chat")
async def get_chat_history(user_id: str, limit: int = 50):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor = db.chat_history.find(
        {"user_id": user_id, "service": "faq"}, sort=[("timestamp", -1)]
    ).limit(limit)
    history = await cursor.to_list(length=limit)
    return {"user_id": user_id, "history": [serialize_doc(h) for h in history]}

@app.get("/api/faq/history/chat/{conversation_id}")
async def get_conversation(conversation_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor = db.chat_history.find({"conversation_id": conversation_id}, sort=[("timestamp", 1)])
    messages = await cursor.to_list(length=200)
    return {"conversation_id": conversation_id, "messages": [serialize_doc(m) for m in messages]}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8002)))