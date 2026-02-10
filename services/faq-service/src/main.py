"""
FAQ Agent - HR Knowledge Base Assistant
Answers common HR questions using OpenAI
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
from dotenv import load_dotenv
import logging
from openai import OpenAI
import uvicorn
import traceback

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="FAQ Agent",
    description="HR Knowledge Base Assistant",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get API key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Check if API key exists
if not OPENAI_API_KEY:
    logger.error("❌ OPENAI_API_KEY not found in environment variables!")
else:
    logger.info(f"✅ OpenAI API Key found (starts with: {OPENAI_API_KEY[:20]}...)")

# Initialize OpenAI client
try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info("✅ OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"❌ Failed to initialize OpenAI client: {str(e)}")
    client = None

# Pydantic models
class QuestionRequest(BaseModel):
    question: str
    user_id: Optional[str] = None

class QuestionResponse(BaseModel):
    answer: str
    question: str
    confidence: float = 0.95

# System prompt for FAQ agent
SYSTEM_PROMPT = """You are a helpful HR assistant for a company. You answer questions about:
- Company policies and procedures
- Working hours and schedules
- Benefits and perks
- Leave policies (vacation, sick leave, etc.)
- Dress code
- Office locations and facilities
- Onboarding and training
- General HR inquiries

Be professional, friendly, and concise. If you don't know the answer, be honest and suggest who to contact.

Company Information:
- Working Hours: Monday-Friday, 9 AM - 6 PM
- Dress Code: Business casual
- Main Office: 123 Business Street, Singapore
- HR Contact: hr@company.com
- Annual Leave: 18 days per year
- Sick Leave: 14 days per year
- Medical Benefits: Full coverage for employee, 50% for dependents
"""

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    api_key_status = "configured" if OPENAI_API_KEY else "missing"
    client_status = "initialized" if client else "failed"
    
    return {
        "status": "healthy",
        "service": "faq-agent",
        "version": "1.0.0",
        "openai_api_key": api_key_status,
        "openai_client": client_status
    }

@app.post("/api/faq/ask", response_model=QuestionResponse)
async def ask_question(request: QuestionRequest):
    """
    Answer FAQ questions using OpenAI
    """
    try:
        logger.info(f"📥 Received question: {request.question}")
        
        # Check if API key exists
        if not OPENAI_API_KEY:
            logger.error("❌ OpenAI API key not configured")
            raise HTTPException(
                status_code=500, 
                detail="OpenAI API key not configured. Please set OPENAI_API_KEY in .env file"
            )
        
        # Check if client is initialized
        if not client:
            logger.error("❌ OpenAI client not initialized")
            raise HTTPException(
                status_code=500,
                detail="OpenAI client initialization failed"
            )
        
        logger.info("🔄 Calling OpenAI API...")
        
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": request.question}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        answer = response.choices[0].message.content.strip()
        
        logger.info(f"✅ Got response from OpenAI: {answer[:100]}...")
        
        return QuestionResponse(
            answer=answer,
            question=request.question,
            confidence=0.95
        )
        
    except HTTPException as he:
        # Re-raise HTTP exceptions
        logger.error(f"❌ HTTP Exception: {he.detail}")
        raise he
        
    except Exception as e:
        # Log the full error
        logger.error(f"❌ Error processing question: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Check for specific OpenAI errors
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

@app.get("/api/faq/categories")
async def get_categories():
    """
    Return available FAQ categories
    """
    return {
        "categories": [
            {
                "id": "policies",
                "name": "Company Policies",
                "icon": "policy"
            },
            {
                "id": "benefits",
                "name": "Benefits & Perks",
                "icon": "card_giftcard"
            },
            {
                "id": "leave",
                "name": "Leave Policies",
                "icon": "event"
            },
            {
                "id": "office",
                "name": "Office & Facilities",
                "icon": "business"
            },
            {
                "id": "training",
                "name": "Training & Development",
                "icon": "school"
            },
            {
                "id": "general",
                "name": "General Inquiries",
                "icon": "help"
            }
        ]
    }

@app.get("/api/faq/popular")
async def get_popular_questions():
    """
    Return popular/frequently asked questions
    """
    return {
        "questions": [
            "What are the company's working hours?",
            "How do I request vacation leave?",
            "What is the dress code policy?",
            "How many sick days do I get?",
            "What benefits are available?",
            "Where is the office located?",
            "How do I contact HR?",
            "What is the remote work policy?"
        ]
    }

@app.on_event("startup")
async def startup_event():
    """Log startup information"""
    logger.info("=" * 50)
    logger.info("🚀 FAQ Agent Starting Up")
    logger.info("=" * 50)
    logger.info(f"OpenAI API Key: {'✅ Configured' if OPENAI_API_KEY else '❌ Missing'}")
    if OPENAI_API_KEY:
        logger.info(f"Key starts with: {OPENAI_API_KEY[:20]}...")
    logger.info(f"OpenAI Client: {'✅ Initialized' if client else '❌ Failed'}")
    logger.info("=" * 50)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port)
