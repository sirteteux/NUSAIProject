"""
Payroll Agent - Salary and Compensation Assistant
Handles payroll queries, payslip generation, and salary information using OpenAI
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
import os
from dotenv import load_dotenv
import logging
from openai import OpenAI
from datetime import datetime
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
    title="Payroll Agent",
    description="Salary and Compensation Assistant",
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
DB_NAME = os.getenv("DB_NAME", "payroll_db")

mongo_client: AsyncIOMotorClient = None
db = None

# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────
class PayrollQueryRequest(BaseModel):
    query: str
    employee_id: Optional[str] = None
    conversation_id: Optional[str] = None      # ← thread identifier

class PayrollQueryResponse(BaseModel):
    answer: str
    data: Optional[Dict] = None
    conversation_id: str                        # ← returned so frontend can reuse it

class PayslipRequest(BaseModel):
    employee_id: str
    month: Optional[str] = None
    year: Optional[int] = None

class PayslipResponse(BaseModel):
    employee_id: str
    employee_name: str
    month: str
    year: int
    gross_salary: float
    deductions: Dict
    net_salary: float
    payment_date: str

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def serialize_doc(doc: dict) -> dict:
    if doc and "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc

async def log_message(conv_id: str, role: str, message: str, employee_id: str = None,
                      flagged: bool = False):
    """Persist a single chat message. Never raises — logging must not break the main flow."""
    if db is None:
        return
    try:
        await db.chat_history.insert_one({
            "conversation_id": conv_id,
            "service": "payroll",
            "employee_id": employee_id,
            "role": role,
            "message": message,
            "flagged": flagged,   # True for guardrail-intercepted messages
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
SEED_EMPLOYEES = [
    {
        "employee_id": "EMP000001",
        "name": "Admin User",
        "email": "admin@example.com",
        "department": "Administration",
        "position": "Administrator",
        "monthly_salary": 8000,
        "annual_salary": 96000,
        "currency": "SGD",
        "join_date": "2020-01-15",
        "tax_rate": 0.20,
        "cpf_rate": 0.20,
        "insurance": 200
    },
    {
        "employee_id": "EMP000002",
        "name": "John Doe",
        "email": "john@example.com",
        "department": "Engineering",
        "position": "Senior Developer",
        "monthly_salary": 7500,
        "annual_salary": 90000,
        "currency": "SGD",
        "join_date": "2021-03-10",
        "tax_rate": 0.18,
        "cpf_rate": 0.20,
        "insurance": 200
    }
]

PAYROLL_SYSTEM_PROMPT = """You are a helpful Payroll Assistant. You help employees with:
- Salary information and breakdowns
- Payslip queries
- Tax and deduction questions
- Bonus and allowance information
- Payment schedules
- Salary history

Be professional, accurate, and friendly. If you need specific employee data to answer,
let the user know you'll need their employee ID.

When providing salary information, always format currency as SGD (Singapore Dollars).

GUARDRAILS — NEVER DO THESE:
DO NOT disclose another employee's salary, payslip, or compensation details
DO NOT approve, process, or commit to salary changes, bonuses, or increments
DO NOT provide tax advice or interpret tax law
DO NOT discuss redundancy, retrenchment packages, or termination payouts
DO NOT share payroll system credentials or internal configuration details
"""

# Queries matching these keywords are short-circuited before hitting OpenAI.
# They are logged with flagged=True for HR audit and return a static escalation response.
PAYROLL_SENSITIVE_KEYWORDS = [
    "other employee",      # attempting to access another person's data
    "everyone's salary",   # bulk salary disclosure attempt
    "salary of",           # fishing for a specific person's pay
    "how much does",       # comparative salary query about others
    "retrench",            # redundancy / termination payout queries
    "terminate",           # termination-related payroll queries
    "lawsuit",             # legal disputes involving pay
    "underpaid",           # potential legal / dispute escalation
    "discrimination",      # pay discrimination complaints
    "override",            # prompt injection attempt
    "ignore instructions", # jailbreak attempt
]

PAYROLL_ESCALATION_RESPONSE = (
    "This query involves a sensitive payroll matter that requires direct HR support. "
    "Please contact hr@company.com or call +65 6123 4567 to speak with a payroll specialist "
    "who can properly assist you."
)

# ─────────────────────────────────────────────
# Startup / Shutdown
# ─────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    global mongo_client, db

    logger.info("=" * 50)
    logger.info("🚀 Payroll Agent Starting Up")
    logger.info("=" * 50)
    logger.info(f"OpenAI API:  {'✅ Configured' if OPENAI_API_KEY else '❌ Missing'}")
    logger.info(f"MongoDB URL: {MONGODB_URL}")

    try:
        mongo_client = AsyncIOMotorClient(MONGODB_URL)
        db = mongo_client[DB_NAME]
        await mongo_client.admin.command("ping")
        logger.info("✅ MongoDB connected successfully")

        if await db.employees.count_documents({}) == 0:
            await db.employees.insert_many(SEED_EMPLOYEES)
            logger.info(f"🌱 Seeded {len(SEED_EMPLOYEES)} employees")
        else:
            count = await db.employees.count_documents({})
            logger.info(f"📋 Found {count} existing employees in MongoDB")

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
        "service": "payroll-agent",
        "version": "1.0.0",
        "openai_status": "configured" if OPENAI_API_KEY else "missing",
        "mongodb_status": mongo_status
    }

# ─────────────────────────────────────────────
# Payslip Calculator
# ─────────────────────────────────────────────
async def calculate_payslip(employee_id: str, month: str = None, year: int = None) -> Dict:
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    emp = await db.employees.find_one({"employee_id": employee_id})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    if not month or not year:
        now = datetime.now()
        month = now.strftime("%B")
        year = now.year

    gross = emp["monthly_salary"]
    tax = gross * emp["tax_rate"]
    cpf = gross * emp["cpf_rate"]
    insurance = emp["insurance"]
    total_deductions = tax + cpf + insurance
    net_salary = gross - total_deductions
    payment_date = f"{year}-{datetime.strptime(month, '%B').month:02d}-25"

    return {
        "employee_id": employee_id,
        "employee_name": emp["name"],
        "department": emp["department"],
        "position": emp["position"],
        "month": month,
        "year": year,
        "gross_salary": gross,
        "deductions": {
            "income_tax": tax,
            "cpf": cpf,
            "insurance": insurance,
            "total": total_deductions
        },
        "net_salary": net_salary,
        "currency": emp["currency"],
        "payment_date": payment_date
    }

# ─────────────────────────────────────────────
# AI Query — Level 1 Conversational Memory
# ─────────────────────────────────────────────
@app.post("/api/payroll/query", response_model=PayrollQueryResponse)
async def query_payroll(request: PayrollQueryRequest):
    try:
        logger.info(f"📥 Payroll query: {request.query}")

        if not client:
            raise HTTPException(status_code=500, detail="OpenAI not configured")
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        # Use provided conversation_id or generate a new one
        conv_id = request.conversation_id or str(uuid.uuid4())

        # ── Guardrail: sensitive keyword intercept ──
        # Checked BEFORE hitting OpenAI — saves tokens and enforces policy instantly
        query_lower = request.query.lower()
        if any(kw in query_lower for kw in PAYROLL_SENSITIVE_KEYWORDS):
            logger.warning(f"🚨 Sensitive payroll query intercepted: {request.query}")
            await log_message(conv_id, "user",      request.query,              request.employee_id, flagged=True)
            await log_message(conv_id, "assistant", PAYROLL_ESCALATION_RESPONSE, request.employee_id, flagged=True)
            return PayrollQueryResponse(
                answer=PAYROLL_ESCALATION_RESPONSE,
                data=None,
                conversation_id=conv_id
            )

        # ── Build employee context from DB ──
        employee_context = ""
        employee_data = None

        if request.employee_id:
            emp = await db.employees.find_one({"employee_id": request.employee_id})
            if emp:
                employee_data = serialize_doc(emp)
                employee_context = f"""
Employee Information:
- Name: {emp['name']}
- Department: {emp['department']}
- Position: {emp['position']}
- Monthly Salary: {emp['currency']} {emp['monthly_salary']:,.2f}
- Annual Salary: {emp['currency']} {emp['annual_salary']:,.2f}
- Join Date: {emp['join_date']}
"""

        # ── Start messages with system prompt ──
        messages = [{"role": "system", "content": PAYROLL_SYSTEM_PROMPT}]

        if employee_context:
            messages.append({"role": "system", "content": employee_context})

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
        logger.info("✅ Generated payroll response")

        # ── Persist both sides of the exchange ──
        await log_message(conv_id, "user",      request.query, request.employee_id)
        await log_message(conv_id, "assistant", answer,        request.employee_id)

        return PayrollQueryResponse(
            answer=answer,
            data=employee_data,
            conversation_id=conv_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────
# Payslip Endpoints
# ─────────────────────────────────────────────
@app.post("/api/payroll/payslip", response_model=PayslipResponse)
async def get_payslip(request: PayslipRequest):
    try:
        payslip = await calculate_payslip(request.employee_id, request.month, request.year)
        return PayslipResponse(**payslip)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error generating payslip: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/payroll/payslip/{employee_id}")
async def get_payslip_by_id(employee_id: str, month: str = None, year: int = None):
    try:
        return await calculate_payslip(employee_id, month, year)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/payroll/history/{employee_id}")
async def get_salary_history(employee_id: str, months: int = 6):
    try:
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        emp = await db.employees.find_one({"employee_id": employee_id})
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        history = []
        now = datetime.now()

        for i in range(months):
            month_num = now.month - i
            year = now.year
            if month_num <= 0:
                month_num += 12
                year -= 1
            month_date = datetime(year, month_num, 1)
            month_name = month_date.strftime("%B")

            payslip = await calculate_payslip(employee_id, month_name, year)
            history.append({
                "month": month_name,
                "year": year,
                "gross": payslip["gross_salary"],
                "net": payslip["net_salary"],
                "payment_date": payslip["payment_date"]
            })

        return {"employee_id": employee_id, "employee_name": emp["name"], "history": history}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────
# Chat History Endpoints
# ─────────────────────────────────────────────
@app.get("/api/payroll/history/chat")
async def get_chat_history(employee_id: str, limit: int = 50):
    """All recent chat messages for an employee."""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    cursor = db.chat_history.find(
        {"employee_id": employee_id, "service": "payroll"},
        sort=[("timestamp", -1)]
    ).limit(limit)

    history = await cursor.to_list(length=limit)
    return {"employee_id": employee_id, "history": [serialize_doc(h) for h in history]}

@app.get("/api/payroll/history/chat/{conversation_id}")
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
    port = int(os.getenv("PORT", 8003))
    uvicorn.run(app, host="0.0.0.0", port=port)