"""
Recruitment Agent - AI-Powered Hiring Assistant
Handles job postings, candidate screening, resume analysis
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
    title="Recruitment Agent",
    description="AI-Powered Hiring Assistant",
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
DB_NAME = os.getenv("DB_NAME", "recruitment_db")

mongo_client: AsyncIOMotorClient = None
db = None

# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────
class RecruitmentQueryRequest(BaseModel):
    query: str
    context: Optional[str] = None
    conversation_id: Optional[str] = None      # ← thread identifier

class RecruitmentQueryResponse(BaseModel):
    answer: str
    data: Optional[Dict] = None
    conversation_id: str                        # ← returned so frontend can reuse it

class JobOpening(BaseModel):
    title: str
    department: str
    location: str
    type: str
    experience: str
    skills: List[str]
    description: str
    salary_range: str
    status: str = "open"
    posted: str = datetime.now().strftime("%Y-%m-%d")

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def serialize_doc(doc: dict) -> dict:
    if doc and "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc

async def log_message(conv_id: str, role: str, message: str, user_id: str = None,
                      flagged: bool = False):
    """Persist a single chat message. Never raises — logging must not break the main flow."""
    if db is None:
        return
    try:
        await db.chat_history.insert_one({
            "conversation_id": conv_id,
            "service": "recruitment",
            "user_id": user_id,
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
SEED_JOB_OPENINGS = [
    {
        "title": "Senior Software Engineer",
        "department": "Engineering",
        "location": "Singapore",
        "type": "Full-time",
        "experience": "5+ years",
        "skills": ["Python", "React", "AWS", "Docker", "Kubernetes"],
        "description": "Lead backend development team, design scalable systems, mentor junior developers.",
        "posted": "2025-02-01",
        "status": "open",
        "salary_range": "SGD 8,000 - 12,000"
    },
    {
        "title": "HR Manager",
        "department": "Human Resources",
        "location": "Singapore",
        "type": "Full-time",
        "experience": "3+ years",
        "skills": ["HR Management", "Recruitment", "Employee Relations", "Labor Law"],
        "description": "Lead HR department, drive talent acquisition, manage employee relations.",
        "posted": "2025-01-28",
        "status": "open",
        "salary_range": "SGD 6,000 - 8,000"
    },
    {
        "title": "Marketing Specialist",
        "department": "Marketing",
        "location": "Remote",
        "type": "Full-time",
        "experience": "2+ years",
        "skills": ["Digital Marketing", "SEO", "Content Creation", "Analytics"],
        "description": "Drive digital marketing campaigns, manage social media, analyze performance.",
        "posted": "2025-02-05",
        "status": "open",
        "salary_range": "SGD 4,500 - 6,500"
    },
    {
        "title": "Data Scientist",
        "department": "Analytics",
        "location": "Singapore",
        "type": "Full-time",
        "experience": "3+ years",
        "skills": ["Python", "Machine Learning", "SQL", "Statistics", "TensorFlow"],
        "description": "Build ML models, create data pipelines, provide business insights.",
        "posted": "2025-02-03",
        "status": "open",
        "salary_range": "SGD 7,000 - 10,000"
    }
]

SYSTEM_PROMPT = """You are a professional Recruitment AI Assistant. You help with:
- Job posting and requirements
- Candidate screening and evaluation
- Interview scheduling
- Recruitment process guidance
- Hiring best practices

Company Recruitment Policies:
- Application review: 3-5 business days
- Interview process: 2-3 rounds (Phone screen, Technical, Final)
- Background checks required for all hires
- Standard notice period: 1 month
- Probation period: 3 months

Be professional, data-driven, and fair in all assessments.

GUARDRAILS — NEVER DO THESE:
DO NOT disclose another candidate's application status, CV, or personal details
DO NOT confirm or deny hiring decisions for specific candidates
DO NOT discriminate or make remarks based on age, gender, nationality, or religion
DO NOT provide salary negotiation advice that commits the company to a figure
DO NOT handle complaints about biased hiring — escalate to HR
"""

# Queries matching these keywords are short-circuited before hitting OpenAI.
# They are logged with flagged=True for HR audit and return a static escalation response.
RECRUITMENT_SENSITIVE_KEYWORDS = [
    "other candidate",       # attempting to access another applicant's data
    "reject candidate",      # attempting to force a hiring decision
    "blacklist",             # discriminatory action request
    "discriminate",          # discrimination concern — escalate to HR
    "age",                   # age-based bias request
    "gender",                # gender-based bias request
    "nationality",           # nationality-based bias request
    "religion",              # religion-based bias request
    "salary of applicant",   # fishing for another candidate's offered salary
    "guarantee salary",      # committing company to a specific offer
    "lawsuit",               # legal dispute
    "bias",                  # hiring bias complaint — escalate to HR
    "unfair hiring",         # complaint requiring HR involvement
    "override",              # prompt injection attempt
    "ignore instructions",   # jailbreak attempt
]

RECRUITMENT_ESCALATION_RESPONSE = (
    "This query involves a sensitive recruitment matter that requires direct HR support. "
    "For hiring decisions, candidate disputes, or discrimination concerns, please contact "
    "hr@company.com or call +65 6123 4567 to speak with an HR representative."
)

# ─────────────────────────────────────────────
# Startup / Shutdown
# ─────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    global mongo_client, db

    logger.info("=" * 50)
    logger.info("🚀 Recruitment Agent Starting Up")
    logger.info("=" * 50)
    logger.info(f"OpenAI API:  {'✅ Configured' if OPENAI_API_KEY else '❌ Missing'}")
    logger.info(f"MongoDB URL: {MONGODB_URL}")

    try:
        mongo_client = AsyncIOMotorClient(MONGODB_URL)
        db = mongo_client[DB_NAME]
        await mongo_client.admin.command("ping")
        logger.info("✅ MongoDB connected successfully")

        if await db.job_openings.count_documents({}) == 0:
            await db.job_openings.insert_many(SEED_JOB_OPENINGS)
            logger.info(f"🌱 Seeded {len(SEED_JOB_OPENINGS)} job openings")
        else:
            count = await db.job_openings.count_documents({})
            logger.info(f"📋 Found {count} existing job openings in MongoDB")

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
        "service": "recruitment-agent",
        "version": "1.0.0",
        "openai_status": "configured" if OPENAI_API_KEY else "missing",
        "mongodb_status": mongo_status
    }

# ─────────────────────────────────────────────
# AI Query — Level 1 Conversational Memory
# ─────────────────────────────────────────────
@app.post("/api/recruitment/query", response_model=RecruitmentQueryResponse)
async def query_recruitment(request: RecruitmentQueryRequest):
    try:
        logger.info(f"📥 Recruitment query: {request.query}")

        if not client:
            raise HTTPException(status_code=500, detail="OpenAI not configured")
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        # Use provided conversation_id or generate a new one
        conv_id = request.conversation_id or str(uuid.uuid4())

        # ── Guardrail: sensitive keyword intercept ──
        query_lower = request.query.lower()
        if any(kw in query_lower for kw in RECRUITMENT_SENSITIVE_KEYWORDS):
            logger.warning(f"🚨 Sensitive recruitment query intercepted: {request.query}")
            await log_message(conv_id, "user",      request.query,                    None, flagged=True)
            await log_message(conv_id, "assistant", RECRUITMENT_ESCALATION_RESPONSE,  None, flagged=True)
            return RecruitmentQueryResponse(
                answer=RECRUITMENT_ESCALATION_RESPONSE,
                data=None,
                conversation_id=conv_id
            )

        # ── Fetch live job openings from MongoDB ──
        cursor = db.job_openings.find({"status": "open"})
        open_jobs = await cursor.to_list(length=100)

        openings_context = f"\nCurrent Open Positions ({len(open_jobs)}):\n"
        for job in open_jobs[:5]:
            openings_context += (
                f"- {job['title']} ({job['department']}) | "
                f"{job['location']} | {job['salary_range']}\n"
            )

        # ── Start messages with system prompt ──
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": openings_context},
        ]

        if request.context:
            messages.append({"role": "system", "content": f"Additional context: {request.context}"})

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
        logger.info("✅ Generated recruitment response")

        # ── Persist both sides of the exchange ──
        await log_message(conv_id, "user",      request.query, None)
        await log_message(conv_id, "assistant", answer,        None)

        return RecruitmentQueryResponse(
            answer=answer,
            data={"open_positions": len(open_jobs)},
            conversation_id=conv_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in query_recruitment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────
# Job Openings Endpoints
# ─────────────────────────────────────────────
@app.get("/api/recruitment/openings")
async def get_openings(department: Optional[str] = None, location: Optional[str] = None):
    try:
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        query_filter: Dict = {}
        if department:
            query_filter["department"] = {"$regex": f"^{department}$", "$options": "i"}
        if location:
            query_filter["location"] = {"$regex": location, "$options": "i"}

        cursor = db.job_openings.find(query_filter)
        openings = await cursor.to_list(length=100)
        openings = [serialize_doc(job) for job in openings]

        return {"openings": openings, "total": len(openings)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in get_openings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/recruitment/opening/{job_id}")
async def get_opening(job_id: str):
    try:
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        try:
            oid = ObjectId(job_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid job ID format")

        job = await db.job_openings.find_one({"_id": oid})
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        return serialize_doc(job)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in get_opening: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/recruitment/openings")
async def create_opening(job: JobOpening):
    try:
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        result = await db.job_openings.insert_one(job.dict())
        logger.info(f"✅ Created new job opening: {job.title}")
        return {"id": str(result.inserted_id), "message": "Job opening created successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in create_opening: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────
# Chat History Endpoints
# ─────────────────────────────────────────────
@app.get("/api/recruitment/history/chat")
async def get_chat_history(limit: int = 50):
    """All recent recruitment chat messages."""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    cursor = db.chat_history.find(
        {"service": "recruitment"},
        sort=[("timestamp", -1)]
    ).limit(limit)

    history = await cursor.to_list(length=limit)
    return {"history": [serialize_doc(h) for h in history]}

@app.get("/api/recruitment/history/chat/{conversation_id}")
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
    port = int(os.getenv("PORT", 8005))
    uvicorn.run(app, host="0.0.0.0", port=port)