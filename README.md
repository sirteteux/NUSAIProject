# HR Agentic AI - Microservices Architecture

## 🏗️ Architecture Overview

**From Monolith to Microservices**

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                            │
│                      (React + Vite)                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌──────────────────────────────────────────────────────────────┐
│                     API Gateway :8000                         │
│            (Routing, Auth, Rate Limiting)                     │
└────┬────┬────┬────┬────┬────┬────┬──────────────────────────┘
     │    │    │    │    │    │    │
     ↓    ↓    ↓    ↓    ↓    ↓    ↓
┌────────────────────────────────────────────────────────────┐
│  Auth    FAQ  Payroll Leave  Recruit Performance  Coord   │
│  :8001  :8002  :8003  :8004  :8005    :8006      :8007   │
└────┬────┬────┬────┬────┬────┬────┬────────────────────────┘
     │    │    │    │    │    │    │
     ↓    ↓    ↓    ↓    ↓    ↓    ↓
┌──────────────────────────────────────────────────────────┐
│         MongoDB (per-service databases)                  │
│  auth_db | faq_db | payroll_db | leave_db | ...         │
└──────────────────────────────────────────────────────────┘
```

---

## 🎯 Key Differences from Monolith

| Aspect | Monolith (Phase 5) | Microservices (Phase 6) |
|--------|-------------------|-------------------------|
| **Architecture** | Single backend | 7 independent services + Gateway |
| **Database** | Shared MongoDB | Separate DB per service |
| **Scaling** | Scale entire backend | Scale individual services |
| **Deployment** | Deploy everything | Deploy services independently |
| **Failure** | Single point of failure | Isolated failures |
| **Technology** | Locked to Node.js | Mix Node.js + Python |
| **Ports** | Backend: 4000 | Gateway: 8000, Services: 8001-8007 |

---

## 📦 Services Breakdown

### 1. API Gateway (:8000)
- **Tech:** Node.js + Express
- **Purpose:** Single entry point for all requests
- **Features:**
  - Request routing
  - Authentication validation
  - Rate limiting
  - Service health aggregation
  - Load balancing

### 2. Auth Service (:8001)
- **Tech:** Node.js + MongoDB
- **Database:** `auth_db`
- **Responsibilities:**
  - User registration/login
  - JWT token generation
  - Password hashing
  - User profile management

### 3. FAQ Service (:8002)
- **Tech:** Python + FastAPI + OpenAI
- **Database:** `faq_db`
- **Responsibilities:**
  - FAQ AI agent
  - Question categorization
  - Content management

### 4. Payroll Service (:8003)
- **Tech:** Python + FastAPI + OpenAI
- **Database:** `payroll_db`
- **Responsibilities:**
  - Salary queries via AI
  - Payslip generation
  - Compensation calculations

### 5. Leave Service (:8004)
- **Tech:** Python + FastAPI + OpenAI
- **Database:** `leave_db`
- **Responsibilities:**
  - Leave balance tracking
  - Leave requests via AI
  - Approval workflows

### 6. Recruitment Service (:8005)
- **Tech:** Python + FastAPI + OpenAI
- **Database:** `recruitment_db`
- **Responsibilities:**
  - Job posting management
  - Candidate screening via AI
  - Interview coordination

### 7. Performance Service (:8006)
- **Tech:** Python + FastAPI + OpenAI
- **Database:** `performance_db`
- **Responsibilities:**
  - Goal tracking
  - Performance reviews via AI
  - KPI management

### 8. Coordinator Service (:8007)
- **Tech:** Python + FastAPI + LangChain + Redis
- **Cache:** Redis
- **Responsibilities:**
  - Intelligent query routing
  - Multi-agent orchestration
  - Context management

---

## 🚀 Quick Start

### Prerequisites
```bash
- Docker & Docker Compose
- OpenAI API Key
- 8GB+ RAM
```

### 1. Clone and Setup
```bash
cd hr-microservices

# Create .env file
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### 2. Start All Services
```bash
# Build and start all microservices
docker-compose up --build -d

# Wait for services to be healthy (2-3 minutes)
docker-compose ps
```

### 3. Verify Services
```bash
# Check API Gateway
curl http://localhost:8000/health

# Check all services health
curl http://localhost:8000/health/services

# Check individual services
curl http://localhost:8001/health  # Auth
curl http://localhost:8002/health  # FAQ
curl http://localhost:8003/health  # Payroll
curl http://localhost:8004/health  # Leave
curl http://localhost:8005/health  # Recruitment
curl http://localhost:8006/health  # Performance
curl http://localhost:8007/health  # Coordinator
```

### 4. Access Frontend
```
http://localhost:3000
```

---

## 🔄 Migration from Monolith

### Automated Migration Script

```bash
# Run migration script
./scripts/migrate-from-monolith.sh /path/to/hr-phase5

# This will:
# 1. Copy agent code to appropriate services
# 2. Split backend routes into services
# 3. Update frontend API calls
# 4. Configure docker-compose
```

### Manual Migration Steps

1. **Copy AI Agents**
   ```bash
   # FAQ
   cp -r ../hr-phase5/agents/faq/* services/faq-service/
   
   # Payroll
   cp -r ../hr-phase5/agents/payroll/* services/payroll-service/
   
   # Repeat for all agents...
   ```

2. **Update Service Ports**
   - Update each agent's main.py to use new ports (8002-8007)

3. **Update Frontend**
   - Change API calls from `http://localhost:4000` to `http://localhost:8000`
   - All routes now go through API Gateway

4. **Update Environment Variables**
   - Each service has its own DATABASE_URL
   - Services communicate via service names (not localhost)

---

## 🛠️ Development

### Start Single Service
```bash
# Start just Auth service + dependencies
docker-compose up mongodb redis auth-service
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f faq-service
docker-compose logs -f api-gateway
```

### Rebuild Service
```bash
# Rebuild and restart specific service
docker-compose up --build -d faq-service
```

### Hot Reload (Development)
```bash
# Use dev docker-compose with volume mounts
docker-compose -f docker-compose.dev.yml up
```

---

## 📡 API Usage

### Through API Gateway

All requests now go through the gateway:

```javascript
// OLD (Monolith)
POST http://localhost:4000/api/faq/ask

// NEW (Microservices)
POST http://localhost:8000/api/faq/ask
```

### Authentication Flow

```
1. User Login
   POST /api/auth/login
   ↓
2. Receive JWT Token
   {token: "eyJ..."}
   ↓
3. Use Token in Headers
   Authorization: Bearer eyJ...
   ↓
4. Gateway validates and routes
   ↓
5. Service receives request
```

### Example Requests

```bash
# 1. Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}'

# 2. Use Coordinator (with token)
curl -X POST http://localhost:8000/api/coordinator/ask \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"query":"What is my salary?"}'

# 3. Direct FAQ query
curl -X POST http://localhost:8000/api/faq/ask \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"question":"What are the working hours?"}'
```

---

## 🔒 Security

### Service-to-Service Communication
- Services communicate via private Docker network
- No external exposure except through Gateway
- Each service validates JWT independently

### API Gateway Security
- Rate limiting: 100 requests/15 min per IP
- CORS configuration
- Helmet.js security headers
- Request/Response logging with IDs

### Database Isolation
- Each service has separate database
- No cross-service database access
- Database credentials per service

---

## 📊 Monitoring & Observability

### Health Checks
```bash
# Overall health
curl http://localhost:8000/health

# All services health
curl http://localhost:8000/health/services

# Individual service
curl http://localhost:8002/health
```

### Logs
```bash
# View all logs
docker-compose logs -f

# Filter by service
docker-compose logs -f api-gateway
docker-compose logs -f coordinator-service

# Filter by time
docker-compose logs --since 10m
```

### Metrics (Future Enhancement)
- Prometheus for metrics collection
- Grafana for visualization
- Jaeger for distributed tracing

---

## 🧪 Testing

### Integration Tests
```bash
# Test API Gateway routing
npm run test:gateway

# Test Auth Service
cd services/auth-service && npm test

# Test FAQ Service
cd services/faq-service && pytest
```

### Load Testing
```bash
# Install k6
# Run load test
k6 run tests/load/gateway-load-test.js
```

---

## 📈 Scaling

### Horizontal Scaling
```yaml
# Scale specific service
docker-compose up --scale payroll-service=3 -d

# Kubernetes
kubectl scale deployment/payroll-service --replicas=5
```

### Auto-scaling (Kubernetes)
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: payroll-service-hpa
spec:
  scaleTargetRef:
    kind: Deployment
    name: payroll-service
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
```

---

## 🐛 Troubleshooting

### Service Won't Start
```bash
# Check logs
docker-compose logs service-name

# Check dependencies
docker-compose ps

# Rebuild
docker-compose up --build service-name
```

### Gateway Can't Reach Service
```bash
# Check network
docker network inspect hr-microservices-network

# Test service directly
curl http://localhost:8002/health
```

### Database Connection Issues
```bash
# Check MongoDB
docker-compose logs mongodb

# Check connection string in service
docker-compose exec faq-service env | grep DATABASE_URL
```

---

## 📁 Project Structure

```
hr-microservices/
├── README.md (this file)
├── docker-compose.yml
├── docker-compose.dev.yml
├── .env.example
├── MICROSERVICES-ARCHITECTURE.md
│
├── services/
│   ├── api-gateway/
│   │   ├── Dockerfile
│   │   ├── package.json
│   │   └── src/
│   │       └── server.js
│   │
│   ├── auth-service/
│   ├── faq-service/
│   ├── payroll-service/
│   ├── leave-service/
│   ├── recruitment-service/
│   ├── performance-service/
│   └── coordinator-service/
│
├── frontend/
│   └── src/
│       └── services/
│           └── api.js  # Updated to use Gateway
│
├── infrastructure/
│   ├── kubernetes/
│   └── monitoring/
│
└── scripts/
    └── migrate-from-monolith.sh
```

---

## 🎯 Benefits Achieved

✅ **Independent Scaling** - Scale services based on demand  
✅ **Fault Isolation** - One service failure doesn't break others  
✅ **Technology Flexibility** - Use best tool for each service  
✅ **Independent Deployment** - Deploy services separately  
✅ **Team Autonomy** - Teams own specific services  
✅ **Better Performance** - Optimized per service  
✅ **Easier Maintenance** - Smaller, focused codebases  

---

## 🚀 Next Steps

1. ✅ Review architecture
2. ✅ Start services with `docker-compose up`
3. ✅ Test API Gateway routing
4. ✅ Migrate frontend API calls
5. ⬜ Add Prometheus monitoring
6. ⬜ Implement service mesh (Istio)
7. ⬜ Deploy to Kubernetes
8. ⬜ Add distributed tracing

---

## 📞 Support

- Architecture questions: See MICROSERVICES-ARCHITECTURE.md
- Migration help: See scripts/migrate-from-monolith.sh
- Deployment: See infrastructure/kubernetes/

---

**Microservices Architecture - Production Ready! 🚀**
