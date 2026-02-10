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
import json
import uvicorn

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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("❌ OPENAI_API_KEY not found!")
else:
    logger.info(f"✅ OpenAI API Key configured")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Models
class RecruitmentQueryRequest(BaseModel):
    query: str
    context: Optional[str] = None

class RecruitmentQueryResponse(BaseModel):
    answer: str
    data: Optional[Dict] = None

# Job openings database
JOB_OPENINGS = [
    {
        "id": 1,
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
        "id": 2,
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
        "id": 3,
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
        "id": 4,
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

Be professional, data-driven, and fair in all assessments."""

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "recruitment-agent",
        "version": "1.0.0",
        "openai_status": "configured" if OPENAI_API_KEY else "missing"
    }

@app.post("/api/recruitment/query", response_model=RecruitmentQueryResponse)
async def query_recruitment(request: RecruitmentQueryRequest):
    try:
        logger.info(f"📥 Recruitment query: {request.query}")
        
        if not client:
            raise HTTPException(status_code=500, detail="OpenAI not configured")
        
        # Add context about current openings
        openings_context = f"\nCurrent Open Positions ({len(JOB_OPENINGS)}):\n"
        for job in JOB_OPENINGS[:3]:
            openings_context += f"- {job['title']} ({job['department']}) - {job['location']}\n"
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": openings_context},
        ]
        
        if request.context:
            messages.append({"role": "system", "content": f"Additional context: {request.context}"})
        
        messages.append({"role": "user", "content": request.query})
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=500
        )
        
        answer = response.choices[0].message.content.strip()
        
        logger.info(f"✅ Generated recruitment response")
        
        return RecruitmentQueryResponse(
            answer=answer,
            data={"open_positions": len(JOB_OPENINGS)}
        )
        
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/recruitment/openings")
async def get_openings(department: Optional[str] = None, location: Optional[str] = None):
    try:
        openings = JOB_OPENINGS.copy()
        
        if department:
            openings = [j for j in openings if j["department"].lower() == department.lower()]
        
        if location:
            openings = [j for j in openings if location.lower() in j["location"].lower()]
        
        return {
            "openings": openings,
            "total": len(openings)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/recruitment/opening/{job_id}")
async def get_opening(job_id: int):
    try:
        job = next((j for j in JOB_OPENINGS if j["id"] == job_id), None)
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return job
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    logger.info("=" * 50)
    logger.info("🚀 Recruitment Agent Starting Up")
    logger.info("=" * 50)
    logger.info(f"OpenAI API: {'✅ Configured' if OPENAI_API_KEY else '❌ Missing'}")
    logger.info(f"Job Openings: {len(JOB_OPENINGS)}")
    logger.info("=" * 50)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8005))
    uvicorn.run(app, host="0.0.0.0", port=port)
