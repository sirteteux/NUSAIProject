"""
Payroll Agent - Salary and Compensation AI Agent
Upgraded to true AI agent with OpenAI tool calling.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
import sys, os, json, uuid, traceback
from dotenv import load_dotenv
import logging
from openai import OpenAI
from datetime import datetime
import uvicorn
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from react_engine import run_react_loop, build_react_system_prompt

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Payroll Agent", description="Salary and Compensation AI Agent ReAct", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client         = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
MONGODB_URL    = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
DB_NAME        = os.getenv("DB_NAME", "payroll_db")
mongo_client   = None
db             = None

CONTEXT_MARKER = "[Prior conversation context:"

class PayrollQueryRequest(BaseModel):
    query: str
    employee_id: Optional[str] = None
    conversation_id: Optional[str] = None

class PayrollQueryResponse(BaseModel):
    answer: str
    data: Optional[Dict] = None
    conversation_id: str
    tools_used: List[str] = []

class PayslipRequest(BaseModel):
    employee_id: str
    month: Optional[str] = None
    year: Optional[int] = None

PAYROLL_SENSITIVE_KEYWORDS = [
    "other employee", "everyone's salary", "salary of", "how much does",
    "retrench", "terminate", "lawsuit", "underpaid", "discrimination",
    "override", "ignore instructions",
]
PAYROLL_ESCALATION_RESPONSE = (
    "This query involves a sensitive payroll matter that requires direct HR support. "
    "Please contact hr@company.com or call +65 6123 4567."
)

_PAYROLL_SYSTEM_PROMPT_BASE = """You are a Payroll AI Agent for ResourcefulAI. You have tools to look up real payroll data.

Always use tools to retrieve accurate information before answering. Do not guess salary figures. 
When providing salary information, always format currency as SGD (Singapore Dollars).

GUARDRAILS:
- Only show the requesting employee's own data — never another employee's
- Do not approve salary changes or bonuses without manager approval
- Do not provide tax advice or interpret tax law"""

# Wrap with ReAct instruction
PAYROLL_SYSTEM_PROMPT = build_react_system_prompt(_PAYROLL_SYSTEM_PROMPT_BASE)

# ─────────────────────────────────────────────
# Tool Definitions
# ─────────────────────────────────────────────
PAYROLL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_employee_info",
            "description": "Retrieve an employee's profile including salary, department, position, and join date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {"type": "string", "description": "The employee ID, e.g. EMP000001"}
                },
                "required": ["employee_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_payslip",
            "description": "Calculate and return a detailed payslip for a specific month and year, including gross salary, deductions (tax, CPF, insurance), and net salary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {"type": "string"},
                    "month":       {"type": "string", "description": "Month name, e.g. January"},
                    "year":        {"type": "integer", "description": "4-digit year, e.g. 2025"}
                },
                "required": ["employee_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_salary_history",
            "description": "Retrieve salary payment history for the last N months showing gross and net pay per month.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {"type": "string"},
                    "months":      {"type": "integer", "description": "Number of months of history to retrieve (default 6)"}
                },
                "required": ["employee_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_take_home",
            "description": "Calculate hypothetical take-home pay given a gross salary amount. Useful for 'what-if' salary questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "gross_salary":  {"type": "number", "description": "Gross monthly salary in SGD"},
                    "tax_rate":      {"type": "number", "description": "Tax rate as decimal (e.g. 0.20 for 20%)"},
                    "cpf_rate":      {"type": "number", "description": "CPF rate as decimal (e.g. 0.20 for 20%)"},
                    "insurance":     {"type": "number", "description": "Monthly insurance deduction in SGD"}
                },
                "required": ["gross_salary"]
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

async def log_message(conv_id, role, message, employee_id=None, flagged=False):
    if db is None:
        return
    try:
        await db.chat_history.insert_one({
            "conversation_id": conv_id, "service": "payroll",
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

async def _compute_payslip(emp: dict, month: str = None, year: int = None) -> dict:
    if not month or not year:
        now   = datetime.now()
        month = now.strftime("%B")
        year  = now.year
    gross = emp["monthly_salary"]
    tax   = gross * emp["tax_rate"]
    cpf   = gross * emp["cpf_rate"]
    ins   = emp["insurance"]
    total = tax + cpf + ins
    return {
        "employee_id":   emp["employee_id"],
        "employee_name": emp["name"],
        "month": month, "year": year,
        "gross_salary": gross,
        "deductions": {"income_tax": tax, "cpf": cpf, "insurance": ins, "total": total},
        "net_salary": gross - total,
        "currency": emp["currency"],
        "payment_date": f"{year}-{datetime.strptime(month, '%B').month:02d}-25"
    }

# ─────────────────────────────────────────────
# Tool Executor
# ─────────────────────────────────────────────
async def execute_tool(tool_name: str, tool_args: dict) -> str:
    try:
        if tool_name == "get_employee_info":
            emp = await db.employees.find_one({"employee_id": tool_args["employee_id"]})
            if not emp:
                return json.dumps({"error": "Employee not found"})
            emp = serialize_doc(emp)
            # Remove sensitive internal fields before returning to model
            emp.pop("tax_rate", None)
            emp.pop("cpf_rate", None)
            return json.dumps(emp)

        elif tool_name == "get_payslip":
            emp = await db.employees.find_one({"employee_id": tool_args["employee_id"]})
            if not emp:
                return json.dumps({"error": "Employee not found"})
            payslip = await _compute_payslip(
                emp,
                tool_args.get("month"),
                tool_args.get("year")
            )
            return json.dumps(payslip)

        elif tool_name == "get_salary_history":
            emp = await db.employees.find_one({"employee_id": tool_args["employee_id"]})
            if not emp:
                return json.dumps({"error": "Employee not found"})
            months = tool_args.get("months", 6)
            history = []
            now = datetime.now()
            for i in range(months):
                month_num = now.month - i
                year = now.year
                if month_num <= 0:
                    month_num += 12
                    year -= 1
                month_date = datetime(year, month_num, 1)
                payslip = await _compute_payslip(emp, month_date.strftime("%B"), year)
                history.append({
                    "month": payslip["month"], "year": payslip["year"],
                    "gross": payslip["gross_salary"], "net": payslip["net_salary"],
                    "payment_date": payslip["payment_date"]
                })
            return json.dumps({"employee_id": emp["employee_id"], "history": history})

        elif tool_name == "calculate_take_home":
            gross   = tool_args["gross_salary"]
            tax     = gross * tool_args.get("tax_rate",  0.20)
            cpf     = gross * tool_args.get("cpf_rate",  0.20)
            ins     = tool_args.get("insurance", 200)
            total   = tax + cpf + ins
            net     = gross - total
            return json.dumps({
                "gross_salary": gross,
                "deductions": {"income_tax": tax, "cpf": cpf, "insurance": ins, "total": total},
                "net_salary": net,
                "currency": "SGD"
            })

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        logger.error(f"❌ Tool {tool_name} failed: {str(e)}")
        return json.dumps({"error": str(e)})

# ─────────────────────────────────────────────
# Seed Data
# ─────────────────────────────────────────────
SEED_EMPLOYEES = [
    {"employee_id": "EMP000001", "name": "Admin User", "email": "admin@example.com",
     "department": "Administration", "position": "Administrator",
     "monthly_salary": 8000, "annual_salary": 96000, "currency": "SGD",
     "join_date": "2020-01-15", "tax_rate": 0.20, "cpf_rate": 0.20, "insurance": 200},
    {"employee_id": "EMP000002", "name": "John Doe", "email": "john@example.com",
     "department": "Engineering", "position": "Senior Developer",
     "monthly_salary": 7500, "annual_salary": 90000, "currency": "SGD",
     "join_date": "2021-03-10", "tax_rate": 0.18, "cpf_rate": 0.20, "insurance": 200},
]

@app.on_event("startup")
async def startup_event():
    global mongo_client, db
    logger.info("🚀 Payroll Agent v2 Starting (with tool calling)")
    try:
        mongo_client = AsyncIOMotorClient(MONGODB_URL)
        db = mongo_client[DB_NAME]
        await mongo_client.admin.command("ping")
        logger.info("✅ MongoDB connected")
        if await db.employees.count_documents({}) == 0:
            await db.employees.insert_many(SEED_EMPLOYEES)
            logger.info("🌱 Seeded employees")
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
    return {"status": "healthy", "service": "payroll-agent", "version": "2.0.0",
            "openai_status": "configured" if OPENAI_API_KEY else "missing",
            "mongodb_status": mongo_status, "mode": "agentic-tool-calling"}

# ─────────────────────────────────────────────
# AI Query Endpoint — Agentic Loop
# ─────────────────────────────────────────────
@app.post("/api/payroll/query", response_model=PayrollQueryResponse)
async def query_payroll(request: PayrollQueryRequest):
    try:
        logger.info(f"📥 Payroll query: {request.query}")
        if not client:
            raise HTTPException(status_code=500, detail="OpenAI not configured")
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        conv_id = request.conversation_id or str(uuid.uuid4())

        # ── Strip coordinator context + guardrail check ───────────────────────
        original_query = request.query
        if CONTEXT_MARKER in request.query:
            original_query = request.query.split(CONTEXT_MARKER)[0].strip()

        if any(kw in original_query.lower() for kw in PAYROLL_SENSITIVE_KEYWORDS):
            logger.warning(f"🚨 Sensitive payroll query: {original_query}")
            await log_message(conv_id, "user",      request.query,              request.employee_id, flagged=True)
            await log_message(conv_id, "assistant", PAYROLL_ESCALATION_RESPONSE, request.employee_id, flagged=True)
            return PayrollQueryResponse(answer=PAYROLL_ESCALATION_RESPONSE,
                                        data=None, conversation_id=conv_id, tools_used=[])

        # ── Build messages ────────────────────────────────────────────────────
        messages = [{"role": "system", "content": PAYROLL_SYSTEM_PROMPT}]

        if request.employee_id:
            messages.append({"role": "system", "content":
                f"The employee making this request has ID: {request.employee_id}. "
                f"Only retrieve data for this employee ID unless explicitly told otherwise."})

        history = await get_conversation_history(conv_id, limit=10)
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["message"]})
        messages.append({"role": "user", "content": request.query})

        # ── Genuine ReAct loop ────────────────────────────────────────────────
        employee_data = None
        result = await run_react_loop(
            openai_client=client,
            messages=messages,
            tools=PAYROLL_TOOLS,
            tool_executor=execute_tool,
            service_name="Payroll",
            max_iterations=8,
        )
        answer     = result["answer"]
        tools_used = result["tools_used"]
        logger.info(
            f"✅ Payroll ReAct complete — {result['iterations']} iteration(s), "
            f"tools: {tools_used}, thoughts logged: {len(result['thoughts'])}"
        )
        await log_message(conv_id, "user",      request.query, request.employee_id)
        await log_message(conv_id, "assistant", answer,        request.employee_id)
        return PayrollQueryResponse(answer=answer, data=employee_data,
                                    conversation_id=conv_id, tools_used=tools_used)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Payroll error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────
# Supporting Endpoints
# ─────────────────────────────────────────────
@app.get("/api/payroll/payslip/{employee_id}")
async def get_payslip_endpoint(employee_id: str, month: str = None, year: int = None):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    emp = await db.employees.find_one({"employee_id": employee_id})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return await _compute_payslip(emp, month, year)

@app.get("/api/payroll/history/{employee_id}")
async def get_salary_history(employee_id: str, months: int = 6):
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
        payslip = await _compute_payslip(emp, month_date.strftime("%B"), year)
        history.append({"month": payslip["month"], "year": payslip["year"],
                         "gross": payslip["gross_salary"], "net": payslip["net_salary"]})
    return {"employee_id": employee_id, "employee_name": emp["name"], "history": history}

@app.get("/api/payroll/history/chat")
async def get_chat_history(employee_id: str, limit: int = 50):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor = db.chat_history.find(
        {"employee_id": employee_id, "service": "payroll"}, sort=[("timestamp", -1)]
    ).limit(limit)
    history = await cursor.to_list(length=limit)
    return {"employee_id": employee_id, "history": [serialize_doc(h) for h in history]}

@app.get("/api/payroll/history/chat/{conversation_id}")
async def get_conversation(conversation_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor = db.chat_history.find({"conversation_id": conversation_id}, sort=[("timestamp", 1)])
    messages = await cursor.to_list(length=200)
    return {"conversation_id": conversation_id, "messages": [serialize_doc(m) for m in messages]}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8003)))