"""
Leave Management Agent - Leave Request and Tracking Assistant
Handles leave requests, balance tracking, and leave approvals using OpenAI
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
import os
from dotenv import load_dotenv
import logging
from openai import OpenAI
from datetime import datetime, timedelta
import uvicorn
import uuid
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Leave Management Agent",
    description="Leave Request and Tracking Assistant",
    version="1.0.0"
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

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ─────────────────────────────────────────────
# MongoDB Setup
# ─────────────────────────────────────────────
MONGODB_URL = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "leave_db")

mongo_client: AsyncIOMotorClient = None
db = None

# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────
class LeaveRequest(BaseModel):
    employee_id: str
    type: str
    start_date: str
    end_date: str
    reason: Optional[str] = None

class LeaveResponse(BaseModel):
    request_id: str
    employee_id: str
    type: str
    start_date: str
    end_date: str
    days: int
    status: str
    submitted_at: str

class LeaveQueryRequest(BaseModel):
    query: str
    employee_id: Optional[str] = None
    conversation_id: Optional[str] = None      # ← thread identifier

class LeaveQueryResponse(BaseModel):
    answer: str
    data: Optional[Dict] = None
    conversation_id: str                        # ← returned so frontend can reuse it

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def serialize_doc(doc: dict) -> dict:
    if doc and "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc

def calculate_leave_days(start_date: str, end_date: str) -> int:
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = 0
    current = start
    while current <= end:
        if current.weekday() < 5:
            days += 1
        current += timedelta(days=1)
    return days

async def log_message(conv_id: str, role: str, message: str, employee_id: str = None,
                      flagged: bool = False):
    """Persist a single chat message. Never raises — logging must not break the main flow."""
    if db is None:
        return
    try:
        await db.chat_history.insert_one({
            "conversation_id": conv_id,
            "service": "leave",
            "employee_id": employee_id,
            "role": role,
            "message": message,
            "flagged": flagged,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.warning(f"⚠️ Failed to log message: {str(e)}")

async def get_conversation_history(conv_id: str, limit: int = 10) -> List[Dict]:
    """Fetch the last N messages for a conversation, oldest-first for correct context order."""
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
# Seed Data
# ─────────────────────────────────────────────
SEED_BALANCES = [
    {
        "employee_id": "EMP000001",
        "annual":   {"total": 18, "used": 5,  "remaining": 13},
        "sick":     {"total": 14, "used": 2,  "remaining": 12},
        "personal": {"total": 3,  "used": 1,  "remaining": 2}
    },
    {
        "employee_id": "EMP000002",
        "annual":   {"total": 18, "used": 8,  "remaining": 10},
        "sick":     {"total": 14, "used": 1,  "remaining": 13},
        "personal": {"total": 3,  "used": 0,  "remaining": 3}
    }
]

SEED_HISTORY = [
    {
        "employee_id": "EMP000001",
        "type": "annual",
        "start_date": "2024-12-25",
        "end_date": "2024-12-29",
        "days": 5,
        "status": "approved",
        "submitted_at": "2024-12-01T10:00:00"
    },
    {
        "employee_id": "EMP000001",
        "type": "sick",
        "start_date": "2024-11-15",
        "end_date": "2024-11-16",
        "days": 2,
        "status": "approved",
        "submitted_at": "2024-11-15T08:30:00"
    }
]

LEAVE_SYSTEM_PROMPT = """You are a helpful Leave Management Assistant. You help employees with:
- Leave balance inquiries
- Leave policy questions
- Leave request guidance
- Leave approval status
- Holiday calendar information

Company Leave Policy:
- Annual Leave: 18 days per year
- Sick Leave: 14 days per year (with medical certificate)
- Personal Leave: 3 days per year
- Leave requests should be submitted at least 2 weeks in advance (except sick leave)
- Maximum consecutive leave: 14 days for annual leave

Be professional and helpful. Provide clear information about leave balances and policies.

GUARDRAILS — NEVER DO THESE:
DO NOT disclose another employee's leave balance or leave history
DO NOT approve or reject leave requests — that requires manager authorisation
DO NOT grant extra leave days beyond what policy allows
DO NOT advise on medical certification or diagnoses for sick leave
DO NOT handle complaints about unfair leave treatment — escalate to HR
"""

# Queries matching these keywords are short-circuited before hitting OpenAI.
# They are logged with flagged=True for HR audit and return a static escalation response.
LEAVE_SENSITIVE_KEYWORDS = [
    "other employee",       # attempting to access another person's data
    "everyone's leave",     # bulk leave data disclosure attempt
    "leave balance of",     # fishing for another person's balance
    "approve my leave",     # AI cannot approve — manager only
    "force approve",        # attempting to bypass approval workflow
    "extra leave",          # requesting out-of-policy leave allocation
    "unlimited leave",      # policy violation request
    "medical certificate",  # medical advice / certification guidance
    "doctor's note",        # medical documentation advice
    "harassment",           # workplace complaint — escalate to HR
    "unfair",               # dispute requiring HR involvement
    "override",             # prompt injection attempt
    "ignore instructions",  # jailbreak attempt
]

LEAVE_ESCALATION_RESPONSE = (
    "This query involves a sensitive leave matter that requires direct HR support. "
    "For leave approvals, disputes, or policy exceptions, please contact hr@company.com "
    "or call +65 6123 4567 to speak with an HR representative who can properly assist you."
)

# ─────────────────────────────────────────────
# Startup / Shutdown
# ─────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    global mongo_client, db

    logger.info("=" * 50)
    logger.info("🚀 Leave Management Agent Starting Up")
    logger.info("=" * 50)
    logger.info(f"OpenAI API:  {'✅ Configured' if OPENAI_API_KEY else '❌ Missing'}")
    logger.info(f"MongoDB URL: {MONGODB_URL}")

    try:
        mongo_client = AsyncIOMotorClient(MONGODB_URL)
        db = mongo_client[DB_NAME]
        await mongo_client.admin.command("ping")
        logger.info("✅ MongoDB connected successfully")

        if await db.leave_balances.count_documents({}) == 0:
            await db.leave_balances.insert_many(SEED_BALANCES)
            logger.info(f"🌱 Seeded {len(SEED_BALANCES)} leave balances")

        if await db.leave_history.count_documents({}) == 0:
            await db.leave_history.insert_many(SEED_HISTORY)
            logger.info(f"🌱 Seeded {len(SEED_HISTORY)} leave history records")

    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {str(e)}")

    logger.info("=" * 50)

@app.on_event("shutdown")
async def shutdown_event():
    if mongo_client:
        mongo_client.close()
        logger.info("🔌 MongoDB connection closed")

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

    return {
        "status": "healthy",
        "service": "leave-management-agent",
        "version": "1.0.0",
        "openai_status": "configured" if OPENAI_API_KEY else "missing",
        "mongodb_status": mongo_status
    }

# ─────────────────────────────────────────────
# AI Query — Level 1 Conversational Memory
# ─────────────────────────────────────────────
@app.post("/api/leave/query", response_model=LeaveQueryResponse)
async def query_leave(request: LeaveQueryRequest):
    try:
        logger.info(f"📥 Leave query: {request.query}")

        if not client:
            raise HTTPException(status_code=500, detail="OpenAI not configured")
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        # Use provided conversation_id or generate a new one
        conv_id = request.conversation_id or str(uuid.uuid4())

        # ── Strip coordinator context before guardrail check ──────────────────
        CONTEXT_MARKER = "[Prior conversation context:"
        original_query = request.query
        if CONTEXT_MARKER in request.query:
            original_query = request.query.split(CONTEXT_MARKER)[0].strip()

        # ── Guardrail: sensitive keyword intercept (original query only) ──────
        query_lower = original_query.lower()
        if any(kw in query_lower for kw in LEAVE_SENSITIVE_KEYWORDS):
            logger.warning(f"🚨 Sensitive leave query intercepted: {original_query}")
            await log_message(conv_id, "user",      request.query,             request.employee_id, flagged=True)
            await log_message(conv_id, "assistant", LEAVE_ESCALATION_RESPONSE, request.employee_id, flagged=True)
            return LeaveQueryResponse(
                answer=LEAVE_ESCALATION_RESPONSE,
                data=None,
                conversation_id=conv_id
            )

        # ── Build leave balance context from DB ──
        leave_context = ""
        leave_data = None

        if request.employee_id:
            balance_doc = await db.leave_balances.find_one({"employee_id": request.employee_id})
            if balance_doc:
                leave_data = {
                    "annual":   balance_doc["annual"],
                    "sick":     balance_doc["sick"],
                    "personal": balance_doc["personal"]
                }
                leave_context = f"""
Employee Leave Balance:
- Annual Leave:   {balance_doc['annual']['remaining']} days remaining (of {balance_doc['annual']['total']})
- Sick Leave:     {balance_doc['sick']['remaining']} days remaining (of {balance_doc['sick']['total']})
- Personal Leave: {balance_doc['personal']['remaining']} days remaining (of {balance_doc['personal']['total']})
"""

        # ── Start messages with system prompt ──
        messages = [{"role": "system", "content": LEAVE_SYSTEM_PROMPT}]

        if leave_context:
            messages.append({"role": "system", "content": leave_context})

        # ── Inject conversation history for Level 1 memory ──
        history = await get_conversation_history(conv_id, limit=10)
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["message"]})

        logger.info(f"💬 Injecting {len(history)} previous messages into context")

        # ── Append current user message ──
        messages.append({"role": "user", "content": request.query})

        # ── Call OpenAI ──
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=500
        )

        answer = response.choices[0].message.content.strip()
        logger.info("✅ Generated leave response")

        # ── Persist both sides of the exchange ──
        await log_message(conv_id, "user",      request.query, request.employee_id)
        await log_message(conv_id, "assistant", answer,        request.employee_id)

        return LeaveQueryResponse(
            answer=answer,
            data=leave_data,
            conversation_id=conv_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────
# Leave Request
# ─────────────────────────────────────────────
@app.post("/api/leave/request", response_model=LeaveResponse)
async def request_leave(request: LeaveRequest):
    try:
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        balance_doc = await db.leave_balances.find_one({"employee_id": request.employee_id})
        if not balance_doc:
            raise HTTPException(status_code=404, detail="Employee not found")

        days = calculate_leave_days(request.start_date, request.end_date)
        leave_type = request.type.lower()

        if leave_type not in ["annual", "sick", "personal"]:
            raise HTTPException(status_code=400, detail=f"Invalid leave type: {leave_type}")

        remaining = balance_doc[leave_type]["remaining"]
        if remaining < days:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient {leave_type} leave. You have {remaining} days remaining."
            )

        leave_entry = {
            "employee_id": request.employee_id,
            "type": leave_type,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "days": days,
            "status": "pending",
            "submitted_at": datetime.now().isoformat(),
            "reason": request.reason
        }

        result = await db.leave_history.insert_one(leave_entry)
        request_id = str(result.inserted_id)

        logger.info(f"✅ Leave request {request_id} submitted")

        return LeaveResponse(
            request_id=request_id,
            employee_id=request.employee_id,
            type=leave_type,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            status="pending",
            submitted_at=leave_entry["submitted_at"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error submitting leave: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────
# Balance & History
# ─────────────────────────────────────────────
@app.get("/api/leave/balance")
async def get_leave_balance(employee_id: str):
    try:
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        doc = await db.leave_balances.find_one({"employee_id": employee_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Employee not found")

        return {
            "employee_id": employee_id,
            "balances": {
                "annual":   doc["annual"],
                "sick":     doc["sick"],
                "personal": doc["personal"]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/leave/history")
async def get_leave_history(employee_id: str):
    try:
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        cursor = db.leave_history.find(
            {"employee_id": employee_id},
            sort=[("submitted_at", -1)]
        )
        history = await cursor.to_list(length=100)
        return {"employee_id": employee_id, "history": [serialize_doc(h) for h in history]}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────
# Approve Leave
# ─────────────────────────────────────────────
@app.put("/api/leave/approve/{request_id}")
async def approve_leave(request_id: str):
    try:
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        try:
            oid = ObjectId(request_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid request ID format")

        leave_req = await db.leave_history.find_one({"_id": oid})
        if not leave_req:
            raise HTTPException(status_code=404, detail="Leave request not found")

        if leave_req["status"] == "approved":
            raise HTTPException(status_code=400, detail="Leave request already approved")

        await db.leave_history.update_one({"_id": oid}, {"$set": {"status": "approved"}})

        await db.leave_balances.update_one(
            {"employee_id": leave_req["employee_id"]},
            {
                "$inc": {
                    f"{leave_req['type']}.used": leave_req["days"],
                    f"{leave_req['type']}.remaining": -leave_req["days"]
                }
            }
        )

        logger.info(f"✅ Leave request {request_id} approved")
        return {"request_id": request_id, "status": "approved", "message": "Leave request approved successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────
# Chat History Endpoints
# ─────────────────────────────────────────────
@app.get("/api/leave/history/chat")
async def get_chat_history(employee_id: str, limit: int = 50):
    """All recent chat messages for an employee."""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    cursor = db.chat_history.find(
        {"employee_id": employee_id, "service": "leave"},
        sort=[("timestamp", -1)]
    ).limit(limit)

    history = await cursor.to_list(length=limit)
    return {"employee_id": employee_id, "history": [serialize_doc(h) for h in history]}

@app.get("/api/leave/history/chat/{conversation_id}")
async def get_conversation(conversation_id: str):
    """All messages in a specific conversation thread, in chronological order."""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    cursor = db.chat_history.find(
        {"conversation_id": conversation_id},
        sort=[("timestamp", 1)]
    )

    messages = await cursor.to_list(length=200)
    return {"conversation_id": conversation_id, "messages": [serialize_doc(m) for m in messages]}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8004))
    uvicorn.run(app, host="0.0.0.0", port=port)