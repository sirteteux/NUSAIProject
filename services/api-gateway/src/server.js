/**
 * API Gateway with Integrated Authentication
 * Single entry point for all client requests with built-in auth
 */

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const { createProxyMiddleware } = require('http-proxy-middleware');
const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 8000;

// Middleware
app.use(helmet());
app.use(cors({
  origin: process.env.FRONTEND_URL || 'http://localhost:3000',
  credentials: true
}));
app.use(express.json());

// Rate limiting
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 100,
  message: 'Too many requests from this IP, please try again later.'
});
app.use('/api/', limiter);

// MongoDB Connection (Shared Atlas Database)
const MONGODB_URI = process.env.MONGODB_URI;

if (!MONGODB_URI) {
  console.error('❌ MONGODB_URI environment variable is required');
  process.exit(1);
}

mongoose.connect(MONGODB_URI)
  .then(() => console.log('✓ Connected to MongoDB Atlas (shared database)'))
  .catch(err => {
    console.error('MongoDB connection error:', err);
    process.exit(1);
  });

// User Model
const userSchema = new mongoose.Schema({
  employee_id: { type: String, required: true, unique: true },
  name: { type: String, required: true },
  email: { type: String, required: true, unique: true },
  password: { type: String, required: true },
  department: { type: String },
  position: { type: String },
  role: { type: String, default: 'employee' },
  createdAt: { type: Date, default: Date.now }
});

const User = mongoose.model('User', userSchema);

// Service URLs
const SERVICES = {
  faq: process.env.FAQ_SERVICE_URL || 'http://faq-service:8002',
  payroll: process.env.PAYROLL_SERVICE_URL || 'http://payroll-service:8003',
  leave: process.env.LEAVE_SERVICE_URL || 'http://leave-service:8004',
  recruitment: process.env.RECRUITMENT_SERVICE_URL || 'http://recruitment-service:8005',
  performance: process.env.PERFORMANCE_SERVICE_URL || 'http://performance-service:8006',
  coordinator: process.env.COORDINATOR_SERVICE_URL || 'http://coordinator-service:8007',
};

// Health check
app.get('/health', (req, res) => {
  const dbStatus = mongoose.connection.readyState === 1 ? 'connected' : 'disconnected';
  res.json({
    status: 'healthy',
    service: 'api-gateway',
    version: '1.0.0',
    database: dbStatus,
    timestamp: new Date().toISOString(),
    services: Object.keys(SERVICES)
  });
});

// Service health aggregation
app.get('/health/services', async (req, res) => {
  const axios = require('axios');
  const healthChecks = await Promise.allSettled(
    Object.entries(SERVICES).map(async ([name, url]) => {
      try {
        const response = await axios.get(`${url}/health`, { timeout: 5000 });
        return { name, status: 'healthy', url, data: response.data };
      } catch (error) {
        return { name, status: 'unhealthy', url, error: error.message };
      }
    })
  );

  res.json({
    gateway: 'healthy',
    database: mongoose.connection.readyState === 1 ? 'connected' : 'disconnected',
    services: healthChecks.map(result => result.value)
  });
});

// ==================== AUTHENTICATION ROUTES ====================

// Register endpoint
app.post('/api/auth/register', async (req, res) => {
  try {
    const { employee_id, name, email, password, department, position } = req.body;

    if (!employee_id || !name || !email || !password) {
      return res.status(400).json({ error: 'All fields are required' });
    }

    const existingUser = await User.findOne({ 
      $or: [{ email }, { employee_id }] 
    });
    
    if (existingUser) {
      return res.status(409).json({ error: 'User already exists' });
    }

    const hashedPassword = await bcrypt.hash(password, 10);

    const user = new User({
      employee_id,
      name,
      email,
      password: hashedPassword,
      department,
      position
    });

    await user.save();

    res.status(201).json({
      message: 'User registered successfully',
      user: {
        employee_id: user.employee_id,
        name: user.name,
        email: user.email,
        department: user.department,
        position: user.position
      }
    });
  } catch (error) {
    console.error('Registration error:', error);
    res.status(500).json({ error: 'Registration failed' });
  }
});

// Login endpoint
app.post('/api/auth/login', async (req, res) => {
  try {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({ error: 'Email and password are required' });
    }

    const user = await User.findOne({ email });
    if (!user) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    const isValidPassword = await bcrypt.compare(password, user.password);
    if (!isValidPassword) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    const token = jwt.sign(
      { 
        userId: user._id,
        employee_id: user.employee_id,
        email: user.email,
        role: user.role
      },
      process.env.JWT_SECRET || 'your-secret-key',
      { expiresIn: process.env.JWT_EXPIRY || '7d' }
    );

    res.json({
      message: 'Login successful',
      token,
      user: {
        employee_id: user.employee_id,
        name: user.name,
        email: user.email,
        department: user.department,
        position: user.position,
        role: user.role
      }
    });
  } catch (error) {
    console.error('Login error:', error);
    res.status(500).json({ error: 'Login failed' });
  }
});

// Middleware to verify JWT
const authenticateToken = (req, res, next) => {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];

  if (!token) {
    return res.status(401).json({ error: 'Access token required' });
  }

  jwt.verify(token, process.env.JWT_SECRET || 'your-secret-key', (err, user) => {
    if (err) {
      return res.status(403).json({ error: 'Invalid or expired token' });
    }
    req.user = user;
    next();
  });
};

// Get user profile (protected)
app.get('/api/auth/profile', authenticateToken, async (req, res) => {
  try {
    const user = await User.findById(req.user.userId).select('-password');
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }
    res.json({ user });
  } catch (error) {
    console.error('Profile fetch error:', error);
    res.status(500).json({ error: 'Failed to fetch profile' });
  }
});

// Update user profile (protected)
app.put('/api/auth/profile', authenticateToken, async (req, res) => {
  try {
    const { name, department, position } = req.body;
    
    const user = await User.findByIdAndUpdate(
      req.user.userId,
      { name, department, position },
      { new: true }
    ).select('-password');

    res.json({
      message: 'Profile updated successfully',
      user
    });
  } catch (error) {
    console.error('Profile update error:', error);
    res.status(500).json({ error: 'Failed to update profile' });
  }
});

// ==================== SERVICE PROXYING ====================

const createServiceProxy = (target, pathRewrite = {}) => {
  console.log("gg");
  return createProxyMiddleware({
    target,
    changeOrigin: true,
    pathRewrite,
    timeout: 120000,
    proxyTimeout: 120000,
    
    onProxyReq: (proxyReq, req, res) => {
      const requestId = req.headers['x-request-id'] || `${Date.now()}-${Math.random()}`;
      
      console.log(`[${requestId}] ${req.method} ${req.path} → ${target}`);
      
      // Set headers FIRST (before any write)
      if (req.headers.authorization) {
        proxyReq.setHeader('Authorization', req.headers.authorization);
      }
      proxyReq.setHeader('X-Request-ID', requestId);
      
      // Then handle body for POST/PUT/PATCH
      if (req.body && (req.method === 'POST' || req.method === 'PUT' || req.method === 'PATCH')) {
        const bodyData = JSON.stringify(req.body);
        proxyReq.setHeader('Content-Type', 'application/json');
        proxyReq.setHeader('Content-Length', Buffer.byteLength(bodyData));
        proxyReq.write(bodyData);
        // DON'T call proxyReq.end() - let the proxy handle it
      }
    },
    
    onProxyRes: (proxyRes, req, res) => {
      const requestId = req.headers['x-request-id'];
      console.log(`[${requestId}] ${proxyRes.statusCode} ← ${req.path}`);
    },
    
    onError: (err, req, res) => {
      console.error(`Proxy error: ${err.message}`);
      if (!res.headersSent) {
        res.status(503).json({
          error: 'Service Unavailable',
          message: 'The requested service is temporarily unavailable',
          service: req.path.split('/')[2]
        });
      }
    }
  });
};

// Protected Routes - All require authentication
app.use('/api/coordinator', authenticateToken, createServiceProxy(SERVICES.coordinator, {
  '^/api/coordinator': '/api/coordinator'
}));

app.use('/api/faq', authenticateToken, createServiceProxy(SERVICES.faq, {
  '^/api/faq': '/api/faq'
}));

app.use('/api/payroll', authenticateToken, createServiceProxy(SERVICES.payroll, {
  '^/api/payroll': '/api/payroll'
}));

app.use('/api/leave', authenticateToken, createServiceProxy(SERVICES.leave, {
  '^/api/leave': '/api/leave'
}));

app.use('/api/recruitment', authenticateToken, createServiceProxy(SERVICES.recruitment, {
  '^/api/recruitment': '/api/recruitment'
}));

app.use('/api/performance', authenticateToken, createServiceProxy(SERVICES.performance, {
  '^/api/performance': '/api/performance'
}));

// API documentation
app.get('/api/docs', (req, res) => {
  res.json({
    name: 'HR Microservices API Gateway',
    version: '1.0.0',
    description: 'Central API Gateway with Integrated Authentication',
    authentication: 'Built-in (no separate auth service)',
    services: {
      auth: {
        url: '/api/auth',
        description: 'Authentication (integrated in gateway)',
        endpoints: {
          login: 'POST /api/auth/login',
          register: 'POST /api/auth/register',
          profile: 'GET /api/auth/profile'
        }
      },
      coordinator: {
        url: '/api/coordinator',
        description: 'Intelligent query routing',
        endpoints: {
          ask: 'POST /api/coordinator/ask'
        }
      },
      faq: {
        url: '/api/faq',
        description: 'General HR questions',
        endpoints: {
          ask: 'POST /api/faq/ask'
        }
      },
      payroll: { url: '/api/payroll', description: 'Salary queries' },
      leave: { url: '/api/leave', description: 'Leave management' },
      recruitment: { url: '/api/recruitment', description: 'Job openings' },
      performance: { url: '/api/performance', description: 'Performance reviews' }
    }
  });
});

// 404 handler
app.use('*', (req, res) => {
  res.status(404).json({
    error: 'Not Found',
    message: `Route ${req.originalUrl} not found`
  });
});

// Error handler
app.use((err, req, res, next) => {
  console.error('Gateway Error:', err);
  res.status(err.status || 500).json({
    error: 'Internal Server Error',
    message: err.message || 'An unexpected error occurred'
  });
});

// Seed admin user
async function seedAdmin() {
  try {
    const adminExists = await User.findOne({ email: 'admin@example.com' });
    if (!adminExists) {
      const hashedPassword = await bcrypt.hash('admin123', 10);
      const admin = new User({
        employee_id: 'EMP000001',
        name: 'Admin User',
        email: 'admin@example.com',
        password: hashedPassword,
        department: 'IT',
        position: 'System Administrator',
        role: 'admin'
      });
      await admin.save();
      console.log('✓ Admin user seeded (admin@example.com / admin123)');
    }
  } catch (error) {
    console.error('Seed error:', error);
  }
}

// Start server
app.listen(PORT, async () => {
  console.log('='.repeat(50));
  console.log('🚀 API Gateway Started (Auth Integrated)');
  console.log('='.repeat(50));
  console.log(`Port: ${PORT}`);
  console.log(`Database: Shared MongoDB Atlas`);
  console.log(`Environment: ${process.env.NODE_ENV || 'development'}`);
  console.log('\nConfigured Services:');
  Object.entries(SERVICES).forEach(([name, url]) => {
    console.log(`  - ${name.padEnd(15)} → ${url}`);
  });
  console.log('='.repeat(50));
  
  // Seed admin user
  await seedAdmin();
  
  console.log(`\n📖 API Docs: http://localhost:${PORT}/api/docs`);
  console.log(`💚 Health Check: http://localhost:${PORT}/health\n`);
});

module.exports = app;
