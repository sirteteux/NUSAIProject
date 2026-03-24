"""
FAQ Agent - HR Knowledge Base Assistant
Answers common HR questions using OpenAI
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import os
from dotenv import load_dotenv
import logging
from openai import OpenAI
import uvicorn
import traceback
import uuid
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="FAQ Agent",
    description="HR Knowledge Base Assistant",
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
    logger.error("❌ OPENAI_API_KEY not found in environment variables!")
else:
    logger.info(f"✅ OpenAI API Key found (starts with: {OPENAI_API_KEY[:20]}...)")

try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info("✅ OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"❌ Failed to initialize OpenAI client: {str(e)}")
    client = None

# ─────────────────────────────────────────────
# MongoDB Setup
# ─────────────────────────────────────────────
MONGODB_URL = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "faq_db")

mongo_client: AsyncIOMotorClient = None
db = None

# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────
class QuestionRequest(BaseModel):
    question: str
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None      # ← thread identifier

class QuestionResponse(BaseModel):
    answer: str
    question: str
    confidence: float = 0.95
    conversation_id: str                        # ← returned so frontend can reuse it

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
            "service": "faq",
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
SEED_POPULAR_QUESTIONS = [
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

SENSITIVE_KEYWORDS = ['salary', 'fire', 'terminate', 'lawsuit', 'harassment', 'discrimination']

SYSTEM_PROMPT = """You are ResourcefulAI's HR Knowledge Assistant - a helpful, professional virtual assistant for employees.

## YOUR ROLE & CAPABILITIES
You help employees with:
- Company policies and procedures
- Working hours, schedules, and remote work policies
- Benefits, perks, and compensation information
- Leave policies (annual, sick, personal, maternity/paternity)
- Dress code and workplace conduct
- Office locations, facilities, and amenities
- Onboarding, training, and career development
- General HR inquiries and employee support

## COMPANY INFORMATION
**Company name:** ResourcefulAI
**Working Hours:** Monday-Friday, 9 AM - 6 PM (SGT)
**Dress Code:** Business casual (smart casual on Fridays)
**Main Office:** 123 Business Street, Singapore 018956
**HR Contact:** hr@company.com | +65 6123 4567
**Leave Entitlements:**
- Annual Leave: 18 days per year
- Sick Leave: 14 days per year (medical certificate required for 2+ days)
- Personal Leave: 3 days per year
**Medical Benefits:** Full coverage for employees, 50% for dependents

## RESPONSE GUIDELINES
1. Be Professional & Friendly
2. Be Concise (2-4 sentences for simple queries)
3. Be Accurate — only use info from above
4. If unsure, direct them to HR at hr@company.com

## GUARDRAILS — NEVER DO THESE:
DO NOT provide medical, legal, or financial advice
DO NOT discuss other employees' personal information or salaries
DO NOT make promises on behalf of HR or management
DO NOT handle harassment/discrimination complaints (escalate to HR)
"""

# ─────────────────────────────────────────────
# Startup / Shutdown
# ─────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    global mongo_client, db

    logger.info("=" * 50)
    logger.info("🚀 FAQ Agent Starting Up")
    logger.info("=" * 50)
    logger.info(f"OpenAI API Key: {'✅ Configured' if OPENAI_API_KEY else '❌ Missing'}")
    logger.info(f"MongoDB URL:    {MONGODB_URL}")

    try:
        mongo_client = AsyncIOMotorClient(MONGODB_URL)
        db = mongo_client[DB_NAME]
        await mongo_client.admin.command("ping")
        logger.info("✅ MongoDB connected successfully")

        if await db.popular_questions.count_documents({}) == 0:
            await db.popular_questions.insert_many(SEED_POPULAR_QUESTIONS)
            logger.info(f"🌱 Seeded {len(SEED_POPULAR_QUESTIONS)} popular questions")

        if await db.categories.count_documents({}) == 0:
            await db.categories.insert_many(SEED_CATEGORIES)
            logger.info(f"🌱 Seeded {len(SEED_CATEGORIES)} FAQ categories")

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
        "service": "faq-agent",
        "version": "1.0.0",
        "openai_api_key": "configured" if OPENAI_API_KEY else "missing",
        "openai_client": "initialized" if client else "failed",
        "mongodb_status": mongo_status
    }

# ─────────────────────────────────────────────
# AI Ask Endpoint — Level 1 Conversational Memory
# ─────────────────────────────────────────────
@app.post("/api/faq/ask", response_model=QuestionResponse)
async def ask_question(request: QuestionRequest):
    try:
        logger.info(f"📥 Received question: {request.question}")

        if not OPENAI_API_KEY:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")
        if not client:
            raise HTTPException(status_code=500, detail="OpenAI client initialization failed")

        # Use provided conversation_id or generate a new one
        conv_id = request.conversation_id or str(uuid.uuid4())

        # ── Strip coordinator-appended context before guardrail check ─────────
        # The coordinator enriches queries with prior conversation history by
        # appending a [Prior conversation context: ...] block. That block may
        # contain sensitive words (e.g. "salary" from a previous payroll turn)
        # that would incorrectly trigger the guardrail on an innocent question.
        # We extract only the original user question — the text before the marker.
        CONTEXT_MARKER = "[Prior conversation context:"
        original_question = request.question
        if CONTEXT_MARKER in request.question:
            original_question = request.question.split(CONTEXT_MARKER)[0].strip()

        # ── Sensitive keyword check — only on the original question ──────────
        if any(kw in original_question.lower() for kw in SENSITIVE_KEYWORDS):
            logger.warning(f"Sensitive query detected: {original_question}")
            sensitive_answer = (
                "This seems like a sensitive matter that requires direct HR support. "
                "Please contact hr@company.com or call +65 6123 4567."
            )
            # Log it (flagged=True for HR audit trail)
            await log_message(conv_id, "user",      request.question,  request.user_id, flagged=True)
            await log_message(conv_id, "assistant", sensitive_answer,  request.user_id, flagged=True)

            return QuestionResponse(
                answer=sensitive_answer,
                question=request.question,
                confidence=1.0,
                conversation_id=conv_id
            )

        # ── Start messages with system prompt ──
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # ── Inject conversation history for Level 1 memory ──
        history = await get_conversation_history(conv_id, limit=10)
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["message"]})

        logger.info(f"💬 Injecting {len(history)} previous messages into context")

        # ── Append current user message ──
        messages.append({"role": "user", "content": request.question})

        # ── Call OpenAI ──
        logger.info("🔄 Calling OpenAI API...")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )

        answer = response.choices[0].message.content.strip()
        logger.info(f"✅ Got response from OpenAI: {answer[:100]}...")

        # ── Persist both sides of the exchange ──
        await log_message(conv_id, "user",      request.question, request.user_id)
        await log_message(conv_id, "assistant", answer,           request.user_id)

        return QuestionResponse(
            answer=answer,
            question=request.question,
            confidence=0.95,
            conversation_id=conv_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error processing question: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

        error_message = str(e)
        if "invalid_api_key" in error_message or "Incorrect API key" in error_message:
            detail = "Invalid OpenAI API key. Please check your API key in .env file"
        elif "insufficient_quota" in error_message:
            detail = "OpenAI API quota exceeded. Please check your OpenAI account billing"
        elif "rate_limit" in error_message:
            detail = "OpenAI API rate limit exceeded. Please try again in a moment"
        else:
            detail = f"Error: {error_message}"

        raise HTTPException(status_code=500, detail=detail)

# ─────────────────────────────────────────────
# Categories & Popular Questions (from MongoDB)
# ─────────────────────────────────────────────
@app.get("/api/faq/categories")
async def get_categories():
    try:
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        cursor = db.categories.find({}, {"_id": 0})
        categories = await cursor.to_list(length=50)
        return {"categories": categories}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/faq/popular")
async def get_popular_questions():
    try:
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        cursor = db.popular_questions.find(
            {}, {"_id": 0, "question": 1}
        ).sort("views", -1).limit(10)

        docs = await cursor.to_list(length=10)
        return {"questions": [d["question"] for d in docs]}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────
# Chat History Endpoints
# ─────────────────────────────────────────────
@app.get("/api/faq/history/chat")
async def get_chat_history(user_id: str, limit: int = 50):
    """All recent chat messages for a user."""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    cursor = db.chat_history.find(
        {"user_id": user_id, "service": "faq"},
        sort=[("timestamp", -1)]
    ).limit(limit)

    history = await cursor.to_list(length=limit)
    return {"user_id": user_id, "history": [serialize_doc(h) for h in history]}

@app.get("/api/faq/history/chat/{conversation_id}")
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
    port = int(os.getenv("PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port)