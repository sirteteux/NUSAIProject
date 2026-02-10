"""
Coordinator Agent - Intelligent Multi-Agent Router using LangChain
Routes user queries to the appropriate specialized HR agent
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
import os
from dotenv import load_dotenv
import logging
from openai import OpenAI
import httpx
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
    title="Coordinator Agent",
    description="Intelligent Multi-Agent Router with LangChain",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("❌ OPENAI_API_KEY not found!")
else:
    logger.info(f"✅ OpenAI API Key configured")

# Agent URLs
FAQ_URL = os.getenv("FAQ_URL", "http://faq-agent:5005")
PAYROLL_URL = os.getenv("PAYROLL_URL", "http://payroll-agent:5002")
LEAVE_URL = os.getenv("LEAVE_URL", "http://leave-agent:5006")
RECRUITMENT_URL = os.getenv("RECRUITMENT_URL", "http://recruitment-agent:5003")
PERFORMANCE_URL = os.getenv("PERFORMANCE_URL", "http://performance-agent:5004")

# Models
class CoordinatorRequest(BaseModel):
    query: str
    employee_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class CoordinatorResponse(BaseModel):
    answer: str
    agent_used: str
    confidence: float
    metadata: Optional[Dict] = None

# HTTP client for agent communication
http_client = httpx.AsyncClient(timeout=30.0)

# Agent communication functions
async def call_faq_agent(query: str) -> Dict:
    """Call FAQ Agent for general HR questions"""
    try:
        logger.info(f"🔀 Routing to FAQ Agent: {query[:50]}")
        response = await http_client.post(
            f"{FAQ_URL}/api/faq/ask",
            json={"question": query}
        )
        response.raise_for_status()
        data = response.json()
        return {
            "answer": data.get("answer", ""),
            "agent": "FAQ",
            "success": True
        }
    except Exception as e:
        logger.error(f"❌ FAQ Agent error: {str(e)}")
        return {"answer": f"Error calling FAQ agent: {str(e)}", "agent": "FAQ", "success": False}

async def call_payroll_agent(query: str, employee_id: str = None) -> Dict:
    """Call Payroll Agent for salary and compensation questions"""
    try:
        logger.info(f"🔀 Routing to Payroll Agent: {query[:50]}")
        response = await http_client.post(
            f"{PAYROLL_URL}/api/payroll/query",
            json={"query": query, "employee_id": employee_id or "EMP000001"}
        )
        response.raise_for_status()
        data = response.json()
        return {
            "answer": data.get("answer", ""),
            "agent": "Payroll",
            "success": True
        }
    except Exception as e:
        logger.error(f"❌ Payroll Agent error: {str(e)}")
        return {"answer": f"Error calling Payroll agent: {str(e)}", "agent": "Payroll", "success": False}

async def call_leave_agent(query: str, employee_id: str = None) -> Dict:
    """Call Leave Agent for leave requests and balance questions"""
    try:
        logger.info(f"🔀 Routing to Leave Agent: {query[:50]}")
        response = await http_client.post(
            f"{LEAVE_URL}/api/leave/query",
            json={"query": query, "employee_id": employee_id or "EMP000001"}
        )
        response.raise_for_status()
        data = response.json()
        return {
            "answer": data.get("answer", ""),
            "agent": "Leave",
            "success": True
        }
    except Exception as e:
        logger.error(f"❌ Leave Agent error: {str(e)}")
        return {"answer": f"Error calling Leave agent: {str(e)}", "agent": "Leave", "success": False}

async def call_recruitment_agent(query: str) -> Dict:
    """Call Recruitment Agent for hiring and job-related questions"""
    try:
        logger.info(f"🔀 Routing to Recruitment Agent: {query[:50]}")
        response = await http_client.post(
            f"{RECRUITMENT_URL}/api/recruitment/query",
            json={"query": query}
        )
        response.raise_for_status()
        data = response.json()
        return {
            "answer": data.get("answer", ""),
            "agent": "Recruitment",
            "success": True
        }
    except Exception as e:
        logger.error(f"❌ Recruitment Agent error: {str(e)}")
        return {"answer": f"Error calling Recruitment agent: {str(e)}", "agent": "Recruitment", "success": False}

async def call_performance_agent(query: str, employee_id: str = None) -> Dict:
    """Call Performance Agent for goals and performance-related questions"""
    try:
        logger.info(f"🔀 Routing to Performance Agent: {query[:50]}")
        response = await http_client.post(
            f"{PERFORMANCE_URL}/api/performance/query",
            json={"query": query, "employee_id": employee_id or "EMP000001"}
        )
        response.raise_for_status()
        data = response.json()
        return {
            "answer": data.get("answer", ""),
            "agent": "Performance",
            "success": True
        }
    except Exception as e:
        logger.error(f"❌ Performance Agent error: {str(e)}")
        return {"answer": f"Error calling Performance agent: {str(e)}", "agent": "Performance", "success": False}

# Intelligent routing using OpenAI (LangChain-inspired approach)
async def route_query_intelligent(query: str, employee_id: str = None) -> Dict:
    """
    Use OpenAI to intelligently route the query to the appropriate agent
    This implements a LangChain-style routing pattern
    """
    
    if not OPENAI_API_KEY:
        logger.warning("⚠️  No OpenAI key, defaulting to FAQ agent")
        return await call_faq_agent(query)
    
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # LangChain-style routing prompt with clear agent descriptions
        routing_prompt = f"""You are an intelligent router for an HR system with 5 specialized AI agents.
Analyze this user query and determine which agent should handle it.

User Query: "{query}"

Available Agents:
1. FAQ Agent
   - Handles: General HR questions, company policies, working hours, dress code, office locations, benefits overview
   - Keywords: "policy", "company", "office", "hours", "benefits", "how do I", "where is"

2. Payroll Agent
   - Handles: Salary information, compensation, payslips, bonuses, deductions, tax questions
   - Keywords: "salary", "pay", "payslip", "bonus", "deduction", "tax", "compensation", "earnings"

3. Leave Agent
   - Handles: Leave requests, vacation balance, sick leave, leave policies, time off
   - Keywords: "leave", "vacation", "holiday", "sick", "time off", "days off", "absence", "PTO"

4. Recruitment Agent
   - Handles: Job openings, hiring process, applications, interviews, career opportunities
   - Keywords: "job", "opening", "position", "hire", "recruit", "apply", "interview", "career"

5. Performance Agent
   - Handles: Goals, KPIs, performance reviews, development, feedback, ratings
   - Keywords: "goal", "performance", "review", "KPI", "objective", "development", "feedback", "rating"

Respond with ONLY ONE of these exact words: FAQ, Payroll, Leave, Recruitment, Performance

Think step by step:
1. Identify key words in the query
2. Match them to agent capabilities
3. Choose the BEST matching agent"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": routing_prompt},
                {"role": "user", "content": query}
            ],
            temperature=0.0,  # Deterministic routing
            max_tokens=10
        )
        
        agent_choice = response.choices[0].message.content.strip()
        logger.info(f"🎯 LangChain-style routing chose: {agent_choice}")
        
        # Route to the selected agent
        if "Payroll" in agent_choice:
            return await call_payroll_agent(query, employee_id)
        elif "Leave" in agent_choice:
            return await call_leave_agent(query, employee_id)
        elif "Recruitment" in agent_choice:
            return await call_recruitment_agent(query)
        elif "Performance" in agent_choice:
            return await call_performance_agent(query, employee_id)
        else:  # Default to FAQ
            return await call_faq_agent(query)
            
    except Exception as e:
        logger.error(f"❌ Routing error: {str(e)}, defaulting to FAQ agent")
        return await call_faq_agent(query)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "coordinator-agent",
        "version": "1.0.0",
        "framework": "LangChain-inspired routing",
        "openai_status": "configured" if OPENAI_API_KEY else "missing",
        "agents_connected": {
            "faq": FAQ_URL,
            "payroll": PAYROLL_URL,
            "leave": LEAVE_URL,
            "recruitment": RECRUITMENT_URL,
            "performance": PERFORMANCE_URL
        }
    }

@app.post("/api/coordinator/ask", response_model=CoordinatorResponse)
async def ask_coordinator(request: CoordinatorRequest):
    """
    Main endpoint - intelligently routes queries to appropriate agents using LangChain pattern
    """
    try:
        logger.info(f"📥 Coordinator received: {request.query}")
        
        # Intelligent routing using LangChain-style approach
        result = await route_query_intelligent(request.query, request.employee_id)
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("answer"))
        
        logger.info(f"✅ Routed to {result['agent']} agent successfully")
        
        return CoordinatorResponse(
            answer=result["answer"],
            agent_used=result["agent"],
            confidence=0.95,
            metadata={
                "routing_method": "langchain_intelligent",
                "timestamp": datetime.now().isoformat(),
                "employee_id": request.employee_id
            }
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"❌ Coordinator error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/coordinator/agents")
async def list_agents():
    """List all available agents and their capabilities"""
    return {
        "agents": [
            {
                "name": "FAQ",
                "description": "General HR questions and company policies",
                "capabilities": ["Company info", "Working hours", "Policies", "Dress code", "Office locations"],
                "keywords": ["policy", "company", "office", "hours", "benefits"],
                "url": FAQ_URL
            },
            {
                "name": "Payroll",
                "description": "Salary and compensation information",
                "capabilities": ["Salary queries", "Payslips", "Bonuses", "Deductions", "Tax info"],
                "keywords": ["salary", "pay", "payslip", "bonus", "tax"],
                "url": PAYROLL_URL
            },
            {
                "name": "Leave",
                "description": "Leave management and requests",
                "capabilities": ["Leave balance", "Leave requests", "Vacation days", "Sick leave", "Policies"],
                "keywords": ["leave", "vacation", "holiday", "sick", "time off"],
                "url": LEAVE_URL
            },
            {
                "name": "Recruitment",
                "description": "Job openings and hiring process",
                "capabilities": ["Job openings", "Applications", "Interview process", "Career opportunities"],
                "keywords": ["job", "opening", "hire", "recruit", "interview"],
                "url": RECRUITMENT_URL
            },
            {
                "name": "Performance",
                "description": "Performance management and goals",
                "capabilities": ["Goal tracking", "Performance reviews", "KPIs", "Career development"],
                "keywords": ["goal", "performance", "review", "KPI", "development"],
                "url": PERFORMANCE_URL
            }
        ],
        "routing_strategy": "LangChain-inspired intelligent routing with OpenAI"
    }

@app.on_event("startup")
async def startup_event():
    """Log startup information"""
    logger.info("=" * 70)
    logger.info("🚀 Coordinator Agent Starting Up - LangChain Pattern")
    logger.info("=" * 70)
    logger.info(f"OpenAI API: {'✅ Configured' if OPENAI_API_KEY else '❌ Missing'}")
    logger.info(f"Routing Method: LangChain-inspired intelligent routing")
    logger.info(f"FAQ Agent: {FAQ_URL}")
    logger.info(f"Payroll Agent: {PAYROLL_URL}")
    logger.info(f"Leave Agent: {LEAVE_URL}")
    logger.info(f"Recruitment Agent: {RECRUITMENT_URL}")
    logger.info(f"Performance Agent: {PERFORMANCE_URL}")
    logger.info("=" * 70)

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await http_client.aclose()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8007))
    uvicorn.run(app, host="0.0.0.0", port=port)
