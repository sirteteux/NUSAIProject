# 🚀 Quick Start - HR Microservices

## ⚡ 5-Minute Setup
---------------------------------------------
### Prerequisites
```bash
✓ Docker & Docker Compose installed
✓ 8GB+ RAM
✓ OpenAI API Key
---------------------------------------------
### Step 1: Create Environment File
cd hr-microservices

# Copy example
cp .env.example .env

----------------------------
SETTING UP .ENV
----------------------------
Place the .env in your services folder and HR-Microservices folder

----------------------------
Configuration
----------------------------
Go to your services\coordinator-service
Edit requirements.txt to below:
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic>=2.5.3
python-dotenv==1.0.0
openai==1.12.0
httpx>=0.27,<0.28

---------------------------
INSTALLATION
---------------------------
cd frontend
npm install
Open new terminal and cd services\api-gateway
npm install
Open new terminal and cd services\auth-service
npm install
cd services\coordinator-service
pip install -r requirements.txt
pip install pytest pytest-asyncio
Do testing by running "python -m pytest tests/"
Open new terminal
Run "docker-compose up -d"

# This starts:
# - MongoDB (database)
# - Redis (cache)
# - API Gateway (:8000)
# - 7 Microservices (:8001-8007)
# - Frontend (:3000)
-------------------------------------------------
### Step 3: Wait for Services (2-3 minutes)
# Watch logs
docker-compose logs -f

# Or check status
docker-compose ps
--------------------------------------------------
### Step 4: Verify Everything Works
```bash
# Check API Gateway
curl http://localhost:8000/health

# Check all services
curl http://localhost:8000/health/services

# Should see all services "healthy"
---------------------------------------------
### Step 5: Access the Application
Open browser: http://localhost:3000

Default login:
Email: admin@example.com
Password: admin123
-------------------------------------------------

## 🎯 Service Ports

| Service | Port | URL |
|---------|------|-----|
| **Frontend** | 3000 | http://localhost:3000 |
| **API Gateway** | 8000 | http://localhost:8000 |
| **Auth Service** | 8001 | http://localhost:8001 |
| **FAQ Service** | 8002 | http://localhost:8002 |
| **Payroll Service** | 8003 | http://localhost:8003 |
| **Leave Service** | 8004 | http://localhost:8004 |
| **Recruitment Service** | 8005 | http://localhost:8005 |
| **Performance Service** | 8006 | http://localhost:8006 |
| **Coordinator Service** | 8007 | http://localhost:8007 |
| **MongoDB** | 27017 | mongodb://localhost:27017 |
| **Redis** | 6379 | redis://localhost:6379 |

-----------------------------------------------------------------------------------

## 🧪 Testing the System

### 1. Test API Gateway
```bash
curl http://localhost:8000/api/docs
-----------------------------------------------------------------------------------
### 2. Test Login
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "admin123"
  }'

Save the token from response!
-----------------------------------------------------------------------------------
### 3. Test Coordinator (with token)
TOKEN="your-token-here"

curl -X POST http://localhost:8000/api/coordinator/ask \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "What is my salary?",
    "employee_id": "EMP000001"
  }'
```
-----------------------------------------------------------------------------------
### 4. Test Direct FAQ Service
```bash
curl -X POST http://localhost:8000/api/faq/ask \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "question": "What are the working hours?"
  }'
```
-----------------------------------------------------------------------------------

## 📊 View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api-gateway
docker-compose logs -f faq-service
docker-compose logs -f auth-service

# Last 100 lines
docker-compose logs --tail=100 faq-service

# Since last 10 minutes
docker-compose logs --since=10m
```

---

## 🔄 Common Commands

### Restart a Service
```bash
docker-compose restart faq-service
```

### Rebuild a Service
```bash
docker-compose up --build -d faq-service
```

### Stop All Services
```bash
docker-compose down
```

### Stop and Remove Everything (including data)
```bash
docker-compose down -v
```

### View Running Containers
```bash
docker-compose ps
```

### Check Resource Usage
```bash
docker stats
```

---

## 🐛 Troubleshooting

### Service Won't Start
```bash
# Check logs
docker-compose logs service-name

# Check if port is in use
netstat -an | grep 8000

# Restart service
docker-compose restart service-name
```

### Can't Connect to Database
```bash
# Check MongoDB is running
docker-compose ps mongodb

# Check MongoDB logs
docker-compose logs mongodb

# Restart MongoDB
docker-compose restart mongodb
```

### Gateway Can't Reach Service
```bash
# Check service is healthy
docker-compose ps

# Check network
docker network inspect hr-microservices-network

# Test service directly
curl http://localhost:8002/health
```

### Frontend Can't Connect
```bash
# Check API Gateway is running
curl http://localhost:8000/health

# Check frontend logs
docker-compose logs frontend

# Check browser console for errors
```

-----------------------------------------------------------------------------------

## 📁 Project Structure

```
hr-microservices/
├── services/
│   ├── api-gateway/        # Port 8000 - Entry point
│   ├── auth-service/       # Port 8001 - Authentication
│   ├── faq-service/        # Port 8002 - FAQ AI
│   ├── payroll-service/    # Port 8003 - Payroll AI
│   ├── leave-service/      # Port 8004 - Leave AI
│   ├── recruitment-service/# Port 8005 - Recruitment AI
│   ├── performance-service/# Port 8006 - Performance AI
│   └── coordinator-service/# Port 8007 - Multi-agent
│
├── frontend/               # Port 3000 - React app
├── infrastructure/         # K8s configs
├── scripts/               # Helper scripts
├── docker-compose.yml     # All services
└── .env                   # Configuration
```

-----------------------------------------------------------------------------------

## 🎓 Next Steps

1. ✅ **Explore the UI**
   - Login at http://localhost:3000
   - Try "Ask Anything" feature
   - Test different queries

2. ✅ **Test Different Services**
   - FAQ: "What are the company policies?"
   - Payroll: "What is my salary?"
   - Leave: "How many vacation days do I have?"
   - Recruitment: "What jobs are available?"
   - Performance: "What are my goals?"

3. ✅ **Monitor Services**
   - Check health: http://localhost:8000/health/services
   - View logs: `docker-compose logs -f`

4. ✅ **Read Documentation**
   - README.md - Full documentation
   - MICROSERVICES-ARCHITECTURE.md - Architecture details
   - MONOLITH-VS-MICROSERVICES.md - Comparison

5. ✅ **Customize**
   - Add your own data
   - Modify services
   - Add new features

-----------------------------------------------------------------------------------

## 🆘 Get Help

### Check Documentation
- `README.md` - Main documentation
- `MICROSERVICES-ARCHITECTURE.md` - Architecture guide
- `MONOLITH-VS-MICROSERVICES.md` - Migration info

### Common Issues
1. **Services unhealthy** → Wait 2-3 minutes for startup
2. **Port conflicts** → Stop other Docker containers
3. **Out of memory** → Increase Docker memory to 8GB+
4. **OpenAI errors** → Check your API key in `.env`

### Debug Mode
```bash
# Start with verbose logging
docker-compose up

# Check specific service
docker-compose up faq-service

# Check service health
curl http://localhost:8002/health
```

-----------------------------------------------------------------------------------

## ✅ Success Checklist

After setup, you should have:

- [ ] All services running (`docker-compose ps`)
- [ ] API Gateway responding (`curl localhost:8000/health`)
- [ ] All services healthy (`curl localhost:8000/health/services`)
- [ ] Frontend accessible (http://localhost:3000)
- [ ] Can login with admin credentials
- [ ] Can ask questions via Coordinator
- [ ] All logs showing no errors

-----------------------------------------------------------------------------------

**You're now running a production-grade microservices architecture! 🎉**

**Next:** Deploy to AWS or Kubernetes for full production setup!
