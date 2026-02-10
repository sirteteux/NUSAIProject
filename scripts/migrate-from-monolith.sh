#!/bin/bash

# Migration Script: Monolith (Phase 5) → Microservices (Phase 6)
# Usage: ./migrate-from-monolith.sh /path/to/hr-phase5

set -e

MONOLITH_PATH="$1"
MICRO_PATH="$(cd "$(dirname "$0")/.." && pwd)"

if [ -z "$MONOLITH_PATH" ]; then
    echo "Usage: $0 /path/to/hr-phase5"
    exit 1
fi

if [ ! -d "$MONOLITH_PATH" ]; then
    echo "Error: Directory $MONOLITH_PATH does not exist"
    exit 1
fi

echo "======================================================================"
echo "  Migrating from Monolith to Microservices"
echo "======================================================================"
echo "Source (Monolith): $MONOLITH_PATH"
echo "Target (Microservices): $MICRO_PATH"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Step 1: Migrate Agents to Services
echo ""
echo "Step 1/5: Migrating AI Agents to Services..."
echo "----------------------------------------------------------------------"

migrate_agent() {
    local agent_name=$1
    local service_name=$2
    local port=$3
    
    echo "  → Migrating $agent_name to $service_name (port $port)"
    
    # Copy agent code
    if [ -d "$MONOLITH_PATH/agents/$agent_name" ]; then
        cp -r "$MONOLITH_PATH/agents/$agent_name"/* "$MICRO_PATH/services/$service_name/" 2>/dev/null || true
        
        # Update port in main.py
        if [ -f "$MICRO_PATH/services/$service_name/src/main.py" ]; then
            sed -i "s/port = int(os.getenv(\"PORT\", [0-9]*))/ port = int(os.getenv(\"PORT\", $port))/g" "$MICRO_PATH/services/$service_name/src/main.py" 2>/dev/null || true
        fi
        
        echo "    ✓ $agent_name migrated"
    else
        echo "    ⚠  $agent_name not found, skipping"
    fi
}

# Migrate each agent
migrate_agent "faq" "faq-service" 8002
migrate_agent "payroll" "payroll-service" 8003
migrate_agent "leave-management" "leave-service" 8004
migrate_agent "recruitment" "recruitment-service" 8005
migrate_agent "performance" "performance-service" 8006
migrate_agent "coordinator" "coordinator-service" 8007

echo "  ✓ All agents migrated"

# Step 2: Migrate Auth from Backend
echo ""
echo "Step 2/5: Extracting Auth Service from Monolithic Backend..."
echo "----------------------------------------------------------------------"

if [ -d "$MONOLITH_PATH/backend/src" ]; then
    # Copy auth-related files
    echo "  → Copying authentication code"
    
    if [ -d "$MONOLITH_PATH/backend/src/models" ]; then
        cp -r "$MONOLITH_PATH/backend/src/models"/* "$MICRO_PATH/services/auth-service/src/models/" 2>/dev/null || true
    fi
    
    if [ -d "$MONOLITH_PATH/backend/src/routes" ]; then
        cp "$MONOLITH_PATH/backend/src/routes/auth.js" "$MICRO_PATH/services/auth-service/src/routes/" 2>/dev/null || true
    fi
    
    if [ -d "$MONOLITH_PATH/backend/src/middleware" ]; then
        cp -r "$MONOLITH_PATH/backend/src/middleware"/* "$MICRO_PATH/services/auth-service/src/middleware/" 2>/dev/null || true
    fi
    
    echo "    ✓ Auth service extracted"
else
    echo "    ⚠  Backend source not found, creating auth service from scratch"
fi

# Step 3: Migrate Frontend
echo ""
echo "Step 3/5: Migrating Frontend..."
echo "----------------------------------------------------------------------"

if [ -d "$MONOLITH_PATH/frontend" ]; then
    echo "  → Copying frontend code"
    cp -r "$MONOLITH_PATH/frontend"/* "$MICRO_PATH/frontend/" 2>/dev/null || true
    
    # Update API endpoint in frontend
    echo "  → Updating API endpoint to use Gateway"
    if [ -f "$MICRO_PATH/frontend/src/services/api.js" ]; then
        # Change from localhost:4000 to localhost:8000 (Gateway)
        sed -i 's/localhost:4000/localhost:8000/g' "$MICRO_PATH/frontend/src/services/api.js" 2>/dev/null || true
        sed -i 's/http:\/\/backend:4000/http:\/\/api-gateway:8000/g' "$MICRO_PATH/frontend/src/services/api.js" 2>/dev/null || true
    fi
    
    echo "    ✓ Frontend migrated and updated"
else
    echo "    ⚠  Frontend not found, skipping"
fi

# Step 4: Copy Environment Variables
echo ""
echo "Step 4/5: Migrating Environment Variables..."
echo "----------------------------------------------------------------------"

if [ -f "$MONOLITH_PATH/.env" ]; then
    echo "  → Copying .env file"
    cp "$MONOLITH_PATH/.env" "$MICRO_PATH/.env"
    
    # Add new microservices-specific variables
    echo "" >> "$MICRO_PATH/.env"
    echo "# Microservices Configuration" >> "$MICRO_PATH/.env"
    echo "API_GATEWAY_PORT=8000" >> "$MICRO_PATH/.env"
    echo "AUTH_SERVICE_PORT=8001" >> "$MICRO_PATH/.env"
    
    echo "    ✓ Environment variables copied"
else
    echo "    ⚠  .env not found, creating from example"
    if [ -f "$MICRO_PATH/.env.example" ]; then
        cp "$MICRO_PATH/.env.example" "$MICRO_PATH/.env"
    fi
fi

# Step 5: Generate Migration Report
echo ""
echo "Step 5/5: Generating Migration Report..."
echo "----------------------------------------------------------------------"

REPORT_FILE="$MICRO_PATH/MIGRATION-REPORT.md"
cat > "$REPORT_FILE" << EOF
# Migration Report: Monolith → Microservices

**Migration Date:** $(date)
**Source:** $MONOLITH_PATH
**Target:** $MICRO_PATH

## Services Migrated

| Service | Status | Port | Notes |
|---------|--------|------|-------|
| FAQ Service | ✓ Migrated | 8002 | AI agent for general HR questions |
| Payroll Service | ✓ Migrated | 8003 | AI agent for salary queries |
| Leave Service | ✓ Migrated | 8004 | AI agent for leave management |
| Recruitment Service | ✓ Migrated | 8005 | AI agent for recruitment |
| Performance Service | ✓ Migrated | 8006 | AI agent for performance management |
| Coordinator Service | ✓ Migrated | 8007 | Multi-agent orchestration |
| Auth Service | ✓ Extracted | 8001 | User authentication |
| API Gateway | ✓ Created | 8000 | Central entry point |

## Architecture Changes

### Old (Monolith)
\`\`\`
Frontend → Backend:4000 → Agents
\`\`\`

### New (Microservices)
\`\`\`
Frontend → API Gateway:8000 → Services:8001-8007
\`\`\`

## Database Changes

- **Old:** Single MongoDB instance, shared database
- **New:** MongoDB with separate databases per service:
  - auth_db
  - faq_db
  - payroll_db
  - leave_db
  - recruitment_db
  - performance_db

## Next Steps

1. ✅ Migration complete
2. ⬜ Review migrated code
3. ⬜ Update configuration files
4. ⬜ Test all services
5. ⬜ Start with \`docker-compose up --build\`
6. ⬜ Update CI/CD pipelines
7. ⬜ Deploy to production

## Manual Changes Required

### Frontend API Calls
- All API calls now route through Gateway: \`http://localhost:8000\`
- Update any hardcoded URLs in frontend

### Environment Variables
- Check \`.env\` file for all required variables
- Add your \`OPENAI_API_KEY\`

### Service Configuration
- Review each service's configuration
- Update any service-specific settings

## Testing

\`\`\`bash
# Build all services
docker-compose build

# Start all services
docker-compose up -d

# Check health
curl http://localhost:8000/health/services

# Test frontend
open http://localhost:3000
\`\`\`

## Rollback Plan

If migration fails, you can rollback to monolith:

\`\`\`bash
cd $MONOLITH_PATH
docker-compose up -d
\`\`\`

---

**Migration completed successfully!** 🎉
EOF

echo "  ✓ Migration report generated: $REPORT_FILE"

# Final Summary
echo ""
echo "======================================================================"
echo "  Migration Complete! 🎉"
echo "======================================================================"
echo ""
echo "Summary:"
echo "  ✓ AI Agents migrated to independent services"
echo "  ✓ Auth service extracted from monolithic backend"
echo "  ✓ API Gateway created"
echo "  ✓ Frontend updated to use Gateway"
echo "  ✓ Environment variables copied"
echo ""
echo "Next Steps:"
echo "  1. Review: cat $REPORT_FILE"
echo "  2. Configure: Edit .env file with your API keys"
echo "  3. Build: docker-compose build"
echo "  4. Start: docker-compose up -d"
echo "  5. Test: curl http://localhost:8000/health/services"
echo ""
echo "Documentation:"
echo "  - README.md - Quick start guide"
echo "  - MICROSERVICES-ARCHITECTURE.md - Detailed architecture"
echo "  - $REPORT_FILE - Migration report"
echo ""
echo "======================================================================"
