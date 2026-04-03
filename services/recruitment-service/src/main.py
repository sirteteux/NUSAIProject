"""
Recruitment Agent - AI Agent with tool calling.
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

app = FastAPI(title="Recruitment Agent", description="Hiring AI Agent with tool calling", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client         = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
MONGODB_URL    = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
DB_NAME        = os.getenv("DB_NAME", "recruitment_db")
mongo_client   = None
db             = None

CONTEXT_MARKER = "[Prior conversation context:"

class RecruitmentQueryRequest(BaseModel):
    query: str
    context: Optional[str] = None
    conversation_id: Optional[str] = None

class RecruitmentQueryResponse(BaseModel):
    answer: str
    data: Optional[Dict] = None
    conversation_id: str
    tools_used: List[str] = []

RECRUITMENT_SENSITIVE_KEYWORDS = [
    "other candidate", "reject candidate", "blacklist", "discriminate",
    "gender", "nationality", "religion", "guarantee salary",
    "lawsuit", "unfair hiring", "override", "ignore instructions",
]
RECRUITMENT_ESCALATION_RESPONSE = (
    "This query involves a sensitive recruitment matter that requires direct HR support. "
    "Please contact hr@company.com or call +65 6123 4567."
)

_RECRUITMENT_SYSTEM_PROMPT_BASE = """You are a Recruitment AI Agent for ResourcefulAI. You have tools to look up real job data.

Use tools to retrieve accurate job information before answering. You can:
- Search for open positions by department or location
- Get detailed job requirements
- Check how many open positions exist
- Create new job postings (HR only)

GUARDRAILS:
- Do not disclose candidate data or application statuses
- Do not make discriminatory remarks about candidates
- Do not commit to salary offers without HR approval
- Provide fair, accurate information to all enquirers"""

# Wrap with ReAct instruction
RECRUITMENT_SYSTEM_PROMPT = build_react_system_prompt(_RECRUITMENT_SYSTEM_PROMPT_BASE)

# ─────────────────────────────────────────────
# Tool Definitions
# ─────────────────────────────────────────────
RECRUITMENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_job_openings",
            "description": "Search for open job positions, optionally filtered by department or location. Returns a list of matching jobs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {"type": "string", "description": "Filter by department name (optional)"},
                    "location":   {"type": "string", "description": "Filter by location (optional)"},
                    "status":     {"type": "string", "enum": ["open", "closed", "all"], "description": "Filter by job status (default: open)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_details",
            "description": "Get full details of a specific job opening including description, required skills, salary range, and experience requirements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The MongoDB job ID"}
                },
                "required": ["job_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recruitment_stats",
            "description": "Get summary statistics: total open positions, breakdown by department, and recently posted jobs.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_job_posting",
            "description": "Create a new job posting. This is an HR-only action.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title":        {"type": "string"},
                    "department":   {"type": "string"},
                    "location":     {"type": "string"},
                    "type":         {"type": "string", "enum": ["Full-time", "Part-time", "Contract"]},
                    "experience":   {"type": "string", "description": "e.g. '3+ years'"},
                    "skills":       {"type": "array", "items": {"type": "string"}},
                    "description":  {"type": "string"},
                    "salary_range": {"type": "string", "description": "e.g. 'SGD 5,000 - 7,000'"}
                },
                "required": ["title", "department", "location", "type", "experience", "skills", "description", "salary_range"]
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

async def log_message(conv_id, role, message, user_id=None, flagged=False):
    if db is None:
        return
    try:
        await db.chat_history.insert_one({
            "conversation_id": conv_id, "service": "recruitment",
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

# ─────────────────────────────────────────────
# Tool Executor
# ─────────────────────────────────────────────
async def execute_tool(tool_name: str, tool_args: dict) -> str:
    try:
        if tool_name == "search_job_openings":
            query_filter = {}
            status = tool_args.get("status", "open")
            if status != "all":
                query_filter["status"] = status
            if tool_args.get("department"):
                query_filter["department"] = {"$regex": tool_args["department"], "$options": "i"}
            if tool_args.get("location"):
                query_filter["location"] = {"$regex": tool_args["location"], "$options": "i"}

            cursor = db.job_openings.find(query_filter)
            jobs   = await cursor.to_list(length=50)
            jobs   = [serialize_doc(j) for j in jobs]
            return json.dumps({"total": len(jobs), "jobs": jobs})

        elif tool_name == "get_job_details":
            try:
                oid = ObjectId(tool_args["job_id"])
            except Exception:
                return json.dumps({"error": "Invalid job ID format"})
            job = await db.job_openings.find_one({"_id": oid})
            if not job:
                return json.dumps({"error": "Job not found"})
            return json.dumps(serialize_doc(job))

        elif tool_name == "get_recruitment_stats":
            total     = await db.job_openings.count_documents({"status": "open"})
            pipeline  = [
                {"$match": {"status": "open"}},
                {"$group": {"_id": "$department", "count": {"$sum": 1}}}
            ]
            by_dept   = await db.job_openings.aggregate(pipeline).to_list(length=20)
            recent    = await db.job_openings.find(
                {"status": "open"}, sort=[("posted", -1)]
            ).limit(3).to_list(length=3)
            return json.dumps({
                "total_open": total,
                "by_department": {d["_id"]: d["count"] for d in by_dept},
                "recently_posted": [{"title": j["title"], "department": j["department"], "posted": j["posted"]}
                                     for j in recent]
            })

        elif tool_name == "create_job_posting":
            job = {
                "title":        tool_args["title"],
                "department":   tool_args["department"],
                "location":     tool_args["location"],
                "type":         tool_args["type"],
                "experience":   tool_args["experience"],
                "skills":       tool_args["skills"],
                "description":  tool_args["description"],
                "salary_range": tool_args["salary_range"],
                "status":       "open",
                "posted":       datetime.now().strftime("%Y-%m-%d")
            }
            result = await db.job_openings.insert_one(job)
            logger.info(f"✅ New job posting created: {tool_args['title']}")
            return json.dumps({"success": True, "job_id": str(result.inserted_id),
                               "message": f"Job posting '{tool_args['title']}' created successfully."})

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        logger.error(f"❌ Tool {tool_name} failed: {str(e)}")
        return json.dumps({"error": str(e)})

# ─────────────────────────────────────────────
# Seed Data
# ─────────────────────────────────────────────
SEED_JOBS = [
    {"title": "Senior Software Engineer", "department": "Engineering",
     "location": "Singapore", "type": "Full-time", "experience": "5+ years",
     "skills": ["Python", "React", "AWS", "Docker", "Kubernetes"],
     "description": "Lead backend development team, design scalable systems.",
     "posted": "2025-02-01", "status": "open", "salary_range": "SGD 8,000 - 12,000"},
    {"title": "HR Manager", "department": "Human Resources",
     "location": "Singapore", "type": "Full-time", "experience": "3+ years",
     "skills": ["HR Management", "Recruitment", "Employee Relations"],
     "description": "Lead HR department, drive talent acquisition.",
     "posted": "2025-01-28", "status": "open", "salary_range": "SGD 6,000 - 8,000"},
    {"title": "Marketing Specialist", "department": "Marketing",
     "location": "Remote", "type": "Full-time", "experience": "2+ years",
     "skills": ["Digital Marketing", "SEO", "Content Creation"],
     "description": "Drive digital marketing campaigns.",
     "posted": "2025-02-05", "status": "open", "salary_range": "SGD 4,500 - 6,500"},
    {"title": "Data Scientist", "department": "Analytics",
     "location": "Singapore", "type": "Full-time", "experience": "3+ years",
     "skills": ["Python", "Machine Learning", "SQL", "TensorFlow"],
     "description": "Build ML models, create data pipelines.",
     "posted": "2025-02-03", "status": "open", "salary_range": "SGD 7,000 - 10,000"},
]

@app.on_event("startup")
async def startup_event():
    global mongo_client, db
    logger.info("🚀 Recruitment Agent v2 Starting (with tool calling)")
    try:
        mongo_client = AsyncIOMotorClient(MONGODB_URL)
        db = mongo_client[DB_NAME]
        await mongo_client.admin.command("ping")
        logger.info("✅ MongoDB connected")
        if await db.job_openings.count_documents({}) == 0:
            await db.job_openings.insert_many(SEED_JOBS)
            logger.info(f"🌱 Seeded {len(SEED_JOBS)} job openings")
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
    return {"status": "healthy", "service": "recruitment-agent", "version": "2.0.0",
            "openai_status": "configured" if OPENAI_API_KEY else "missing",
            "mongodb_status": mongo_status, "mode": "agentic-tool-calling"}

# ─────────────────────────────────────────────
# AI Query Endpoint — Agentic Loop
# ─────────────────────────────────────────────
@app.post("/api/recruitment/query", response_model=RecruitmentQueryResponse)
async def query_recruitment(request: RecruitmentQueryRequest):
    try:
        logger.info(f"📥 Recruitment query: {request.query}")
        if not client:
            raise HTTPException(status_code=500, detail="OpenAI not configured")
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        conv_id = request.conversation_id or str(uuid.uuid4())

        original_query = request.query
        if CONTEXT_MARKER in request.query:
            original_query = request.query.split(CONTEXT_MARKER)[0].strip()

        if any(kw in original_query.lower() for kw in RECRUITMENT_SENSITIVE_KEYWORDS):
            logger.warning(f"🚨 Sensitive recruitment query: {original_query}")
            await log_message(conv_id, "user",      request.query,                    None, flagged=True)
            await log_message(conv_id, "assistant", RECRUITMENT_ESCALATION_RESPONSE,  None, flagged=True)
            return RecruitmentQueryResponse(answer=RECRUITMENT_ESCALATION_RESPONSE,
                                            data=None, conversation_id=conv_id, tools_used=[])

        messages = [{"role": "system", "content": RECRUITMENT_SYSTEM_PROMPT}]
        if request.context:
            messages.append({"role": "system", "content": f"Additional context: {request.context}"})

        history = await get_conversation_history(conv_id, limit=10)
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["message"]})
        messages.append({"role": "user", "content": request.query})

        # ── Genuine ReAct loop ────────────────────────────────────────────
        job_data       = None
        result = await run_react_loop(
            openai_client=client,
            messages=messages,
            tools=RECRUITMENT_TOOLS,
            tool_executor=execute_tool,
            service_name="Recruitment",
            max_iterations=8,
        )
        answer     = result["answer"]
        tools_used = result["tools_used"]
        logger.info(
            f"✅ Recruitment ReAct complete — {result['iterations']} iteration(s), "
            f"tools: {tools_used}, thoughts: {len(result['thoughts'])}"
        )
        await log_message(conv_id, "user",      request.query, None)
        await log_message(conv_id, "assistant", answer,        None)
        return RecruitmentQueryResponse(answer=answer, data=job_data,
                                            conversation_id=conv_id, tools_used=tools_used)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Recruitment error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/recruitment/openings")
async def get_openings(department: Optional[str] = None, location: Optional[str] = None):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    query_filter = {}
    if department:
        query_filter["department"] = {"$regex": department, "$options": "i"}
    if location:
        query_filter["location"] = {"$regex": location, "$options": "i"}
    cursor   = db.job_openings.find(query_filter)
    openings = await cursor.to_list(length=100)
    return {"openings": [serialize_doc(j) for j in openings], "total": len(openings)}

@app.get("/api/recruitment/opening/{job_id}")
async def get_opening(job_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    try:
        oid = ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job ID")
    job = await db.job_openings.find_one({"_id": oid})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return serialize_doc(job)

@app.get("/api/recruitment/history/chat")
async def get_chat_history(limit: int = 50):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor = db.chat_history.find({"service": "recruitment"}, sort=[("timestamp", -1)]).limit(limit)
    history = await cursor.to_list(length=limit)
    return {"history": [serialize_doc(h) for h in history]}

@app.get("/api/recruitment/history/chat/{conversation_id}")
async def get_conversation(conversation_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor = db.chat_history.find({"conversation_id": conversation_id}, sort=[("timestamp", 1)])
    messages = await cursor.to_list(length=200)
    return {"conversation_id": conversation_id, "messages": [serialize_doc(m) for m in messages]}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8005)))