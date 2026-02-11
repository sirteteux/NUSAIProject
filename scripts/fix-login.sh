#!/bin/bash

# Login Fix Script - Diagnose and fix login issues

echo "======================================================================"
echo "  Login Issue Diagnosis & Fix"
echo "======================================================================"
echo ""

# Check 1: Auth Service Status
echo "Check 1: Auth Service Status"
echo "----------------------------------------------------------------------"
if docker-compose ps auth-service | grep -q "Up"; then
    echo "✓ Auth Service is running"
else
    echo "✗ Auth Service is NOT running"
    echo ""
    echo "Fix: Restart Auth Service"
    echo "  docker-compose restart auth-service"
    echo "  docker-compose logs -f auth-service"
    exit 1
fi

echo ""

# Check 2: Auth Service Logs
echo "Check 2: Auth Service Logs (last 20 lines)"
echo "----------------------------------------------------------------------"
docker-compose logs --tail=20 auth-service
echo ""

# Check 3: MongoDB Connection
echo "Check 3: MongoDB Users Database"
echo "----------------------------------------------------------------------"
ADMIN_USER=$(docker-compose exec -T mongodb mongosh --quiet --eval "
  use auth_db
  db.users.findOne({email: 'admin@example.com'})
" 2>/dev/null)

if echo "$ADMIN_USER" | grep -q "admin@example.com"; then
    echo "✓ Admin user exists in database"
else
    echo "✗ Admin user NOT found in database"
    echo ""
    echo "Creating admin user..."
    
    # Create admin user manually
    docker-compose exec -T mongodb mongosh --eval "
      use auth_db
      db.users.insertOne({
        employee_id: 'EMP000001',
        name: 'Admin User',
        email: 'admin@example.com',
        password: '\$2a\$10\$YourHashedPasswordHere',
        department: 'IT',
        position: 'System Administrator',
        role: 'admin',
        createdAt: new Date()
      })
    " > /dev/null 2>&1
    
    echo "✓ Admin user created (you may need to restart auth-service)"
fi

echo ""

# Check 4: Test Login API
echo "Check 4: Test Login API Directly"
echo "----------------------------------------------------------------------"
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "admin123"
  }')

if echo "$LOGIN_RESPONSE" | grep -q "token"; then
    echo "✓ Login API works!"
    echo "Response:"
    echo "$LOGIN_RESPONSE" | jq . 2>/dev/null || echo "$LOGIN_RESPONSE"
else
    echo "✗ Login API failed"
    echo "Response:"
    echo "$LOGIN_RESPONSE"
fi

echo ""

# Check 5: Frontend Connection
echo "Check 5: Frontend API Configuration"
echo "----------------------------------------------------------------------"
if docker-compose exec -T frontend sh -c "cat /app/src/services/api.js 2>/dev/null | grep -i gateway" > /dev/null 2>&1; then
    echo "✓ Frontend configured to use API Gateway"
else
    echo "⚠ Could not verify frontend API configuration"
fi

echo ""
echo "======================================================================"
echo "  Recommended Actions"
echo "======================================================================"
echo ""
echo "If login still fails:"
echo ""
echo "1. Restart Auth Service:"
echo "   docker-compose restart auth-service"
echo ""
echo "2. Check Auth Service logs:"
echo "   docker-compose logs -f auth-service"
echo ""
echo "3. Manually create admin user:"
echo "   docker-compose exec auth-service node -e \""
echo "   const bcrypt = require('bcryptjs');"
echo "   console.log(bcrypt.hashSync('admin123', 10));"
echo "   \""
echo ""
echo "4. Test API directly from browser console:"
echo "   fetch('http://localhost:8000/api/auth/login', {"
echo "     method: 'POST',"
echo "     headers: {'Content-Type': 'application/json'},"
echo "     body: JSON.stringify({email:'admin@example.com',password:'admin123'})"
echo "   }).then(r=>r.json()).then(console.log)"
echo ""
echo "======================================================================"
