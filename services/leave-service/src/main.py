"""
Leave Management Agent - AI Agent with tool calling.
The AI can now actually submit leave requests, check balances,
and approve leave — not just describe how to do it.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
import sys, os, json, uuid, traceback
from dotenv import load_dotenv
import logging
from openai import OpenAI
from datetime import datetime, timedelta
import uvicorn
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from react_engine import run_react_loop, build_react_system_prompt

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Leave Management Agent", description="Leave AI Agent with tool calling", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client         = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
MONGODB_URL    = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
DB_NAME        = os.getenv("DB_NAME", "leave_db")
mongo_client   = None
db             = None

CONTEXT_MARKER = "[Prior conversation context:"

class LeaveQueryRequest(BaseModel):
    query: str
    employee_id: Optional[str] = None
    conversation_id: Optional[str] = None

class LeaveQueryResponse(BaseModel):
    answer: str
    data: Optional[Dict] = None
    conversation_id: str
    tools_used: List[str] = []

LEAVE_SENSITIVE_KEYWORDS = [
    "other employee", "everyone's leave", "leave balance of", "force approve",
    "unlimited leave", "harassment", "unfair", "override", "ignore instructions",
]
LEAVE_ESCALATION_RESPONSE = (
    "This query involves a sensitive leave matter that requires direct HR support. "
    "Please contact hr@company.com or call +65 6123 4567."
)

_LEAVE_SYSTEM_PROMPT_BASE = """You are a Leave Management AI Agent for ResourcefulAI. You have tools to look up balances and submit requests.

Always use tools to retrieve real data before answering. You can:
- Check leave balances
- Submit leave requests on behalf of the employee (with their consent)
- Retrieve leave history
- Approve pending leave requests (manager action)

GUARDRAILS:
- Only access the requesting employee's own data
- Always confirm leave details with the employee before submitting a request
- Do not grant extra leave days beyond policy
- Escalate medical/legal queries to HR

Company Leave Policy:
- Annual: 18 days/year | Sick: 14 days/year | Personal: 3 days/year
- Requests should be submitted 2 weeks in advance (except sick leave)"""

# Wrap with ReAct instruction
LEAVE_SYSTEM_PROMPT = build_react_system_prompt(_LEAVE_SYSTEM_PROMPT_BASE)

# ─────────────────────────────────────────────
# Tool Definitions
# ─────────────────────────────────────────────
LEAVE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_leave_balance",
            "description": "Get the current leave balance for an employee showing used, remaining, and total days for each leave type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {"type": "string"}
                },
                "required": ["employee_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_leave_history",
            "description": "Retrieve the employee's past and pending leave requests.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {"type": "string"},
                    "limit":       {"type": "integer", "description": "Max records to return (default 10)"}
                },
                "required": ["employee_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_leave_request",
            "description": "Submit a leave request for an employee. Returns a request ID if successful. Only call this after confirming details with the employee.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {"type": "string"},
                    "type":        {"type": "string", "enum": ["annual", "sick", "personal"], "description": "Type of leave"},
                    "start_date":  {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                    "end_date":    {"type": "string", "description": "End date in YYYY-MM-DD format"},
                    "reason":      {"type": "string", "description": "Reason for the leave request"}
                },
                "required": ["employee_id", "type", "start_date", "end_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_leave_days",
            "description": "Calculate number of working days (weekdays only) between two dates. Use this before submitting to confirm day count with the employee.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date":   {"type": "string", "description": "YYYY-MM-DD"}
                },
                "required": ["start_date", "end_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "approve_leave_request",
            "description": "Approve a pending leave request. This is a manager/HR action and deducts from the employee's balance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "request_id": {"type": "string", "description": "The leave request ID to approve"}
                },
                "required": ["request_id"]
            }
        }
    }
]

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def serialize_doc(doc):
    if doc and "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc

def _count_weekdays(start_date: str, end_date: str) -> int:
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end   = datetime.strptime(end_date,   "%Y-%m-%d")
    days, current = 0, start
    while current <= end:
        if current.weekday() < 5:
            days += 1
        current += timedelta(days=1)
    return days

async def log_message(conv_id, role, message, employee_id=None, flagged=False):
    if db is None:
        return
    try:
        await db.chat_history.insert_one({
            "conversation_id": conv_id, "service": "leave",
            "employee_id": employee_id, "role": role,
            "message": message, "flagged": flagged,
            "timestamp": datetime.now().isoformat()
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
# Tool Executor
# ─────────────────────────────────────────────
async def execute_tool(tool_name: str, tool_args: dict) -> str:
    try:
        if tool_name == "get_leave_balance":
            doc = await db.leave_balances.find_one({"employee_id": tool_args["employee_id"]})
            if not doc:
                return json.dumps({"error": "Employee not found"})
            return json.dumps({
                "employee_id": tool_args["employee_id"],
                "annual":      doc["annual"],
                "sick":        doc["sick"],
                "personal":    doc["personal"]
            })

        elif tool_name == "get_leave_history":
            limit  = tool_args.get("limit", 10)
            cursor = db.leave_history.find(
                {"employee_id": tool_args["employee_id"]},
                sort=[("submitted_at", -1)]
            ).limit(limit)
            history = await cursor.to_list(length=limit)
            return json.dumps([serialize_doc(h) for h in history])

        elif tool_name == "submit_leave_request":
            employee_id = tool_args["employee_id"]
            leave_type  = tool_args["type"]
            start_date  = tool_args["start_date"]
            end_date    = tool_args["end_date"]
            reason      = tool_args.get("reason", "")

            # Check balance
            balance_doc = await db.leave_balances.find_one({"employee_id": employee_id})
            if not balance_doc:
                return json.dumps({"error": "Employee not found"})

            days      = _count_weekdays(start_date, end_date)
            remaining = balance_doc[leave_type]["remaining"]

            if remaining < days:
                return json.dumps({
                    "error": f"Insufficient {leave_type} leave. Remaining: {remaining} days, requested: {days} days."
                })

            entry = {
                "employee_id":  employee_id,
                "type":         leave_type,
                "start_date":   start_date,
                "end_date":     end_date,
                "days":         days,
                "status":       "pending",
                "submitted_at": datetime.now().isoformat(),
                "reason":       reason
            }
            result     = await db.leave_history.insert_one(entry)
            request_id = str(result.inserted_id)
            logger.info(f"✅ Leave request {request_id} submitted by agent")
            return json.dumps({
                "success":    True,
                "request_id": request_id,
                "days":       days,
                "status":     "pending",
                "message":    f"Leave request submitted successfully for {days} day(s)."
            })

        elif tool_name == "calculate_leave_days":
            days = _count_weekdays(tool_args["start_date"], tool_args["end_date"])
            return json.dumps({
                "start_date": tool_args["start_date"],
                "end_date":   tool_args["end_date"],
                "working_days": days,
                "note": "Excludes weekends. Public holidays not deducted automatically."
            })

        elif tool_name == "approve_leave_request":
            try:
                oid = ObjectId(tool_args["request_id"])
            except Exception:
                return json.dumps({"error": "Invalid request ID"})

            req = await db.leave_history.find_one({"_id": oid})
            if not req:
                return json.dumps({"error": "Leave request not found"})
            if req["status"] == "approved":
                return json.dumps({"error": "Already approved"})

            await db.leave_history.update_one({"_id": oid}, {"$set": {"status": "approved"}})
            await db.leave_balances.update_one(
                {"employee_id": req["employee_id"]},
                {"$inc": {
                    f"{req['type']}.used": req["days"],
                    f"{req['type']}.remaining": -req["days"]
                }}
            )
            return json.dumps({"success": True, "request_id": tool_args["request_id"], "status": "approved"})

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        logger.error(f"❌ Tool {tool_name} failed: {str(e)}")
        return json.dumps({"error": str(e)})

# ─────────────────────────────────────────────
# Seed Data
# ─────────────────────────────────────────────
SEED_BALANCES = [
    {"employee_id": "EMP000001",
     "annual": {"total": 18, "used": 5, "remaining": 13},
     "sick":   {"total": 14, "used": 2, "remaining": 12},
     "personal": {"total": 3, "used": 1, "remaining": 2}},
    {"employee_id": "EMP000002",
     "annual": {"total": 18, "used": 8, "remaining": 10},
     "sick":   {"total": 14, "used": 1, "remaining": 13},
     "personal": {"total": 3, "used": 0, "remaining": 3}},
]
SEED_HISTORY = [
    {"employee_id": "EMP000001", "type": "annual",
     "start_date": "2024-12-25", "end_date": "2024-12-29",
     "days": 5, "status": "approved", "submitted_at": "2024-12-01T10:00:00"},
]

@app.on_event("startup")
async def startup_event():
    global mongo_client, db
    logger.info("🚀 Leave Agent v2 Starting (with tool calling)")
    try:
        mongo_client = AsyncIOMotorClient(MONGODB_URL)
        db = mongo_client[DB_NAME]
        await mongo_client.admin.command("ping")
        logger.info("✅ MongoDB connected")
        if await db.leave_balances.count_documents({}) == 0:
            await db.leave_balances.insert_many(SEED_BALANCES)
        if await db.leave_history.count_documents({}) == 0:
            await db.leave_history.insert_many(SEED_HISTORY)
    except Exception as e:
        logger.error(f"❌ MongoDB failed: {str(e)}")

@app.on_event("shutdown")
async def shutdown_event():
    if mongo_client:
        mongo_client.close()

@app.get("/health")
async def health_check():
    mongo_status = "disconnected"
    try:
        if mongo_client:
            await mongo_client.admin.command("ping")
            mongo_status = "connected"
    except Exception:
        mongo_status = "error"
    return {"status": "healthy", "service": "leave-agent", "version": "2.0.0",
            "openai_status": "configured" if OPENAI_API_KEY else "missing",
            "mongodb_status": mongo_status, "mode": "agentic-tool-calling"}

# ─────────────────────────────────────────────
# AI Query Endpoint — Agentic Loop
# ─────────────────────────────────────────────
@app.post("/api/leave/query", response_model=LeaveQueryResponse)
async def query_leave(request: LeaveQueryRequest):
    try:
        logger.info(f"📥 Leave query: {request.query}")
        if not client:
            raise HTTPException(status_code=500, detail="OpenAI not configured")
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        conv_id = request.conversation_id or str(uuid.uuid4())

        original_query = request.query
        if CONTEXT_MARKER in request.query:
            original_query = request.query.split(CONTEXT_MARKER)[0].strip()

        if any(kw in original_query.lower() for kw in LEAVE_SENSITIVE_KEYWORDS):
            logger.warning(f"🚨 Sensitive leave query: {original_query}")
            await log_message(conv_id, "user",      request.query,             request.employee_id, flagged=True)
            await log_message(conv_id, "assistant", LEAVE_ESCALATION_RESPONSE, request.employee_id, flagged=True)
            return LeaveQueryResponse(answer=LEAVE_ESCALATION_RESPONSE,
                                      data=None, conversation_id=conv_id, tools_used=[])

        messages = [{"role": "system", "content": LEAVE_SYSTEM_PROMPT}]
        if request.employee_id:
            messages.append({"role": "system", "content":
                f"The employee making this request has ID: {request.employee_id}."})

        history = await get_conversation_history(conv_id, limit=10)
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["message"]})
        messages.append({"role": "user", "content": request.query})

        # ── Genuine ReAct loop ────────────────────────────────────────────
        leave_data = None
        result = await run_react_loop(
            openai_client=client,
            messages=messages,
            tools=LEAVE_TOOLS,
            tool_executor=execute_tool,
            service_name="Leave",
            max_iterations=8,
        )
        answer     = result["answer"]
        tools_used = result["tools_used"]
        logger.info(
            f"✅ Leave ReAct complete — {result['iterations']} iteration(s), "
            f"tools: {tools_used}, thoughts: {len(result['thoughts'])}"
        )
        await log_message(conv_id, "user",      request.query, request.employee_id)
        await log_message(conv_id, "assistant", answer,        request.employee_id)
        return LeaveQueryResponse(answer=answer, data=leave_data,
                                            conversation_id=conv_id, tools_used=tools_used)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Leave error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/leave/balance")
async def get_leave_balance(employee_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    doc = await db.leave_balances.find_one({"employee_id": employee_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"employee_id": employee_id, "balances": {
        "annual": doc["annual"], "sick": doc["sick"], "personal": doc["personal"]}}

@app.get("/api/leave/history")
async def get_leave_history(employee_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor = db.leave_history.find({"employee_id": employee_id}, sort=[("submitted_at", -1)])
    history = await cursor.to_list(length=100)
    return {"employee_id": employee_id, "history": [serialize_doc(h) for h in history]}

@app.get("/api/leave/history/chat")
async def get_chat_history(employee_id: str, limit: int = 50):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor = db.chat_history.find(
        {"employee_id": employee_id, "service": "leave"}, sort=[("timestamp", -1)]
    ).limit(limit)
    history = await cursor.to_list(length=limit)
    return {"employee_id": employee_id, "history": [serialize_doc(h) for h in history]}

@app.get("/api/leave/history/chat/{conversation_id}")
async def get_conversation(conversation_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor = db.chat_history.find({"conversation_id": conversation_id}, sort=[("timestamp", 1)])
    messages = await cursor.to_list(length=200)
    return {"conversation_id": conversation_id, "messages": [serialize_doc(m) for m in messages]}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8004)))