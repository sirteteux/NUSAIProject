"""
Performance Agent - AI-Powered Performance Management
Handles KPI tracking, goal setting, performance reviews
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
    title="Performance Agent",
    description="AI-Powered Performance Management",
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
DB_NAME = os.getenv("DB_NAME", "performance_db")

mongo_client: AsyncIOMotorClient = None
db = None

# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────
class PerformanceQueryRequest(BaseModel):
    query: str
    employee_id: Optional[str] = None
    conversation_id: Optional[str] = None      # ← thread identifier

class PerformanceQueryResponse(BaseModel):
    answer: str
    data: Optional[Dict] = None
    conversation_id: str                        # ← returned so frontend can reuse it

class GoalCreateRequest(BaseModel):
    employee_id: str
    title: str
    description: str
    target_date: str
    kpis: Optional[List[str]] = None

class GoalUpdateRequest(BaseModel):
    goal_id: str
    progress: int
    notes: Optional[str] = None

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
            "service": "performance",
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
SEED_GOALS = [
    {
        "employee_id": "EMP000001",
        "title": "Complete Q1 Project Deliverables",
        "description": "Deliver all planned features for Q1 release",
        "progress": 75,
        "target_date": "2025-03-31",
        "status": "on-track",
        "kpis": ["Code quality", "On-time delivery", "Bug reduction"],
        "created": "2025-01-01"
    },
    {
        "employee_id": "EMP000001",
        "title": "Improve Code Review Turnaround",
        "description": "Reduce average code review time to under 24 hours",
        "progress": 60,
        "target_date": "2025-02-28",
        "status": "on-track",
        "kpis": ["Response time", "Review quality"],
        "created": "2025-01-15"
    },
    {
        "employee_id": "EMP000001",
        "title": "Mentor Junior Developers",
        "description": "Provide weekly mentoring sessions to 2 junior developers",
        "progress": 40,
        "target_date": "2025-06-30",
        "status": "needs-attention",
        "kpis": ["Mentee progress", "Knowledge transfer"],
        "created": "2025-01-01"
    }
]

SEED_REVIEWS = [
    {
        "employee_id": "EMP000001",
        "period": "H2 2024",
        "rating": 4.5,
        "date": "2024-12-15",
        "reviewer": "Jane Smith (Manager)",
        "strengths": ["Technical expertise", "Team collaboration", "Problem solving"],
        "improvements": ["Time management", "Documentation"],
        "summary": "Excellent performance with strong technical contributions."
    }
]

SYSTEM_PROMPT = """You are a professional Performance Management AI Assistant. You help with:
- Goal setting and OKR frameworks
- Performance reviews and feedback
- KPI tracking and analysis
- Career development planning
- Performance improvement plans

Company Performance Framework:
- Review Cycle: Semi-annual (H1, H2)
- Rating Scale: 1-5 (1=Needs Improvement, 5=Exceptional)
- Goal Framework: SMART goals (Specific, Measurable, Achievable, Relevant, Time-bound)
- Development: 10% time for learning
- Feedback Culture: Continuous feedback encouraged

Be constructive, data-driven, and growth-focused in all assessments.

GUARDRAILS — NEVER DO THESE:
DO NOT disclose another employee's performance rating, goals, or review details
DO NOT confirm or deny promotion or termination decisions
DO NOT provide legal advice on unfair dismissal or employment disputes
DO NOT manipulate or fabricate performance ratings or review scores
DO NOT handle harassment or discrimination complaints — escalate to HR
"""

# Queries matching these keywords are short-circuited before hitting OpenAI.
# They are logged with flagged=True for HR audit and return a static escalation response.
PERFORMANCE_SENSITIVE_KEYWORDS = [
    "other employee",        # attempting to access another person's data
    "everyone's rating",     # bulk performance data disclosure
    "rating of",             # fishing for another person's score
    "fire",                  # termination discussion
    "terminate",             # termination discussion
    "dismiss",               # unfair dismissal queries
    "promote me",            # demanding a promotion decision
    "force promotion",       # attempting to bypass process
    "change my rating",      # attempting to manipulate review scores
    "increase my score",     # attempting to manipulate KPI data
    "harassment",            # workplace complaint — escalate to HR
    "discrimination",        # legal complaint — escalate to HR
    "lawsuit",               # legal dispute
    "override",              # prompt injection attempt
    "ignore instructions",   # jailbreak attempt
]

PERFORMANCE_ESCALATION_RESPONSE = (
    "This query involves a sensitive performance matter that requires direct HR support. "
    "For promotion decisions, termination concerns, or workplace disputes, please contact "
    "hr@company.com or call +65 6123 4567 to speak with an HR representative."
)

# ─────────────────────────────────────────────
# Startup / Shutdown
# ─────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    global mongo_client, db

    logger.info("=" * 50)
    logger.info("🚀 Performance Agent Starting Up")
    logger.info("=" * 50)
    logger.info(f"OpenAI API:  {'✅ Configured' if OPENAI_API_KEY else '❌ Missing'}")
    logger.info(f"MongoDB URL: {MONGODB_URL}")

    try:
        mongo_client = AsyncIOMotorClient(MONGODB_URL)
        db = mongo_client[DB_NAME]
        await mongo_client.admin.command("ping")
        logger.info("✅ MongoDB connected successfully")

        if await db.goals.count_documents({}) == 0:
            await db.goals.insert_many(SEED_GOALS)
            logger.info(f"🌱 Seeded {len(SEED_GOALS)} goals")

        if await db.performance_reviews.count_documents({}) == 0:
            await db.performance_reviews.insert_many(SEED_REVIEWS)
            logger.info(f"🌱 Seeded {len(SEED_REVIEWS)} performance reviews")

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
        "service": "performance-agent",
        "version": "1.0.0",
        "openai_status": "configured" if OPENAI_API_KEY else "missing",
        "mongodb_status": mongo_status
    }

# ─────────────────────────────────────────────
# AI Query — Level 1 Conversational Memory
# ─────────────────────────────────────────────
@app.post("/api/performance/query", response_model=PerformanceQueryResponse)
async def query_performance(request: PerformanceQueryRequest):
    try:
        logger.info(f"📥 Performance query: {request.query}")

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
        if any(kw in query_lower for kw in PERFORMANCE_SENSITIVE_KEYWORDS):
            logger.warning(f"🚨 Sensitive performance query intercepted: {original_query}")
            await log_message(conv_id, "user",      request.query,                   request.employee_id, flagged=True)
            await log_message(conv_id, "assistant", PERFORMANCE_ESCALATION_RESPONSE, request.employee_id, flagged=True)
            return PerformanceQueryResponse(
                answer=PERFORMANCE_ESCALATION_RESPONSE,
                data=None,
                conversation_id=conv_id
            )

        # ── Build employee performance context from DB ──
        employee_context = ""
        employee_data = None

        if request.employee_id:
            goals_cursor = db.goals.find({"employee_id": request.employee_id})
            goals = await goals_cursor.to_list(length=100)

            reviews_cursor = db.performance_reviews.find({"employee_id": request.employee_id})
            reviews = await reviews_cursor.to_list(length=10)

            if goals:
                avg_progress = sum(g["progress"] for g in goals) / len(goals)
                latest_rating = reviews[0]["rating"] if reviews else None

                employee_data = {
                    "active_goals": len(goals),
                    "avg_progress": round(avg_progress, 1),
                    "recent_rating": latest_rating
                }

                employee_context = f"""
Employee Performance Data:
- Active Goals: {len(goals)}
- Average Goal Progress: {avg_progress:.1f}%
- Latest Review Rating: {latest_rating}/5.0
- Goals Status: {sum(1 for g in goals if g['status'] == 'on-track')} on-track, {sum(1 for g in goals if g['status'] == 'needs-attention')} need attention
"""

        # ── Start messages with system prompt ──
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

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
        logger.info("✅ Generated performance response")

        # ── Persist both sides of the exchange ──
        await log_message(conv_id, "user",      request.query, request.employee_id)
        await log_message(conv_id, "assistant", answer,        request.employee_id)

        return PerformanceQueryResponse(
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
# Goals
# ─────────────────────────────────────────────
@app.get("/api/performance/goals")
async def get_goals(employee_id: str):
    try:
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        cursor = db.goals.find({"employee_id": employee_id})
        goals = await cursor.to_list(length=100)
        goals = [serialize_doc(g) for g in goals]

        avg_progress = sum(g["progress"] for g in goals) / len(goals) if goals else 0

        return {
            "employee_id": employee_id,
            "goals": goals,
            "total": len(goals),
            "avg_progress": round(avg_progress, 1)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/performance/goal/create")
async def create_goal(request: GoalCreateRequest):
    try:
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        goal = {
            "employee_id": request.employee_id,
            "title": request.title,
            "description": request.description,
            "progress": 0,
            "target_date": request.target_date,
            "status": "not-started",
            "kpis": request.kpis or [],
            "created": datetime.now().isoformat()
        }

        result = await db.goals.insert_one(goal)
        goal["id"] = str(result.inserted_id)
        del goal["_id"]

        logger.info(f"✅ Goal created for {request.employee_id}")
        return {"goal": goal, "message": "Goal created successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/performance/goal/update")
async def update_goal(request: GoalUpdateRequest):
    try:
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        try:
            oid = ObjectId(request.goal_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid goal ID format")

        progress = min(100, max(0, request.progress))
        status = "on-track" if progress >= 80 else "in-progress" if progress >= 50 else "needs-attention"

        update_data: Dict = {"$set": {"progress": progress, "status": status}}

        if request.notes:
            update_data["$push"] = {
                "notes": {"date": datetime.now().isoformat(), "note": request.notes}
            }

        await db.goals.update_one({"_id": oid}, update_data)

        updated = await db.goals.find_one({"_id": oid})
        if not updated:
            raise HTTPException(status_code=404, detail="Goal not found")

        logger.info(f"✅ Goal {request.goal_id} updated to {progress}%")
        return {"goal": serialize_doc(updated), "message": "Goal updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────
# Performance Reviews
# ─────────────────────────────────────────────
@app.get("/api/performance/reviews")
async def get_reviews(employee_id: str):
    try:
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        cursor = db.performance_reviews.find({"employee_id": employee_id})
        reviews = await cursor.to_list(length=50)
        reviews = [serialize_doc(r) for r in reviews]

        avg_rating = sum(r["rating"] for r in reviews) / len(reviews) if reviews else None

        return {
            "employee_id": employee_id,
            "reviews": reviews,
            "total": len(reviews),
            "avg_rating": round(avg_rating, 2) if avg_rating else None
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────
# Chat History Endpoints
# ─────────────────────────────────────────────
@app.get("/api/performance/history/chat")
async def get_chat_history(employee_id: str, limit: int = 50):
    """All recent chat messages for an employee."""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    cursor = db.chat_history.find(
        {"employee_id": employee_id, "service": "performance"},
        sort=[("timestamp", -1)]
    ).limit(limit)

    history = await cursor.to_list(length=limit)
    return {"employee_id": employee_id, "history": [serialize_doc(h) for h in history]}

@app.get("/api/performance/history/chat/{conversation_id}")
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
    port = int(os.getenv("PORT", 8006))
    uvicorn.run(app, host="0.0.0.0", port=port)