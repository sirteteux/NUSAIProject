"""
Coordinator Agent - Multi-Step Plan-and-Execute Orchestrator
Upgraded to true multi-step: plans a sequence of agent calls,
executes each step, passes results as context to the next,
then synthesises a unified final answer.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
import sys, os, json, uuid, traceback
from dotenv import load_dotenv
import logging
from openai import OpenAI
import httpx
from datetime import datetime
import uvicorn
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import redis.asyncio as aioredis
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from react_engine import build_react_system_prompt, REACT_INSTRUCTION, REEVAL_PROMPT, FINAL_ANSWER_MARKER

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Coordinator Agent",
              description="ReAct Multi-Step Plan-and-Execute Orchestrator", version="3.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client  = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

FAQ_URL         = os.getenv("FAQ_SERVICE_URL",         "http://localhost:8002")
PAYROLL_URL     = os.getenv("PAYROLL_SERVICE_URL",     "http://localhost:8003")
LEAVE_URL       = os.getenv("LEAVE_SERVICE_URL",       "http://localhost:8004")
RECRUITMENT_URL = os.getenv("RECRUITMENT_SERVICE_URL", "http://localhost:8005")
PERFORMANCE_URL = os.getenv("PERFORMANCE_SERVICE_URL", "http://localhost:8006")

MONGODB_URL = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
DB_NAME     = os.getenv("DB_NAME", "coordinator_db")
REDIS_URL   = os.getenv("REDIS_URL", "redis://localhost:6379")
SESSION_TTL = 3600

mongo_client  = None
db            = None
redis_client  = None
http_client   = httpx.AsyncClient(timeout=30.0)

# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────
class CoordinatorRequest(BaseModel):
    query: str
    employee_id: Optional[str] = None
    conversation_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class CoordinatorResponse(BaseModel):
    answer: str
    agent_used: str
    confidence: float
    conversation_id: str
    plan_executed: List[str] = []
    tools_used: List[str] = []
    thoughts: List[str] = []      # ReAct reasoning trace — visible for audit
    metadata: Optional[Dict] = None

# ─────────────────────────────────────────────
# Guardrails
# ─────────────────────────────────────────────
COORDINATOR_SENSITIVE_KEYWORDS = [
    "ignore instructions", "forget everything", "pretend you are",
    "act as", "bypass", "jailbreak", "do anything now", "you are now",
]
COORDINATOR_ESCALATION_RESPONSE = (
    "I'm unable to process that request. If you have a genuine HR query, "
    "please rephrase or contact hr@company.com directly."
)

# ─────────────────────────────────────────────
# Helpers — MongoDB chat history (Level 1)
# ─────────────────────────────────────────────
async def log_message(conv_id, role, message, employee_id=None,
                       agent_used=None, flagged=False):
    if db is None:
        return
    try:
        await db.chat_history.insert_one({
            "conversation_id": conv_id, "service": "coordinator",
            "employee_id": employee_id, "role": role,
            "message": message, "agent_used": agent_used,
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

# ─────────────────────────────────────────────
# Helpers — Redis session state (Level 2)
# ─────────────────────────────────────────────
async def get_session(employee_id):
    if redis_client is None:
        return {}
    try:
        data = await redis_client.get(f"session:{employee_id}")
        return json.loads(data) if data else {}
    except Exception as e:
        logger.warning(f"⚠️ Redis get failed: {str(e)}")
        return {}

async def save_session(employee_id, updates):
    if redis_client is None:
        return
    try:
        existing = await get_session(employee_id)
        existing.update(updates)
        existing["last_active"] = datetime.now().isoformat()
        services_used = existing.get("services_used", [])
        new_service   = updates.get("last_service")
        if new_service and new_service not in services_used:
            services_used.append(new_service)
        existing["services_used"] = services_used
        await redis_client.setex(f"session:{employee_id}", SESSION_TTL, json.dumps(existing))
    except Exception as e:
        logger.warning(f"⚠️ Redis save failed: {str(e)}")

# ─────────────────────────────────────────────
# Agent Callers
# ─────────────────────────────────────────────
async def call_faq_agent(query: str, conv_id: str) -> Dict:
    try:
        resp = await http_client.post(f"{FAQ_URL}/api/faq/ask",
                                      json={"question": query, "conversation_id": conv_id})
        resp.raise_for_status()
        data = resp.json()
        return {"answer": data.get("answer", ""), "agent": "FAQ",
                "tools_used": data.get("tools_used", []), "success": True}
    except Exception as e:
        logger.error(f"❌ FAQ Agent: {str(e)}")
        return {"answer": f"FAQ unavailable: {str(e)}", "agent": "FAQ", "tools_used": [], "success": False}

async def call_payroll_agent(query: str, employee_id: str, conv_id: str) -> Dict:
    try:
        resp = await http_client.post(f"{PAYROLL_URL}/api/payroll/query",
                                      json={"query": query, "employee_id": employee_id, "conversation_id": conv_id})
        resp.raise_for_status()
        data = resp.json()
        return {"answer": data.get("answer", ""), "agent": "Payroll",
                "tools_used": data.get("tools_used", []), "success": True}
    except Exception as e:
        logger.error(f"❌ Payroll Agent: {str(e)}")
        return {"answer": f"Payroll unavailable: {str(e)}", "agent": "Payroll", "tools_used": [], "success": False}

async def call_leave_agent(query: str, employee_id: str, conv_id: str) -> Dict:
    try:
        resp = await http_client.post(f"{LEAVE_URL}/api/leave/query",
                                      json={"query": query, "employee_id": employee_id, "conversation_id": conv_id})
        resp.raise_for_status()
        data = resp.json()
        return {"answer": data.get("answer", ""), "agent": "Leave",
                "tools_used": data.get("tools_used", []), "success": True}
    except Exception as e:
        logger.error(f"❌ Leave Agent: {str(e)}")
        return {"answer": f"Leave unavailable: {str(e)}", "agent": "Leave", "tools_used": [], "success": False}

async def call_recruitment_agent(query: str, conv_id: str) -> Dict:
    try:
        resp = await http_client.post(f"{RECRUITMENT_URL}/api/recruitment/query",
                                      json={"query": query, "conversation_id": conv_id})
        resp.raise_for_status()
        data = resp.json()
        return {"answer": data.get("answer", ""), "agent": "Recruitment",
                "tools_used": data.get("tools_used", []), "success": True}
    except Exception as e:
        logger.error(f"❌ Recruitment Agent: {str(e)}")
        return {"answer": f"Recruitment unavailable: {str(e)}", "agent": "Recruitment", "tools_used": [], "success": False}

async def call_performance_agent(query: str, employee_id: str, conv_id: str) -> Dict:
    try:
        resp = await http_client.post(f"{PERFORMANCE_URL}/api/performance/query",
                                      json={"query": query, "employee_id": employee_id, "conversation_id": conv_id})
        resp.raise_for_status()
        data = resp.json()
        return {"answer": data.get("answer", ""), "agent": "Performance",
                "tools_used": data.get("tools_used", []), "success": True}
    except Exception as e:
        logger.error(f"❌ Performance Agent: {str(e)}")
        return {"answer": f"Performance unavailable: {str(e)}", "agent": "Performance", "tools_used": [], "success": False}

AGENT_DISPATCH = {
    "FAQ":         lambda q, eid, cid: call_faq_agent(q, cid),
    "Payroll":     lambda q, eid, cid: call_payroll_agent(q, eid, cid),
    "Leave":       lambda q, eid, cid: call_leave_agent(q, eid, cid),
    "Recruitment": lambda q, eid, cid: call_recruitment_agent(q, cid),
    "Performance": lambda q, eid, cid: call_performance_agent(q, eid, cid),
}

# ─────────────────────────────────────────────
# Meta-Query Detection and Handler
# ─────────────────────────────────────────────
META_KEYWORDS = [
    "first question", "last question", "previous question",
    "what did i ask", "what have we", "our conversation",
    "earlier question", "summarise", "summarize", "recap",
    "what we talked", "what i asked", "go back to",
    "previous message", "earlier message", "what was my",
]

async def is_meta_query(query: str) -> bool:
    return any(kw in query.lower() for kw in META_KEYWORDS)

async def handle_meta_query(query: str, history: List[Dict]) -> str:
    if not history:
        return "I don't have any previous messages in this conversation yet. Feel free to ask anything about HR!"

    transcript = "\n".join([
        f"{i+1}. {'You' if m['role']=='user' else 'Assistant'}"
        f"{' ('+m['agent_used']+' Agent)' if m.get('agent_used') else ''}: {m['message']}"
        for i, m in enumerate(history)
    ])
    prompt = (f"Answer this question about the conversation using only the transcript:\n\n"
              f"Transcript:\n{transcript}\n\nQuestion: {query}")
    try:
        resp   = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=300
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        first_user = next((m for m in history if m["role"] == "user"), None)
        if first_user:
            return f"Your first question was: \"{first_user['message']}\""
        return "I couldn't retrieve the conversation history right now."

# ─────────────────────────────────────────────
# PLANNER — creates a step-by-step plan
# ─────────────────────────────────────────────
# PLANNER — ReAct-style: explicit Thought before plan
# ─────────────────────────────────────────────
async def create_plan(query: str, session: Dict, history: List[Dict]) -> List[str]:
    """
    Uses a ReAct-style prompt to reason explicitly before producing a plan.

    The model outputs:
      Thought: <reasoning about the query and what agents are needed>
      Plan: <JSON array>

    This makes the planning decision auditable and forces the model to
    justify its agent selection rather than pattern-matching silently.
    """
    session_hint = ""
    if session.get("last_service") and session.get("last_topic"):
        session_hint = (f"\nSession context: Employee recently asked about "
                        f"'{session['last_topic']}' via {session['last_service']} agent.")

    history_hint = ""
    if history:
        lines = [f"  {m['role']}"
                 f"{' ['+m['agent_used']+']' if m.get('agent_used') else ''}: "
                 f"{m['message'][:100]}" for m in history[-6:]]
        history_hint = "\nRecent conversation:\n" + "\n".join(lines)

    planning_prompt = f"""You are a ReAct planner for an HR multi-agent system.

Your job is to analyse the user's query and select the right agents to call.

{session_hint}
{history_hint}

Each agent has two properties — the TOPICS it knows about, and the ACTIONS it can perform:

Agent        | Topics                                      | Can perform actions?
-------------|---------------------------------------------|---------------------
FAQ          | Policies, benefits, office info, procedures | NO — information only
Payroll      | Salary, payslips, deductions, CPF, tax      | NO — information only
Leave        | Leave balances, leave history               | YES — can submit, approve, cancel leave requests
Recruitment  | Job openings, hiring process                | YES — can create job postings
Performance  | Goals, KPIs, reviews                        | YES — can create goals, update progress

Reasoning approach:
1. Identify what INFORMATION the query needs → which agent knows that topic?
2. Identify what ACTIONS the query needs → which agent can perform that action?
3. If both are needed, include both agents (information agent first, then action agent)
4. Maximum 3 agents. Later agents receive earlier agents' answers as context.

Follow this format EXACTLY:

Thought: <What information is needed? What actions are needed? Which agents cover each?>
Plan: <valid JSON array, e.g. ["FAQ", "Leave"]>

User query: "{query}"
"""

    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": planning_prompt}],
            temperature=0.0, max_tokens=200
        )
        raw = resp.choices[0].message.content.strip()

        # Log the Thought for auditability
        if "Thought:" in raw:
            thought = raw.split("Thought:")[1].split("Plan:")[0].strip()
            logger.info(f"💭 Planner Thought: {thought[:200]}")

        # Extract the Plan JSON
        if "Plan:" in raw:
            plan_raw = raw.split("Plan:")[-1].strip()
        else:
            plan_raw = raw

        plan  = json.loads(plan_raw)
        valid = [a for a in plan if a in AGENT_DISPATCH]
        if not valid:
            logger.warning(f"⚠️ Plan contained no valid agents: {plan_raw}")
            return ["FAQ"]
        logger.info(f"📋 Plan created: {valid}")
        return valid

    except Exception as e:
        logger.error(f"❌ Planner failed: {str(e)} — defaulting to FAQ")
        return ["FAQ"]


# ─────────────────────────────────────────────
# EXECUTOR — ReAct-style: re-evaluate after each step
# ─────────────────────────────────────────────
async def execute_plan(
    plan: List[str],
    original_query: str,
    employee_id: str,
    conv_id: str
) -> Dict:
    """
    Execute each agent step sequentially with ReAct re-evaluation.

    After each step the coordinator asks itself:
      "Do I now have enough information to answer the original question,
       or does the next planned step still add value?"

    This means the coordinator can short-circuit a multi-step plan if
    an earlier step already provides a complete answer, avoiding
    unnecessary downstream calls and token spend.
    """
    step_results       = []
    all_tools          = []
    cumulative_context = ""
    thoughts           = []

    for i, agent_name in enumerate(plan):
        logger.info(f"▶️  Step {i+1}/{len(plan)}: calling {agent_name} agent")

        # Build enriched query with cumulative context from prior steps
        if cumulative_context:
            enriched_query = (
                f"{original_query}\n\n"
                f"[Context from previous steps:\n{cumulative_context}]"
            )
        else:
            enriched_query = original_query

        dispatch = AGENT_DISPATCH.get(agent_name)
        if not dispatch:
            logger.error(f"❌ Unknown agent in plan: {agent_name}")
            continue

        result = await dispatch(enriched_query, employee_id, conv_id)
        step_results.append(result)
        all_tools.extend(result.get("tools_used", []))

        if result.get("answer"):
            cumulative_context += f"\n{agent_name} Agent: {result['answer']}"

        logger.info(f"✅ Step {i+1} ({agent_name}) done: {result['answer'][:80]}...")

        # ── ReAct re-evaluation after each step ──────────────────────────────
        # Only bother if there are more steps remaining in the plan
        remaining = plan[i+1:]
        if remaining:
            reeval_prompt = (
                f"Original question: {original_query}\n\n"
                f"Results so far:\n{cumulative_context}\n\n"
                f"Remaining planned steps: {remaining}\n\n"
                f"Thought: Do I already have sufficient information to fully answer "
                f"the original question? Or do the remaining steps add essential value?\n\n"
                f"Reply with ONLY one of:\n"
                f"  CONTINUE — remaining steps are needed\n"
                f"  DONE — I already have enough information"
            )
            try:
                eval_resp = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": reeval_prompt}],
                    temperature=0.0, max_tokens=20
                )
                decision = eval_resp.choices[0].message.content.strip().upper()
                thoughts.append(f"Step {i+1} re-eval: {decision}")
                logger.info(f"🤔 Re-evaluation after step {i+1}: {decision}")

                if "DONE" in decision:
                    logger.info(
                        f"⚡ Short-circuiting plan at step {i+1} — "
                        f"skipping {remaining}"
                    )
                    break   # goal already achieved — skip remaining agents

            except Exception as e:
                logger.warning(f"⚠️ Re-evaluation failed: {str(e)} — continuing plan")

    return {"step_results": step_results, "all_tools": all_tools, "thoughts": thoughts}


# ─────────────────────────────────────────────
# SYNTHESISER — ReAct Final Answer format
# ─────────────────────────────────────────────
async def synthesise_results(original_query: str, step_results: List[Dict]) -> str:
    """
    If only one step ran, return its answer directly.
    If multiple steps ran, use a ReAct-style synthesis prompt that forces
    explicit reasoning before the final answer.
    """
    if len(step_results) == 1:
        return step_results[0].get("answer", "I was unable to generate a response.")

    results_text = "\n\n".join([
        f"--- {r['agent']} Agent ---\n{r['answer']}"
        for r in step_results if r.get("answer")
    ])

    synthesis_prompt = (
        f"You are synthesising results from multiple HR specialist agents.\n"
        f"Follow the ReAct format:\n\n"
        f"Thought: Review the specialist responses below and reason about how they "
        f"collectively answer the original question. Identify any gaps or contradictions.\n\n"
        f"Final Answer: Provide a single, coherent, well-structured response that "
        f"addresses ALL aspects of the original question. Do not repeat agent labels.\n\n"
        f"---\n"
        f"Original question: {original_query}\n\n"
        f"Specialist responses:\n{results_text}\n"
        f"---\n\n"
        f"Now produce your Thought and Final Answer:"
    )

    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": synthesis_prompt}],
            temperature=0.2, max_tokens=800
        )
        raw = resp.choices[0].message.content.strip()

        # Log the synthesis Thought
        if "Thought:" in raw:
            thought = raw.split("Thought:")[1].split("Final Answer:")[0].strip()
            logger.info(f"💭 Synthesis Thought: {thought[:150]}")

        # Extract Final Answer
        if FINAL_ANSWER_MARKER in raw:
            return raw.split(FINAL_ANSWER_MARKER, 1)[-1].strip()

        # Fallback — model responded without the marker
        return raw.strip()

    except Exception as e:
        logger.error(f"❌ Synthesis failed: {str(e)}")
        return "\n\n".join([f"**{r['agent']}:** {r['answer']}" for r in step_results])

# ─────────────────────────────────────────────
# Startup / Shutdown
# ─────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    global mongo_client, db, redis_client
    logger.info("🚀 Coordinator Agent v3 Starting (Plan-and-Execute)")
    logger.info(f"OpenAI: {'✅' if OPENAI_API_KEY else '❌'} | MongoDB: {MONGODB_URL} | Redis: {REDIS_URL}")
    try:
        mongo_client = AsyncIOMotorClient(MONGODB_URL)
        db = mongo_client[DB_NAME]
        await mongo_client.admin.command("ping")
        logger.info("✅ MongoDB connected")
    except Exception as e:
        logger.error(f"❌ MongoDB failed: {str(e)}")
    try:
        redis_client = await aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
        logger.info("✅ Redis connected")
    except Exception as e:
        logger.error(f"❌ Redis failed: {str(e)}")

@app.on_event("shutdown")
async def shutdown_event():
    await http_client.aclose()
    if mongo_client:
        mongo_client.close()
    if redis_client:
        await redis_client.aclose()

# ─────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────
@app.get("/health")
async def health_check():
    mongo_status = redis_status = "disconnected"
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
        "status": "healthy", "service": "coordinator-agent", "version": "3.1.0",
        "mode": "react-plan-and-execute",
        "openai_status": "configured" if OPENAI_API_KEY else "missing",
        "mongodb_status": mongo_status, "redis_status": redis_status,
        "agents": {k: url for k, url in [("faq", FAQ_URL), ("payroll", PAYROLL_URL),
                                           ("leave", LEAVE_URL), ("recruitment", RECRUITMENT_URL),
                                           ("performance", PERFORMANCE_URL)]}
    }

# ─────────────────────────────────────────────
# Main Endpoint — Plan-and-Execute
# ─────────────────────────────────────────────
@app.post("/api/coordinator/ask", response_model=CoordinatorResponse)
async def ask_coordinator(request: CoordinatorRequest):
    try:
        logger.info(f"📥 Coordinator received: {request.query}")
        conv_id     = request.conversation_id or str(uuid.uuid4())
        employee_id = request.employee_id or "anonymous"

        # ── Guardrail ─────────────────────────────────────────────────────────
        if any(kw in request.query.lower() for kw in COORDINATOR_SENSITIVE_KEYWORDS):
            logger.warning(f"🚨 Guardrail triggered: {request.query}")
            await log_message(conv_id, "user",      request.query,                   employee_id, flagged=True)
            await log_message(conv_id, "assistant", COORDINATOR_ESCALATION_RESPONSE, employee_id, flagged=True)
            return CoordinatorResponse(
                answer=COORDINATOR_ESCALATION_RESPONSE, agent_used="guardrail",
                confidence=1.0, conversation_id=conv_id, plan_executed=[], tools_used=[],
                metadata={"flagged": True}
            )

        # ── Level 2: Redis session ────────────────────────────────────────────
        session = await get_session(employee_id)
        if session:
            logger.info(f"📦 Session: last={session.get('last_service')}, topic={str(session.get('last_topic',''))[:40]}")

        # ── Level 1: MongoDB conversation history ─────────────────────────────
        history = await get_conversation_history(conv_id, limit=10)
        logger.info(f"💬 {len(history)} historical messages loaded")

        # ── Meta-query intercept ──────────────────────────────────────────────
        if await is_meta_query(request.query):
            logger.info("🧠 Meta-query detected")
            answer = await handle_meta_query(request.query, history)
            await log_message(conv_id, "user",      request.query, employee_id)
            await log_message(conv_id, "assistant", answer,        employee_id, agent_used="Coordinator")
            return CoordinatorResponse(
                answer=answer, agent_used="Coordinator", confidence=0.99,
                conversation_id=conv_id, plan_executed=["Coordinator"], tools_used=[],
                metadata={"routing_method": "meta_query"}
            )

        # ── PLAN — decide which agents to call and in what order ──────────────
        plan = await create_plan(request.query, session, history)
        logger.info(f"📋 Execution plan: {plan}")

        # ── EXECUTE — run each step with ReAct re-evaluation between steps ─────
        execution    = await execute_plan(plan, request.query, employee_id, conv_id)
        step_results = execution["step_results"]
        all_tools    = execution["all_tools"]
        plan_thoughts= execution.get("thoughts", [])

        if not step_results or not any(r.get("success") for r in step_results):
            raise HTTPException(status_code=500, detail="All agent steps failed")

        # ── SYNTHESISE — ReAct Thought + Final Answer format ───────────────────
        final_answer = await synthesise_results(request.query, step_results)
        agents_used  = [r["agent"] for r in step_results]
        agent_label  = " + ".join(agents_used)

        # Collect all thoughts from domain agents too
        all_thoughts = plan_thoughts + [
            t for r in step_results
            for t in r.get("thoughts", [])
        ]
        logger.info(f"✅ ReAct plan complete: {agent_label} | {len(all_thoughts)} thoughts logged")

        # ── Persist ───────────────────────────────────────────────────────────
        await log_message(conv_id, "user",      request.query, employee_id, agent_used=None)
        await log_message(conv_id, "assistant", final_answer,  employee_id, agent_used=agent_label)

        # ── Update Redis session ──────────────────────────────────────────────
        await save_session(employee_id, {
            "last_service": agents_used[-1].lower(),
            "last_topic":   request.query[:100]
        })

        return CoordinatorResponse(
            answer=final_answer,
            agent_used=agent_label,
            confidence=0.95,
            conversation_id=conv_id,
            plan_executed=agents_used,   # actual agents called (may differ from plan after short-circuit)
            tools_used=all_tools,
            thoughts=all_thoughts,
            metadata={
                "routing_method":  "react_plan_and_execute",
                "planned_steps":   plan,
                "executed_steps":  len(step_results),
                "short_circuited": len(plan) > len(step_results),
                "timestamp":       datetime.now().isoformat(),
                "employee_id":     employee_id,
                "history_used":    len(history),
                "session_loaded":  bool(session)
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Coordinator error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────
# Supporting Endpoints
# ─────────────────────────────────────────────
@app.get("/api/coordinator/agents")
async def list_agents():
    return {
        "agents": [
            {"name": "FAQ",         "url": FAQ_URL,         "description": "HR policies and general questions"},
            {"name": "Payroll",     "url": PAYROLL_URL,     "description": "Salary, payslips, deductions"},
            {"name": "Leave",       "url": LEAVE_URL,       "description": "Leave balance and requests"},
            {"name": "Recruitment", "url": RECRUITMENT_URL, "description": "Job openings and hiring"},
            {"name": "Performance", "url": PERFORMANCE_URL, "description": "Goals, KPIs, reviews"},
        ],
        "routing_strategy": "ReAct plan-and-execute: Thought → Plan → Execute (with re-evaluation) → Synthesise (Final Answer)"
    }

@app.get("/api/coordinator/history/chat")
async def get_chat_history(employee_id: str, limit: int = 50):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor = db.chat_history.find(
        {"employee_id": employee_id, "service": "coordinator"}, sort=[("timestamp", -1)]
    ).limit(limit)
    history = await cursor.to_list(length=limit)
    def ser(d):
        if "_id" in d:
            d["id"] = str(d["_id"]); del d["_id"]
        return d
    return {"employee_id": employee_id, "history": [ser(h) for h in history]}

@app.get("/api/coordinator/history/chat/{conversation_id}")
async def get_conversation(conversation_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor = db.chat_history.find({"conversation_id": conversation_id}, sort=[("timestamp", 1)])
    messages = await cursor.to_list(length=200)
    def ser(d):
        if "_id" in d:
            d["id"] = str(d["_id"]); del d["_id"]
        return d
    return {"conversation_id": conversation_id, "messages": [ser(m) for m in messages]}

@app.get("/api/coordinator/session/{employee_id}")
async def get_employee_session(employee_id: str):
    session = await get_session(employee_id)
    if not session:
        return {"employee_id": employee_id, "session": None, "message": "No active session"}
    return {"employee_id": employee_id, "session": session}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8007)))