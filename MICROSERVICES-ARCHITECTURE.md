# HR Agentic AI - Microservices Architecture

## 🏗️ Restructuring Plan: Monolith → Microservices

### Current Structure (Monolithic Backend)
```
hr-phase5/
├── agents/               # 6 AI agents (already separate services)
│   ├── coordinator/
│   ├── faq/
│   ├── payroll/
│   ├── leave-management/
│   ├── recruitment/
│   └── performance/
├── backend/             # ❌ MONOLITHIC - Single backend for all
│   ├── src/routes/      # All routes in one service
│   ├── src/models/      # All models in one database
│   └── src/config/
└── frontend/            # Single frontend

Problems:
- Backend is a single point of failure
- All routes and models tightly coupled
- Shared database schema
- Can't scale individual services
- Deploy all or nothing
```

### New Structure (Microservices)
```
hr-microservices/
├── services/
│   ├── api-gateway/           # NEW - Entry point, routing
│   ├── auth-service/          # NEW - Authentication & users
│   ├── faq-service/           # AI agent + business logic
│   ├── payroll-service/       # AI agent + business logic
│   ├── leave-service/         # AI agent + business logic
│   ├── recruitment-service/   # AI agent + business logic
│   ├── performance-service/   # AI agent + business logic
│   └── coordinator-service/   # AI routing + orchestration
├── frontend/
├── infrastructure/
│   ├── docker-compose.yml
│   ├── kubernetes/
│   └── monitoring/
└── shared/
    ├── proto/                 # gRPC schemas
    └── libraries/             # Shared code

Benefits:
✅ Each service independently deployable
✅ Separate databases per service
✅ Technology flexibility
✅ Better scalability
✅ Fault isolation
✅ Team autonomy
```

---

## 📊 Microservices Breakdown

### 1. API Gateway
**Purpose:** Single entry point, routing, authentication
**Tech:** Node.js + Express + Kong/Nginx
**Port:** 8000
**Responsibilities:**
- Route requests to appropriate services
- JWT validation
- Rate limiting
- API versioning
- Load balancing

### 2. Auth Service
**Purpose:** User management, authentication
**Tech:** Node.js + MongoDB
**Port:** 8001
**Database:** auth_db
**Responsibilities:**
- User registration/login
- JWT token generation
- Password management
- User profiles

### 3. FAQ Service
**Purpose:** General HR questions
**Tech:** Python + FastAPI + OpenAI + PostgreSQL
**Port:** 8002
**Database:** faq_db
**Responsibilities:**
- FAQ AI agent
- FAQ content management
- Search and categorization

### 4. Payroll Service
**Purpose:** Salary and compensation
**Tech:** Python + FastAPI + OpenAI + PostgreSQL
**Port:** 8003
**Database:** payroll_db
**Responsibilities:**
- Payroll AI agent
- Salary calculations
- Payslip generation
- Compensation data

### 5. Leave Service
**Purpose:** Leave management
**Tech:** Python + FastAPI + OpenAI + PostgreSQL
**Port:** 8004
**Database:** leave_db
**Responsibilities:**
- Leave AI agent
- Leave requests
- Balance tracking
- Approval workflows

### 6. Recruitment Service
**Purpose:** Hiring and recruitment
**Tech:** Python + FastAPI + OpenAI + PostgreSQL
**Port:** 8005
**Database:** recruitment_db
**Responsibilities:**
- Recruitment AI agent
- Job postings
- Candidate management
- Interview scheduling

### 7. Performance Service
**Purpose:** Performance management
**Tech:** Python + FastAPI + OpenAI + PostgreSQL
**Port:** 8006
**Database:** performance_db
**Responsibilities:**
- Performance AI agent
- Goal tracking
- Reviews
- KPI management

### 8. Coordinator Service
**Purpose:** Multi-agent orchestration
**Tech:** Python + FastAPI + LangChain + Redis
**Port:** 8007
**Database:** Redis (caching)
**Responsibilities:**
- Intelligent routing
- Agent coordination
- Context management

---

## 🗄️ Database Strategy

### Option 1: Database per Service (Recommended)
```
auth_db          → Auth Service
faq_db           → FAQ Service
payroll_db       → Payroll Service
leave_db         → Leave Service
recruitment_db   → Recruitment Service
performance_db   → Performance Service
coordinator_cache → Coordinator (Redis)
```

### Option 2: Shared Database with Schemas
```
hr_db
├── auth_schema
├── faq_schema
├── payroll_schema
├── leave_schema
├── recruitment_schema
└── performance_schema
```

**Recommendation:** Option 1 (true microservices isolation)

---

## 🔄 Communication Patterns

### 1. Synchronous (REST)
- Frontend ↔ API Gateway
- API Gateway ↔ Services
- Service ↔ Service (when needed)

### 2. Asynchronous (Message Queue)
- Event-driven updates
- Background jobs
- Notifications
**Tech:** RabbitMQ or Apache Kafka

### 3. Service Discovery
**Tech:** Consul or Kubernetes DNS

---

## 🚀 Migration Strategy

### Phase 1: Extract Services (Week 1)
1. Create API Gateway
2. Extract Auth Service
3. Update routes to use gateway

### Phase 2: Service Independence (Week 2)
1. Separate databases
2. Add service-to-service communication
3. Implement health checks

### Phase 3: Deployment (Week 3)
1. Docker Compose setup
2. Kubernetes manifests
3. CI/CD updates

### Phase 4: Optimization (Week 4)
1. Add caching (Redis)
2. Message queue integration
3. Monitoring and logging

---

## 📁 New Project Structure

```
hr-microservices/
├── README.md
├── docker-compose.yml
├── docker-compose.dev.yml
├── .env.example
│
├── services/
│   ├── api-gateway/
│   │   ├── Dockerfile
│   │   ├── package.json
│   │   ├── src/
│   │   │   ├── server.js
│   │   │   ├── routes/
│   │   │   ├── middleware/
│   │   │   └── config/
│   │   └── tests/
│   │
│   ├── auth-service/
│   │   ├── Dockerfile
│   │   ├── package.json
│   │   ├── src/
│   │   │   ├── server.js
│   │   │   ├── controllers/
│   │   │   ├── models/
│   │   │   ├── services/
│   │   │   └── routes/
│   │   ├── database/
│   │   └── tests/
│   │
│   ├── faq-service/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── api/
│   │   │   ├── services/
│   │   │   ├── models/
│   │   │   └── ai/
│   │   ├── database/
│   │   └── tests/
│   │
│   ├── payroll-service/
│   ├── leave-service/
│   ├── recruitment-service/
│   ├── performance-service/
│   └── coordinator-service/
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── services/
│       │   └── api/
│       │       ├── gateway.js      # All calls go through gateway
│       │       ├── auth.js
│       │       ├── faq.js
│       │       └── ...
│       └── ...
│
├── infrastructure/
│   ├── kubernetes/
│   │   ├── api-gateway.yaml
│   │   ├── auth-service.yaml
│   │   └── ...
│   ├── monitoring/
│   │   ├── prometheus/
│   │   └── grafana/
│   └── logging/
│       └── elasticsearch/
│
├── shared/
│   ├── proto/                # gRPC definitions (if using gRPC)
│   ├── libraries/
│   │   ├── logger/
│   │   ├── auth/
│   │   └── database/
│   └── config/
│
└── .github/
    └── workflows/
        ├── api-gateway.yml
        ├── auth-service.yml
        └── ...
```

---

## 🔧 Technology Stack

### API Gateway
- **Framework:** Express.js + express-gateway or Kong
- **Features:** Routing, rate limiting, caching
- **Port:** 8000

### Services
- **Auth:** Node.js + Express + MongoDB + JWT
- **AI Services:** Python + FastAPI + PostgreSQL + OpenAI
- **Coordinator:** Python + FastAPI + Redis + LangChain

### Infrastructure
- **Container Orchestration:** Kubernetes or Docker Swarm
- **Service Mesh:** Istio (optional)
- **Message Queue:** RabbitMQ or Kafka
- **Caching:** Redis
- **Monitoring:** Prometheus + Grafana
- **Logging:** ELK Stack (Elasticsearch, Logstash, Kibana)
- **Tracing:** Jaeger

---

## 🎯 Key Principles

1. **Single Responsibility:** Each service does one thing well
2. **Independent Deployment:** Deploy services independently
3. **Data Isolation:** Each service owns its data
4. **Fault Tolerance:** Circuit breakers, retries, fallbacks
5. **Observability:** Logging, metrics, tracing
6. **API Contracts:** Clear versioned APIs
7. **Security:** Service-to-service authentication

---

## 📈 Scalability

### Horizontal Scaling
```yaml
# Scale individual services based on load
kubectl scale deployment/payroll-service --replicas=5
kubectl scale deployment/faq-service --replicas=3
```

### Auto-scaling
```yaml
# HPA based on CPU/Memory
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: payroll-service-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: payroll-service
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

---

## 🔒 Security Enhancements

1. **Service-to-Service Auth:** mTLS or JWT
2. **API Gateway Auth:** OAuth 2.0 / JWT
3. **Network Policies:** Restrict service communication
4. **Secrets Management:** Kubernetes Secrets / Vault
5. **Rate Limiting:** Per service and user

---

## 📊 Monitoring & Observability

```
Logging:    All services → Fluentd → Elasticsearch → Kibana
Metrics:    Services → Prometheus → Grafana
Tracing:    Services → Jaeger
Alerting:   Prometheus → AlertManager → Slack/Email
Health:     Kubernetes Liveness/Readiness Probes
```

---

## 🚀 Next Steps

1. Review this architecture plan
2. Confirm technology choices
3. Start with API Gateway creation
4. Migrate one service at a time
5. Update CI/CD pipelines
6. Add monitoring and logging
7. Performance testing
8. Gradual rollout

---

**This microservices architecture provides:**
- ✅ Better scalability
- ✅ Independent deployments
- ✅ Fault isolation
- ✅ Technology flexibility
- ✅ Team autonomy
- ✅ Easier maintenance

Ready to start the migration?
