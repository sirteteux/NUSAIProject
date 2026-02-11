# HR Microservices - Simplified Authentication

## ✅ What Changed

**Removed:** Separate `auth-service` (port 8001)  
**Now:** Authentication integrated directly into **API Gateway** (port 8000)

This makes login work exactly like your Phase 5 monolith - simple and straightforward!

---

## 🏗️ Architecture

```
┌─────────────┐
│  Frontend   │
│   :3000     │
└──────┬──────┘
       │
       ↓
┌────────────────────────────────┐
│   API Gateway :8000            │
│   (Auth Built-in)              │
│   - Login/Register             │
│   - User Management            │
│   - Routes to AI Services      │
└───┬──┬──┬──┬──┬──┬────────────┘
    │  │  │  │  │  │
    ↓  ↓  ↓  ↓  ↓  ↓
  ┌──┐┌──┐┌──┐┌──┐┌──┐┌────┐
  │FQ││Py││Lv││Rc││Pf││Cord│
  │02││03││04││05││06││8007│
  └──┘└──┘└──┘└──┘└──┘└────┘
    │  │  │  │  │  │    │
    └──┴──┴──┴──┴──┴────┘
               │
               ↓
    ┌────────────────────┐
    │  MongoDB Atlas     │
    │  (Shared Database) │
    └────────────────────┘
```

---

## 🚀 Quick Start

### 1. Setup Environment

```bash
cd hr-microservices-no-auth

# Copy template
cp .env.example .env

# Edit with your credentials
nano .env
```

Add:
```bash
OPENAI_API_KEY=sk-your-key-here
MONGODB_URI=mongodb+srv://admin:pass1234@resourcefulaicluster.o1bby2h.mongodb.net/?appName=ResourcefulAICluster
JWT_SECRET=your-secret-key
```

### 2. Start Services

```bash
# Build and start
docker-compose build
docker-compose up -d

# Wait 2 minutes
sleep 120

# Check status
docker-compose ps
```

### 3. Login

```
http://localhost:3000

Email: admin@example.com
Password: admin123
```

**That's it!** Login works exactly like your Phase 5 monolith! 🎉

---

## 📊 Services Overview

| Service | Port | Purpose |
|---------|------|---------|
| **API Gateway** | 8000 | Auth + Routing (combined!) |
| FAQ Service | 8002 | HR questions |
| Payroll Service | 8003 | Salary queries |
| Leave Service | 8004 | Leave management |
| Recruitment Service | 8005 | Job openings |
| Performance Service | 8006 | Reviews |
| Coordinator Service | 8007 | Multi-agent routing |
| Frontend | 3000 | React app |
| Redis | 6379 | Caching |

**No more auth-service on port 8001!**

---

## ✅ Benefits

1. ✅ **Simpler** - One less service to manage
2. ✅ **Faster Login** - No extra network hop
3. ✅ **Just Like Monolith** - Same login flow as Phase 5
4. ✅ **Same MongoDB** - Your Atlas database
5. ✅ **Less Memory** - One fewer container

---

## 🔍 How It Works

### Before (Separate Auth Service):
```
Frontend → Gateway → Auth Service → MongoDB
```

### Now (Integrated):
```
Frontend → Gateway (Auth Built-in) → MongoDB
```

**Login is handled directly in the API Gateway!**

---

## 🧪 Test It

```bash
# Health check
curl http://localhost:8000/health

# Test login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}'

# Should return token immediately
```

---

## 📋 Environment Variables

Required in `.env`:

```bash
OPENAI_API_KEY=sk-...                    # Your OpenAI key
MONGODB_URI=mongodb+srv://admin:pass...  # Your Atlas URI
JWT_SECRET=your-secret                    # Any secure string
```

---

## 🔒 Authentication Flow

1. **User enters credentials** at `http://localhost:3000/login`
2. **Frontend sends POST** to `http://localhost:8000/api/auth/login`
3. **API Gateway**:
   - Queries MongoDB for user
   - Verifies password
   - Generates JWT token
   - Returns token to frontend
4. **Frontend** stores token in localStorage
5. **All subsequent requests** include token in header
6. **API Gateway** validates token before proxying to AI services

---

## 📁 What's Different

### Removed:
- ❌ `services/auth-service/` folder
- ❌ Auth service container (port 8001)
- ❌ Separate auth database connection

### Updated:
- ✅ `services/api-gateway/src/server.js` - Now handles auth
- ✅ `services/api-gateway/package.json` - Added mongoose, bcrypt, jwt
- ✅ `docker-compose.yml` - Removed auth-service
- ✅ API Gateway connects directly to MongoDB

---

## 🔧 Common Commands

```bash
# View logs
docker-compose logs -f

# Restart gateway
docker-compose restart api-gateway

# Rebuild gateway
docker-compose build --no-cache api-gateway
docker-compose up -d api-gateway

# Check database
docker-compose logs api-gateway | grep MongoDB
```

---

## 🆘 Troubleshooting

### Login Not Working?

```bash
# Check gateway logs
docker-compose logs api-gateway | tail -50

# Look for:
# ✓ Connected to MongoDB Atlas (shared database)
# ✓ Admin user seeded (admin@example.com / admin123)
```

### Can't Connect to MongoDB?

1. Check MongoDB Atlas Network Access
2. Verify MONGODB_URI in .env
3. Test connection:
   ```bash
   docker-compose logs api-gateway | grep "Connected to MongoDB"
   ```

---

## ✅ Success Checklist

- [ ] Only 7 services running (no auth-service)
- [ ] API Gateway shows "Connected to MongoDB"
- [ ] Admin user seeded message in logs
- [ ] Can login at http://localhost:3000
- [ ] Token returned from /api/auth/login

---

## 📚 Documentation

- **This README** - Quick start
- **SETUP-ATLAS.md** - MongoDB Atlas setup
- **TROUBLESHOOTING.md** - Common issues
- **LOGIN-FIX.md** - Login problems

---
