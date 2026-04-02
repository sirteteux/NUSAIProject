"""
Performance KPI Agent - AI Agent with tool calling.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
import os, json, uuid, traceback
from dotenv import load_dotenv
import logging
from openai import OpenAI
from datetime import datetime
import uvicorn
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Performance Agent", description="Performance AI Agent with tool calling", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client         = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
MONGODB_URL    = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
DB_NAME        = os.getenv("DB_NAME", "performance_db")
mongo_client   = None
db             = None

CONTEXT_MARKER = "[Prior conversation context:"

class PerformanceQueryRequest(BaseModel):
    query: str
    employee_id: Optional[str] = None
    conversation_id: Optional[str] = None

class PerformanceQueryResponse(BaseModel):
    answer: str
    data: Optional[Dict] = None
    conversation_id: str
    tools_used: List[str] = []

PERFORMANCE_SENSITIVE_KEYWORDS = [
    "other employee", "everyone's rating", "rating of", "fire", "terminate",
    "dismiss", "force promotion", "change my rating", "increase my score",
    "harassment", "discrimination", "lawsuit", "override", "ignore instructions",
]
PERFORMANCE_ESCALATION_RESPONSE = (
    "This query involves a sensitive performance matter requiring direct HR support. "
    "Please contact hr@company.com or call +65 6123 4567."
)

PERFORMANCE_SYSTEM_PROMPT = """You are a professional Performance Management AI Agent for ResourcefulAI — constructive, data-driven, and growth-focused. 
 You have tools to look up and update real performance data.

If the query involves confidential information or restricted topics, do not answer and advise contacting HR.

Always use tools to retrieve accurate data before answering. You can:
- View and create SMART goals
- Update goal progress with notes
- Retrieve performance review history
- Provide development recommendations based on actual data

GUARDRAILS:
- Only access the requesting employee's own data
- Do not manipulate or fabricate ratings
- Do not confirm promotion or termination decisions
- Escalate discrimination/harassment queries to HR"""

# ─────────────────────────────────────────────
# Tool Definitions
# ─────────────────────────────────────────────
PERFORMANCE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_employee_goals",
            "description": "Retrieve all active goals for an employee including progress percentage, status, KPIs, and target dates.",
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
            "name": "get_performance_reviews",
            "description": "Retrieve performance review history for an employee including ratings, strengths, improvements, and reviewer feedback.",
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
            "name": "create_goal",
            "description": "Create a new SMART goal for an employee. Returns the created goal ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id":  {"type": "string"},
                    "title":        {"type": "string", "description": "Short goal title"},
                    "description":  {"type": "string", "description": "Detailed description of the goal"},
                    "target_date":  {"type": "string", "description": "Target completion date YYYY-MM-DD"},
                    "kpis":         {"type": "array", "items": {"type": "string"}, "description": "Key Performance Indicators for this goal"}
                },
                "required": ["employee_id", "title", "description", "target_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_goal_progress",
            "description": "Update the progress percentage of a goal and optionally add a note. Status is auto-calculated: >=80% = on-track, >=50% = in-progress, <50% = needs-attention.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_id":  {"type": "string", "description": "The MongoDB goal ID"},
                    "progress": {"type": "integer", "description": "Progress percentage 0-100"},
                    "note":     {"type": "string", "description": "Optional progress note"}
                },
                "required": ["goal_id", "progress"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_performance_summary",
            "description": "Get a summary of an employee's overall performance: goal count, average progress, latest review rating, and goals needing attention.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {"type": "string"}
                },
                "required": ["employee_id"]
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
            "conversation_id": conv_id, "service": "performance",
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
        if tool_name == "get_employee_goals":
            cursor = db.goals.find({"employee_id": tool_args["employee_id"]})
            goals  = await cursor.to_list(length=100)
            return json.dumps([serialize_doc(g) for g in goals])

        elif tool_name == "get_performance_reviews":
            cursor  = db.performance_reviews.find({"employee_id": tool_args["employee_id"]})
            reviews = await cursor.to_list(length=20)
            return json.dumps([serialize_doc(r) for r in reviews])

        elif tool_name == "create_goal":
            goal = {
                "employee_id": tool_args["employee_id"],
                "title":       tool_args["title"],
                "description": tool_args["description"],
                "progress":    0,
                "target_date": tool_args["target_date"],
                "status":      "not-started",
                "kpis":        tool_args.get("kpis", []),
                "created":     datetime.now().isoformat()
            }
            result  = await db.goals.insert_one(goal)
            goal_id = str(result.inserted_id)
            logger.info(f"✅ Goal created: {goal_id}")
            return json.dumps({"success": True, "goal_id": goal_id,
                               "message": f"Goal '{tool_args['title']}' created successfully."})

        elif tool_name == "update_goal_progress":
            try:
                oid = ObjectId(tool_args["goal_id"])
            except Exception:
                return json.dumps({"error": "Invalid goal ID"})

            progress = min(100, max(0, tool_args["progress"]))
            status   = ("on-track" if progress >= 80 else
                        "in-progress" if progress >= 50 else "needs-attention")

            update   = {"$set": {"progress": progress, "status": status}}
            if tool_args.get("note"):
                update["$push"] = {"notes": {
                    "date": datetime.now().isoformat(),
                    "note": tool_args["note"]
                }}

            await db.goals.update_one({"_id": oid}, update)
            updated = await db.goals.find_one({"_id": oid})
            if not updated:
                return json.dumps({"error": "Goal not found"})
            return json.dumps({"success": True, "goal": serialize_doc(updated),
                               "message": f"Goal updated to {progress}% — status: {status}"})

        elif tool_name == "get_performance_summary":
            goals_cursor   = db.goals.find({"employee_id": tool_args["employee_id"]})
            goals          = await goals_cursor.to_list(length=100)
            reviews_cursor = db.performance_reviews.find({"employee_id": tool_args["employee_id"]})
            reviews        = await reviews_cursor.to_list(length=10)

            avg_progress   = (sum(g["progress"] for g in goals) / len(goals)) if goals else 0
            latest_rating  = reviews[0]["rating"] if reviews else None
            needs_attention = [g["title"] for g in goals if g.get("status") == "needs-attention"]

            return json.dumps({
                "employee_id":       tool_args["employee_id"],
                "total_goals":       len(goals),
                "avg_progress":      round(avg_progress, 1),
                "latest_rating":     latest_rating,
                "on_track":          sum(1 for g in goals if g.get("status") == "on-track"),
                "needs_attention":   needs_attention,
                "total_reviews":     len(reviews)
            })

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        logger.error(f"❌ Tool {tool_name} failed: {str(e)}")
        return json.dumps({"error": str(e)})

# ─────────────────────────────────────────────
# Seed Data
# ─────────────────────────────────────────────
SEED_GOALS = [
    {"employee_id": "EMP000001", "title": "Complete Q1 Project Deliverables",
     "description": "Deliver all planned features for Q1 release",
     "progress": 75, "target_date": "2025-03-31", "status": "on-track",
     "kpis": ["Code quality", "On-time delivery", "Bug reduction"], "created": "2025-01-01"},
    {"employee_id": "EMP000001", "title": "Mentor Junior Developers",
     "description": "Weekly mentoring sessions for 2 junior developers",
     "progress": 40, "target_date": "2025-06-30", "status": "needs-attention",
     "kpis": ["Mentee progress", "Knowledge transfer"], "created": "2025-01-01"},
]
SEED_REVIEWS = [
    {"employee_id": "EMP000001", "period": "H2 2024", "rating": 4.5,
     "date": "2024-12-15", "reviewer": "Jane Smith (Manager)",
     "strengths": ["Technical expertise", "Team collaboration", "Problem solving"],
     "improvements": ["Time management", "Documentation"],
     "summary": "Excellent performance with strong technical contributions."},
]

@app.on_event("startup")
async def startup_event():
    global mongo_client, db
    logger.info("🚀 Performance Agent v2 Starting (with tool calling)")
    try:
        mongo_client = AsyncIOMotorClient(MONGODB_URL)
        db = mongo_client[DB_NAME]
        await mongo_client.admin.command("ping")
        logger.info("✅ MongoDB connected")
        if await db.goals.count_documents({}) == 0:
            await db.goals.insert_many(SEED_GOALS)
        if await db.performance_reviews.count_documents({}) == 0:
            await db.performance_reviews.insert_many(SEED_REVIEWS)
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
    return {"status": "healthy", "service": "performance-agent", "version": "2.0.0",
            "openai_status": "configured" if OPENAI_API_KEY else "missing",
            "mongodb_status": mongo_status, "mode": "agentic-tool-calling"}

# ─────────────────────────────────────────────
# AI Query Endpoint — Agentic Loop
# ─────────────────────────────────────────────
@app.post("/api/performance/query", response_model=PerformanceQueryResponse)
async def query_performance(request: PerformanceQueryRequest):
    try:
        logger.info(f"📥 Performance query: {request.query}")
        if not client:
            raise HTTPException(status_code=500, detail="OpenAI not configured")
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")

        conv_id = request.conversation_id or str(uuid.uuid4())

        original_query = request.query
        if CONTEXT_MARKER in request.query:
            original_query = request.query.split(CONTEXT_MARKER)[0].strip()

        if any(kw in original_query.lower() for kw in PERFORMANCE_SENSITIVE_KEYWORDS):
            logger.warning(f"🚨 Sensitive performance query: {original_query}")
            await log_message(conv_id, "user",      request.query,                   request.employee_id, flagged=True)
            await log_message(conv_id, "assistant", PERFORMANCE_ESCALATION_RESPONSE, request.employee_id, flagged=True)
            return PerformanceQueryResponse(answer=PERFORMANCE_ESCALATION_RESPONSE,
                                            data=None, conversation_id=conv_id, tools_used=[])

        messages = [{"role": "system", "content": PERFORMANCE_SYSTEM_PROMPT}]
        if request.employee_id:
            messages.append({"role": "system", "content":
                f"The employee making this request has ID: {request.employee_id}."})

        history = await get_conversation_history(conv_id, limit=10)
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["message"]})
        messages.append({"role": "user", "content": request.query})

        tools_used     = []
        summary_data   = None
        max_iterations = 6

        for iteration in range(max_iterations):
            logger.info(f"🔄 Performance agent iteration {iteration + 1}")
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=PERFORMANCE_TOOLS,
                tool_choice="auto",
                temperature=0.2,
                max_tokens=600
            )

            msg = response.choices[0].message
            messages.append(msg)

            if not msg.tool_calls:
                answer = msg.content.strip() if msg.content else "I was unable to generate a response."
                logger.info(f"✅ Performance agent done after {iteration + 1} iteration(s)")
                await log_message(conv_id, "user",      request.query, request.employee_id)
                await log_message(conv_id, "assistant", answer,        request.employee_id)
                return PerformanceQueryResponse(answer=answer, data=summary_data,
                                                conversation_id=conv_id, tools_used=tools_used)

            for tool_call in msg.tool_calls:
                tool_name   = tool_call.function.name
                tool_args   = json.loads(tool_call.function.arguments)
                logger.info(f"🔧 Performance calling tool: {tool_name}({tool_args})")
                tool_result = await execute_tool(tool_name, tool_args)
                tools_used.append(tool_name)

                if tool_name == "get_performance_summary":
                    try:
                        summary_data = json.loads(tool_result)
                    except Exception:
                        pass

                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": tool_result})

        answer = "I reached the maximum reasoning steps. Please try rephrasing your question."
        await log_message(conv_id, "user", request.query, request.employee_id)
        await log_message(conv_id, "assistant", answer, request.employee_id)
        return PerformanceQueryResponse(answer=answer, data=None, conversation_id=conv_id, tools_used=tools_used)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Performance error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/performance/goals")
async def get_goals(employee_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor = db.goals.find({"employee_id": employee_id})
    goals  = await cursor.to_list(length=100)
    goals  = [serialize_doc(g) for g in goals]
    avg    = sum(g["progress"] for g in goals) / len(goals) if goals else 0
    return {"employee_id": employee_id, "goals": goals, "total": len(goals), "avg_progress": round(avg, 1)}

@app.get("/api/performance/reviews")
async def get_reviews(employee_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor  = db.performance_reviews.find({"employee_id": employee_id})
    reviews = await cursor.to_list(length=50)
    reviews = [serialize_doc(r) for r in reviews]
    avg     = sum(r["rating"] for r in reviews) / len(reviews) if reviews else None
    return {"employee_id": employee_id, "reviews": reviews, "total": len(reviews),
            "avg_rating": round(avg, 2) if avg else None}

@app.get("/api/performance/history/chat")
async def get_chat_history(employee_id: str, limit: int = 50):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor = db.chat_history.find(
        {"employee_id": employee_id, "service": "performance"}, sort=[("timestamp", -1)]
    ).limit(limit)
    history = await cursor.to_list(length=limit)
    return {"employee_id": employee_id, "history": [serialize_doc(h) for h in history]}

@app.get("/api/performance/history/chat/{conversation_id}")
async def get_conversation(conversation_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    cursor = db.chat_history.find({"conversation_id": conversation_id}, sort=[("timestamp", 1)])
    messages = await cursor.to_list(length=200)
    return {"conversation_id": conversation_id, "messages": [serialize_doc(m) for m in messages]}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8006)))