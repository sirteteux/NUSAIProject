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
import json
import uvicorn

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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("❌ OPENAI_API_KEY not found!")
else:
    logger.info(f"✅ OpenAI API Key configured")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Models
class PerformanceQueryRequest(BaseModel):
    query: str
    employee_id: Optional[str] = None

class PerformanceQueryResponse(BaseModel):
    answer: str
    data: Optional[Dict] = None

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

# Employee goals database
EMPLOYEE_GOALS = {
    "EMP000001": [
        {
            "id": "G001",
            "title": "Complete Q1 Project Deliverables",
            "description": "Deliver all planned features for Q1 release",
            "progress": 75,
            "target_date": "2025-03-31",
            "status": "on-track",
            "kpis": ["Code quality", "On-time delivery", "Bug reduction"],
            "created": "2025-01-01"
        },
        {
            "id": "G002",
            "title": "Improve Code Review Turnaround",
            "description": "Reduce average code review time to under 24 hours",
            "progress": 60,
            "target_date": "2025-02-28",
            "status": "on-track",
            "kpis": ["Response time", "Review quality"],
            "created": "2025-01-15"
        },
        {
            "id": "G003",
            "title": "Mentor Junior Developers",
            "description": "Provide weekly mentoring sessions to 2 junior developers",
            "progress": 40,
            "target_date": "2025-06-30",
            "status": "needs-attention",
            "kpis": ["Mentee progress", "Knowledge transfer"],
            "created": "2025-01-01"
        }
    ]
}

PERFORMANCE_REVIEWS = {
    "EMP000001": [
        {
            "id": "REV001",
            "period": "H2 2024",
            "rating": 4.5,
            "date": "2024-12-15",
            "reviewer": "Jane Smith (Manager)",
            "strengths": ["Technical expertise", "Team collaboration", "Problem solving"],
            "improvements": ["Time management", "Documentation"],
            "summary": "Excellent performance with strong technical contributions."
        }
    ]
}

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

Be constructive, data-driven, and growth-focused in all assessments."""

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "performance-agent",
        "version": "1.0.0",
        "openai_status": "configured" if OPENAI_API_KEY else "missing"
    }

@app.post("/api/performance/query", response_model=PerformanceQueryResponse)
async def query_performance(request: PerformanceQueryRequest):
    try:
        logger.info(f"📥 Performance query: {request.query}")
        
        if not client:
            raise HTTPException(status_code=500, detail="OpenAI not configured")
        
        employee_context = ""
        employee_data = None
        
        if request.employee_id and request.employee_id in EMPLOYEE_GOALS:
            goals = EMPLOYEE_GOALS[request.employee_id]
            reviews = PERFORMANCE_REVIEWS.get(request.employee_id, [])
            
            employee_data = {
                "active_goals": len(goals),
                "avg_progress": sum(g["progress"] for g in goals) / len(goals) if goals else 0,
                "recent_rating": reviews[0]["rating"] if reviews else None
            }
            
            employee_context = f"""
Employee Performance Data:
- Active Goals: {len(goals)}
- Average Goal Progress: {employee_data['avg_progress']:.1f}%
- Latest Review Rating: {employee_data['recent_rating']}/5.0
- Goals Status: {sum(1 for g in goals if g['status'] == 'on-track')} on-track, {sum(1 for g in goals if g['status'] == 'needs-attention')} need attention
"""
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        
        if employee_context:
            messages.append({"role": "system", "content": employee_context})
        
        messages.append({"role": "user", "content": request.query})
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=500
        )
        
        answer = response.choices[0].message.content.strip()
        
        logger.info(f"✅ Generated performance response")
        
        return PerformanceQueryResponse(
            answer=answer,
            data=employee_data
        )
        
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/performance/goals")
async def get_goals(employee_id: str):
    try:
        goals = EMPLOYEE_GOALS.get(employee_id, [])
        
        return {
            "employee_id": employee_id,
            "goals": goals,
            "total": len(goals),
            "avg_progress": sum(g["progress"] for g in goals) / len(goals) if goals else 0
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/performance/goal/create")
async def create_goal(request: GoalCreateRequest):
    try:
        if request.employee_id not in EMPLOYEE_GOALS:
            EMPLOYEE_GOALS[request.employee_id] = []
        
        goal_id = f"G{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        goal = {
            "id": goal_id,
            "title": request.title,
            "description": request.description,
            "progress": 0,
            "target_date": request.target_date,
            "status": "not-started",
            "kpis": request.kpis or [],
            "created": datetime.now().isoformat()
        }
        
        EMPLOYEE_GOALS[request.employee_id].append(goal)
        
        logger.info(f"✅ Goal {goal_id} created for {request.employee_id}")
        
        return {
            "goal": goal,
            "message": "Goal created successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/performance/goal/update")
async def update_goal(request: GoalUpdateRequest):
    try:
        for emp_id, goals in EMPLOYEE_GOALS.items():
            for goal in goals:
                if goal["id"] == request.goal_id:
                    goal["progress"] = min(100, max(0, request.progress))
                    
                    if goal["progress"] >= 80:
                        goal["status"] = "on-track"
                    elif goal["progress"] >= 50:
                        goal["status"] = "in-progress"
                    else:
                        goal["status"] = "needs-attention"
                    
                    if request.notes:
                        if "notes" not in goal:
                            goal["notes"] = []
                        goal["notes"].append({
                            "date": datetime.now().isoformat(),
                            "note": request.notes
                        })
                    
                    logger.info(f"✅ Goal {request.goal_id} updated to {request.progress}%")
                    
                    return {
                        "goal": goal,
                        "message": "Goal updated successfully"
                    }
        
        raise HTTPException(status_code=404, detail="Goal not found")
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/performance/reviews")
async def get_reviews(employee_id: str):
    try:
        reviews = PERFORMANCE_REVIEWS.get(employee_id, [])
        
        return {
            "employee_id": employee_id,
            "reviews": reviews,
            "total": len(reviews),
            "avg_rating": sum(r["rating"] for r in reviews) / len(reviews) if reviews else None
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    logger.info("=" * 50)
    logger.info("🚀 Performance Agent Starting Up")
    logger.info("=" * 50)
    logger.info(f"OpenAI API: {'✅ Configured' if OPENAI_API_KEY else '❌ Missing'}")
    logger.info(f"Employees tracked: {len(EMPLOYEE_GOALS)}")
    logger.info("=" * 50)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8006))
    uvicorn.run(app, host="0.0.0.0", port=port)
