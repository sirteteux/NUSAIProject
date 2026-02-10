"""
Leave Management Agent - Leave Request and Tracking Assistant
Handles leave requests, balance tracking, and leave approvals using OpenAI
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
import os
from dotenv import load_dotenv
import logging
from openai import OpenAI
from datetime import datetime, timedelta
import json
import uvicorn

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
    title="Leave Management Agent",
    description="Leave Request and Tracking Assistant",
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

# Initialize OpenAI client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("❌ OPENAI_API_KEY not found!")
else:
    logger.info(f"✅ OpenAI API Key configured")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Pydantic models
class LeaveRequest(BaseModel):
    employee_id: str
    type: str  # annual, sick, personal, etc.
    start_date: str
    end_date: str
    reason: Optional[str] = None

class LeaveResponse(BaseModel):
    request_id: str
    employee_id: str
    type: str
    start_date: str
    end_date: str
    days: int
    status: str
    submitted_at: str

class LeaveQueryRequest(BaseModel):
    query: str
    employee_id: Optional[str] = None

class LeaveQueryResponse(BaseModel):
    answer: str
    data: Optional[Dict] = None

# Mock leave database
LEAVE_BALANCES = {
    "EMP000001": {
        "annual": {"total": 18, "used": 5, "remaining": 13},
        "sick": {"total": 14, "used": 2, "remaining": 12},
        "personal": {"total": 3, "used": 1, "remaining": 2}
    },
    "EMP000002": {
        "annual": {"total": 18, "used": 8, "remaining": 10},
        "sick": {"total": 14, "used": 1, "remaining": 13},
        "personal": {"total": 3, "used": 0, "remaining": 3}
    }
}

LEAVE_HISTORY = {
    "EMP000001": [
        {
            "id": "LV001",
            "type": "annual",
            "start_date": "2024-12-25",
            "end_date": "2024-12-29",
            "days": 5,
            "status": "approved",
            "submitted_at": "2024-12-01T10:00:00"
        },
        {
            "id": "LV002",
            "type": "sick",
            "start_date": "2024-11-15",
            "end_date": "2024-11-16",
            "days": 2,
            "status": "approved",
            "submitted_at": "2024-11-15T08:30:00"
        }
    ]
}

# System prompt
LEAVE_SYSTEM_PROMPT = """You are a helpful Leave Management Assistant. You help employees with:
- Leave balance inquiries
- Leave policy questions
- Leave request guidance
- Leave approval status
- Holiday calendar information

Company Leave Policy:
- Annual Leave: 18 days per year
- Sick Leave: 14 days per year (with medical certificate)
- Personal Leave: 3 days per year
- Leave requests should be submitted at least 2 weeks in advance (except sick leave)
- Maximum consecutive leave: 14 days for annual leave

Be professional and helpful. Provide clear information about leave balances and policies.
"""

def calculate_leave_days(start_date: str, end_date: str) -> int:
    """Calculate number of leave days (excluding weekends)"""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    
    days = 0
    current = start
    while current <= end:
        # Count only weekdays
        if current.weekday() < 5:  # Monday = 0, Friday = 4
            days += 1
        current += timedelta(days=1)
    
    return days

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "leave-management-agent",
        "version": "1.0.0",
        "openai_status": "configured" if OPENAI_API_KEY else "missing"
    }

@app.post("/api/leave/query", response_model=LeaveQueryResponse)
async def query_leave(request: LeaveQueryRequest):
    """
    Answer leave-related questions using AI
    """
    try:
        logger.info(f"📥 Leave query: {request.query}")
        
        if not client:
            raise HTTPException(status_code=500, detail="OpenAI not configured")
        
        # Get employee leave balance if employee_id provided
        leave_context = ""
        leave_data = None
        
        if request.employee_id and request.employee_id in LEAVE_BALANCES:
            balance = LEAVE_BALANCES[request.employee_id]
            leave_data = balance
            leave_context = f"""
Employee Leave Balance:
- Annual Leave: {balance['annual']['remaining']} days remaining (out of {balance['annual']['total']})
- Sick Leave: {balance['sick']['remaining']} days remaining (out of {balance['sick']['total']})
- Personal Leave: {balance['personal']['remaining']} days remaining (out of {balance['personal']['total']})
"""
        
        # Construct messages
        messages = [
            {"role": "system", "content": LEAVE_SYSTEM_PROMPT},
        ]
        
        if leave_context:
            messages.append({"role": "system", "content": leave_context})
        
        messages.append({"role": "user", "content": request.query})
        
        # Call OpenAI
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=500
        )
        
        answer = response.choices[0].message.content.strip()
        
        logger.info(f"✅ Generated leave response")
        
        return LeaveQueryResponse(
            answer=answer,
            data=leave_data
        )
        
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/leave/request", response_model=LeaveResponse)
async def request_leave(request: LeaveRequest):
    """
    Submit a leave request
    """
    try:
        logger.info(f"📝 Leave request from {request.employee_id}")
        
        # Validate employee
        if request.employee_id not in LEAVE_BALANCES:
            raise HTTPException(status_code=404, detail="Employee not found")
        
        # Calculate days
        days = calculate_leave_days(request.start_date, request.end_date)
        
        # Check if enough balance
        balance = LEAVE_BALANCES[request.employee_id]
        leave_type = request.type.lower()
        
        if leave_type not in balance:
            raise HTTPException(status_code=400, detail=f"Invalid leave type: {leave_type}")
        
        if balance[leave_type]["remaining"] < days:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient {leave_type} leave balance. You have {balance[leave_type]['remaining']} days remaining."
            )
        
        # Create leave request
        request_id = f"LV{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        leave_entry = {
            "id": request_id,
            "type": leave_type,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "days": days,
            "status": "pending",
            "submitted_at": datetime.now().isoformat(),
            "reason": request.reason
        }
        
        # Add to history
        if request.employee_id not in LEAVE_HISTORY:
            LEAVE_HISTORY[request.employee_id] = []
        LEAVE_HISTORY[request.employee_id].append(leave_entry)
        
        logger.info(f"✅ Leave request {request_id} submitted")
        
        return LeaveResponse(
            request_id=request_id,
            employee_id=request.employee_id,
            type=leave_type,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            status="pending",
            submitted_at=leave_entry["submitted_at"]
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"❌ Error submitting leave: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/leave/balance")
async def get_leave_balance(employee_id: str):
    """
    Get leave balance for employee
    """
    try:
        if employee_id not in LEAVE_BALANCES:
            raise HTTPException(status_code=404, detail="Employee not found")
        
        return {
            "employee_id": employee_id,
            "balances": LEAVE_BALANCES[employee_id]
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/leave/history")
async def get_leave_history(employee_id: str):
    """
    Get leave history for employee
    """
    try:
        history = LEAVE_HISTORY.get(employee_id, [])
        
        return {
            "employee_id": employee_id,
            "history": sorted(history, key=lambda x: x["submitted_at"], reverse=True)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/leave/approve/{request_id}")
async def approve_leave(request_id: str):
    """
    Approve a leave request (for managers/HR)
    """
    try:
        # Find the leave request
        for emp_id, requests in LEAVE_HISTORY.items():
            for req in requests:
                if req["id"] == request_id:
                    req["status"] = "approved"
                    
                    # Update balance
                    leave_type = req["type"]
                    days = req["days"]
                    LEAVE_BALANCES[emp_id][leave_type]["used"] += days
                    LEAVE_BALANCES[emp_id][leave_type]["remaining"] -= days
                    
                    logger.info(f"✅ Leave request {request_id} approved")
                    
                    return {
                        "request_id": request_id,
                        "status": "approved",
                        "message": "Leave request approved successfully"
                    }
        
        raise HTTPException(status_code=404, detail="Leave request not found")
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    """Log startup information"""
    logger.info("=" * 50)
    logger.info("🚀 Leave Management Agent Starting Up")
    logger.info("=" * 50)
    logger.info(f"OpenAI API: {'✅ Configured' if OPENAI_API_KEY else '❌ Missing'}")
    logger.info(f"Employees tracked: {len(LEAVE_BALANCES)}")
    logger.info("=" * 50)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8004))
    uvicorn.run(app, host="0.0.0.0", port=port)
