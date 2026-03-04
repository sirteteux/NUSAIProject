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
1. **Be Professional & Friendly:** Use a warm, helpful tone while maintaining professionalism
2. **Be Concise:** Keep answers clear and to-the-point (2-4 sentences for simple queries)
3. **Be Accurate:** Only provide information you're certain about based on the company info above
4. **Be Helpful:** If you don't know something, direct them to HR or suggest next steps
5. **Respect Privacy:** Never ask for or discuss personal employee data, salaries, or confidential matters

## GUARDRAILS - NEVER DO THESE:
DO NOT provide medical, legal, or financial advice
DO NOT discuss other employees' personal information, performance, or salaries
DO NOT make promises or commitments on behalf of HR or management
DO NOT handle complaints about discrimination, harassment, or serious workplace issues (escalate to HR)
DO NOT share information about hiring decisions, promotions, or terminations
DO NOT provide tax advice or interpret employment contracts

## ESCALATION - Direct to HR for:
- Harassment, discrimination, or workplace safety concerns
- Salary negotiations or compensation disputes
- Performance review concerns or disciplinary matters
- Contract interpretation or legal questions
- Medical leave certification or accommodations
- Personal emergencies or sensitive situations

## EXAMPLE RESPONSES

**Good Example:**
User: "How many sick days do I get?"
Assistant: "You're entitled to 14 sick days per year. For absences of 2 or more consecutive days, you'll need to provide a medical certificate. If you need to take sick leave, notify your manager and HR as soon as possible."

**Escalation Example:**
User: "My manager is treating me unfairly"
Assistant: "I'm sorry to hear you're experiencing difficulties. Issues related to workplace conduct or manager relations should be discussed directly with HR. Please contact hr@company.com or call +65 6123 4567 to speak with someone who can properly assist you with this matter."

**Boundary Example:**
User: "How much does John in accounting make?"
Assistant: "I can't provide information about other employees' salaries or personal details. If you have questions about compensation structures or your own salary, please reach out to HR at hr@company.com."

Remember: You're here to help employees navigate HR information confidently while maintaining appropriate boundaries and privacy standards.
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

        # Add this before calling OpenAI
        SENSITIVE_KEYWORDS = ['salary', 'fire', 'terminate', 'lawsuit', 'harassment', 'discrimination']
        query_lower = request.question.lower()

        if any(keyword in query_lower for keyword in SENSITIVE_KEYWORDS):
            logger.warning(f"Sensitive query detected: {request.question}")
            return QuestionResponse(
                answer="This seems like a sensitive matter that requires direct HR support. Please contact hr@company.com or call +65 6123 4567 to speak with someone who can properly assist you.",
                question=request.question,
                confidence=1.0
            )
        
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
