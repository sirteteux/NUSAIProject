#!/bin/bash

# Microservices Troubleshooting Script
# Diagnoses and fixes common startup issues

echo "======================================================================"
echo "  HR Microservices - Troubleshooting"
echo "======================================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check 1: .env file exists
echo "Check 1: Environment File"
echo "----------------------------------------------------------------------"
if [ -f .env ]; then
    echo -e "${GREEN}✓${NC} .env file exists"
    
    # Check for OpenAI key
    if grep -q "OPENAI_API_KEY=sk-" .env; then
        echo -e "${GREEN}✓${NC} OPENAI_API_KEY found"
    else
        echo -e "${RED}✗${NC} OPENAI_API_KEY missing or invalid"
        echo -e "${YELLOW}Fix:${NC} Add OPENAI_API_KEY=sk-your-key to .env"
    fi
else
    echo -e "${RED}✗${NC} .env file not found"
    echo -e "${YELLOW}Creating .env.example...${NC}"
    cat > .env << 'EOF'
OPENAI_API_KEY=sk-your-openai-key-here
MONGO_USERNAME=admin
MONGO_PASSWORD=securepassword123
JWT_SECRET=your-jwt-secret-here
NODE_ENV=development
FRONTEND_URL=http://localhost:3000
EOF
    echo -e "${GREEN}✓${NC} Created .env file - Please add your OPENAI_API_KEY!"
    exit 1
fi

echo ""

# Check 2: Docker is running
echo "Check 2: Docker Status"
echo "----------------------------------------------------------------------"
if docker ps > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Docker is running"
else
    echo -e "${RED}✗${NC} Docker is not running"
    echo -e "${YELLOW}Fix:${NC} Start Docker Desktop"
    exit 1
fi

echo ""

# Check 3: Port availability
echo "Check 3: Port Availability"
echo "----------------------------------------------------------------------"
PORTS=(3000 8000 8001 8002 8003 8004 8005 8006 8007 27017 6379)
PORT_ISSUES=0

for port in "${PORTS[@]}"; do
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠${NC}  Port $port is in use"
        PORT_ISSUES=1
    else
        echo -e "${GREEN}✓${NC} Port $port is available"
    fi
done

if [ $PORT_ISSUES -eq 1 ]; then
    echo -e "${YELLOW}Warning:${NC} Some ports are in use. Stop other services or use:"
    echo "  docker-compose down"
fi

echo ""

# Check 4: Check current container status
echo "Check 4: Container Status"
echo "----------------------------------------------------------------------"
if docker-compose ps | grep -q "Up"; then
    echo "Current containers:"
    docker-compose ps
    echo ""
    echo -e "${YELLOW}Tip:${NC} Use 'docker-compose logs SERVICE_NAME' to see logs"
else
    echo -e "${YELLOW}⚠${NC}  No containers running"
fi

echo ""

# Check 5: Service ports configuration
echo "Check 5: Service Port Configuration"
echo "----------------------------------------------------------------------"
if [ -d services ]; then
    echo "Checking if services use correct ports..."
    
    # Check Python services
    for service in faq payroll leave recruitment performance coordinator; do
        service_dir="services/${service}-service"
        if [ -d "$service_dir" ] && [ -f "$service_dir/src/main.py" ]; then
            port=$(grep -o 'port = int(os.getenv("PORT", [0-9]*)' "$service_dir/src/main.py" | grep -o '[0-9]*')
            if [ -n "$port" ]; then
                echo "  ${service}-service: port $port"
            fi
        fi
    done
else
    echo -e "${RED}✗${NC} services/ directory not found"
fi

echo ""

# Recommendations
echo "======================================================================"
echo "  Recommendations"
echo "======================================================================"
echo ""

echo "If services are failing to start:"
echo ""
echo "1. ${GREEN}Use simplified docker-compose:${NC}"
echo "   docker-compose -f docker-compose.simple.yml up -d"
echo ""
echo "2. ${GREEN}Check logs for specific service:${NC}"
echo "   docker-compose logs payroll-service"
echo "   docker-compose logs faq-service"
echo ""
echo "3. ${GREEN}Start services one by one:${NC}"
echo "   docker-compose up -d mongodb redis"
echo "   sleep 30"
echo "   docker-compose up -d auth-service"
echo "   docker-compose up -d faq-service payroll-service"
echo ""
echo "4. ${GREEN}Rebuild if needed:${NC}"
echo "   docker-compose down"
echo "   docker-compose build --no-cache"
echo "   docker-compose up -d"
echo ""
echo "5. ${GREEN}Check service health:${NC}"
echo "   curl http://localhost:8000/health"
echo "   curl http://localhost:8001/health"
echo "   curl http://localhost:8002/health"
echo ""

echo "======================================================================"
echo "For more help, see TROUBLESHOOTING.md"
echo "======================================================================"
