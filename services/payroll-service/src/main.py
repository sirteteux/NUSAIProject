"""
Payroll Agent - Salary and Compensation Assistant
Handles payroll queries, payslip generation, and salary information using OpenAI
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
    title="Payroll Agent",
    description="Salary and Compensation Assistant",
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
class PayrollQueryRequest(BaseModel):
    query: str
    employee_id: Optional[str] = None

class PayrollQueryResponse(BaseModel):
    answer: str
    data: Optional[Dict] = None

class PayslipRequest(BaseModel):
    employee_id: str
    month: Optional[str] = None
    year: Optional[int] = None

class PayslipResponse(BaseModel):
    employee_id: str
    employee_name: str
    month: str
    year: int
    gross_salary: float
    deductions: Dict[str, float]
    net_salary: float
    payment_date: str

# Mock employee database (In production, this would be MongoDB)
EMPLOYEE_DATA = {
    "EMP000001": {
        "name": "Admin User",
        "email": "admin@example.com",
        "department": "Administration",
        "position": "Administrator",
        "monthly_salary": 8000,
        "annual_salary": 96000,
        "currency": "SGD",
        "join_date": "2020-01-15",
        "tax_rate": 0.20,
        "cpf_rate": 0.20,
        "insurance": 200
    },
    "EMP000002": {
        "name": "John Doe",
        "email": "john@example.com",
        "department": "Engineering",
        "position": "Senior Developer",
        "monthly_salary": 7500,
        "annual_salary": 90000,
        "currency": "SGD",
        "join_date": "2021-03-10",
        "tax_rate": 0.18,
        "cpf_rate": 0.20,
        "insurance": 200
    }
}

# System prompt for payroll queries
PAYROLL_SYSTEM_PROMPT = """You are a helpful Payroll Assistant. You help employees with:
- Salary information and breakdowns
- Payslip queries
- Tax and deduction questions
- Bonus and allowance information
- Payment schedules
- Salary history

Be professional, accurate, and friendly. If you need specific employee data to answer, 
let the user know you'll need their employee ID.

When providing salary information, always format currency as SGD (Singapore Dollars).
"""

def calculate_payslip(employee_id: str, month: str = None, year: int = None) -> Dict:
    """Calculate payslip for an employee"""
    
    if employee_id not in EMPLOYEE_DATA:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    emp = EMPLOYEE_DATA[employee_id]
    
    # Use current month/year if not provided
    if not month or not year:
        now = datetime.now()
        month = now.strftime("%B")
        year = now.year
    
    # Calculate deductions
    gross = emp["monthly_salary"]
    tax = gross * emp["tax_rate"]
    cpf = gross * emp["cpf_rate"]
    insurance = emp["insurance"]
    
    total_deductions = tax + cpf + insurance
    net_salary = gross - total_deductions
    
    # Payment date (last day of month)
    payment_date = f"{year}-{datetime.strptime(month, '%B').month:02d}-25"
    
    return {
        "employee_id": employee_id,
        "employee_name": emp["name"],
        "department": emp["department"],
        "position": emp["position"],
        "month": month,
        "year": year,
        "gross_salary": gross,
        "deductions": {
            "income_tax": tax,
            "cpf": cpf,
            "insurance": insurance,
            "total": total_deductions
        },
        "net_salary": net_salary,
        "currency": emp["currency"],
        "payment_date": payment_date
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "payroll-agent",
        "version": "1.0.0",
        "openai_status": "configured" if OPENAI_API_KEY else "missing"
    }

@app.post("/api/payroll/query", response_model=PayrollQueryResponse)
async def query_payroll(request: PayrollQueryRequest):
    """
    Answer payroll-related questions using AI
    """
    try:
        logger.info(f"📥 Payroll query: {request.query}")
        
        if not client:
            raise HTTPException(status_code=500, detail="OpenAI not configured")
        
        # Get employee context if employee_id provided
        employee_context = ""
        employee_data = None
        
        if request.employee_id and request.employee_id in EMPLOYEE_DATA:
            emp = EMPLOYEE_DATA[request.employee_id]
            employee_data = emp
            employee_context = f"""
Employee Information:
- Name: {emp['name']}
- Department: {emp['department']}
- Position: {emp['position']}
- Monthly Salary: {emp['currency']} {emp['monthly_salary']:,.2f}
- Annual Salary: {emp['currency']} {emp['annual_salary']:,.2f}
- Join Date: {emp['join_date']}
"""
        
        # Construct messages
        messages = [
            {"role": "system", "content": PAYROLL_SYSTEM_PROMPT},
        ]
        
        if employee_context:
            messages.append({"role": "system", "content": employee_context})
        
        messages.append({"role": "user", "content": request.query})
        
        # Call OpenAI
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=500
        )
        
        answer = response.choices[0].message.content.strip()
        
        logger.info(f"✅ Generated payroll response")
        
        return PayrollQueryResponse(
            answer=answer,
            data=employee_data
        )
        
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/payroll/payslip", response_model=PayslipResponse)
async def get_payslip(request: PayslipRequest):
    """
    Generate payslip for an employee
    """
    try:
        logger.info(f"📄 Generating payslip for {request.employee_id}")
        
        payslip = calculate_payslip(
            request.employee_id,
            request.month,
            request.year
        )
        
        return PayslipResponse(**payslip)
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"❌ Error generating payslip: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/payroll/payslip/{employee_id}")
async def get_payslip_by_id(employee_id: str, month: str = None, year: int = None):
    """
    Get payslip for employee (GET endpoint for compatibility)
    """
    try:
        payslip = calculate_payslip(employee_id, month, year)
        return payslip
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/payroll/history/{employee_id}")
async def get_salary_history(employee_id: str, months: int = 6):
    """
    Get salary payment history for employee
    """
    try:
        if employee_id not in EMPLOYEE_DATA:
            raise HTTPException(status_code=404, detail="Employee not found")
        
        emp = EMPLOYEE_DATA[employee_id]
        history = []
        
        # Generate last N months of history
        now = datetime.now()
        for i in range(months):
            month_date = datetime(now.year, now.month - i, 1) if now.month > i else datetime(now.year - 1, 12 - (i - now.month), 1)
            month_name = month_date.strftime("%B")
            year = month_date.year
            
            payslip = calculate_payslip(employee_id, month_name, year)
            history.append({
                "month": month_name,
                "year": year,
                "gross": payslip["gross_salary"],
                "net": payslip["net_salary"],
                "payment_date": payslip["payment_date"]
            })
        
        return {
            "employee_id": employee_id,
            "employee_name": emp["name"],
            "history": history
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    """Log startup information"""
    logger.info("=" * 50)
    logger.info("🚀 Payroll Agent Starting Up")
    logger.info("=" * 50)
    logger.info(f"OpenAI API: {'✅ Configured' if OPENAI_API_KEY else '❌ Missing'}")
    logger.info(f"Employees in DB: {len(EMPLOYEE_DATA)}")
    logger.info("=" * 50)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8003))
    uvicorn.run(app, host="0.0.0.0", port=port)
