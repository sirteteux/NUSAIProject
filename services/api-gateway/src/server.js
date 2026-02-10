/**
 * API Gateway - HR Microservices
 * Single entry point for all client requests
 * Routes to appropriate microservices
 */

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const { createProxyMiddleware } = require('http-proxy-middleware');
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
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100, // Limit each IP to 100 requests per windowMs
  message: 'Too many requests from this IP, please try again later.'
});
app.use('/api/', limiter);

// Service URLs from environment
const SERVICES = {
  auth: process.env.AUTH_SERVICE_URL || 'http://auth-service:8001',
  faq: process.env.FAQ_SERVICE_URL || 'http://faq-service:8002',
  payroll: process.env.PAYROLL_SERVICE_URL || 'http://payroll-service:8003',
  leave: process.env.LEAVE_SERVICE_URL || 'http://leave-service:8004',
  recruitment: process.env.RECRUITMENT_SERVICE_URL || 'http://recruitment-service:8005',
  performance: process.env.PERFORMANCE_SERVICE_URL || 'http://performance-service:8006',
  coordinator: process.env.COORDINATOR_SERVICE_URL || 'http://coordinator-service:8007',
};

// Health check
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'api-gateway',
    version: '1.0.0',
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
    services: healthChecks.map(result => result.value)
  });
});

// Proxy configuration with authentication middleware
const createServiceProxy = (target, pathRewrite = {}) => {
  return createProxyMiddleware({
    target,
    changeOrigin: true,
    pathRewrite,
    onProxyReq: (proxyReq, req, res) => {
      // Forward authentication headers
      if (req.headers.authorization) {
        proxyReq.setHeader('Authorization', req.headers.authorization);
      }
      
      // Add request ID for tracing
      const requestId = req.headers['x-request-id'] || `${Date.now()}-${Math.random()}`;
      proxyReq.setHeader('X-Request-ID', requestId);
      
      console.log(`[${requestId}] ${req.method} ${req.path} → ${target}`);
    },
    onProxyRes: (proxyRes, req, res) => {
      const requestId = req.headers['x-request-id'];
      console.log(`[${requestId}] ${proxyRes.statusCode} ← ${req.path}`);
    },
    onError: (err, req, res) => {
      console.error(`Proxy error: ${err.message}`);
      res.status(503).json({
        error: 'Service Unavailable',
        message: 'The requested service is temporarily unavailable',
        service: req.path.split('/')[2]
      });
    }
  });
};

// Route: Auth Service (no auth required)
app.use('/api/auth', createServiceProxy(SERVICES.auth, {
  '^/api/auth': '/api/auth'
}));

// Simple JWT validation middleware (for protected routes)
const authenticate = (req, res, next) => {
  const token = req.headers.authorization;
  
  if (!token) {
    return res.status(401).json({ error: 'No authorization token provided' });
  }

  // In production, validate JWT here
  // For now, just pass through to services which will validate
  next();
};

// Protected Routes - All require authentication
app.use('/api/coordinator', authenticate, createServiceProxy(SERVICES.coordinator, {
  '^/api/coordinator': '/api/coordinator'
}));

app.use('/api/faq', authenticate, createServiceProxy(SERVICES.faq, {
  '^/api/faq': '/api/faq'
}));

app.use('/api/payroll', authenticate, createServiceProxy(SERVICES.payroll, {
  '^/api/payroll': '/api/payroll'
}));

app.use('/api/leave', authenticate, createServiceProxy(SERVICES.leave, {
  '^/api/leave': '/api/leave'
}));

app.use('/api/recruitment', authenticate, createServiceProxy(SERVICES.recruitment, {
  '^/api/recruitment': '/api/recruitment'
}));

app.use('/api/performance', authenticate, createServiceProxy(SERVICES.performance, {
  '^/api/performance': '/api/performance'
}));

// API documentation
app.get('/api/docs', (req, res) => {
  res.json({
    name: 'HR Microservices API Gateway',
    version: '1.0.0',
    description: 'Central API Gateway for HR Agentic AI Microservices',
    services: {
      auth: {
        url: '/api/auth',
        description: 'Authentication and user management',
        endpoints: {
          login: 'POST /api/auth/login',
          register: 'POST /api/auth/register',
          profile: 'GET /api/auth/profile'
        }
      },
      coordinator: {
        url: '/api/coordinator',
        description: 'Intelligent query routing to appropriate services',
        endpoints: {
          ask: 'POST /api/coordinator/ask',
          agents: 'GET /api/coordinator/agents'
        }
      },
      faq: {
        url: '/api/faq',
        description: 'General HR questions and answers',
        endpoints: {
          ask: 'POST /api/faq/ask',
          popular: 'GET /api/faq/popular'
        }
      },
      payroll: {
        url: '/api/payroll',
        description: 'Salary and compensation queries',
        endpoints: {
          query: 'POST /api/payroll/query',
          payslip: 'GET /api/payroll/payslip/:id'
        }
      },
      leave: {
        url: '/api/leave',
        description: 'Leave management and requests',
        endpoints: {
          query: 'POST /api/leave/query',
          request: 'POST /api/leave/request'
        }
      },
      recruitment: {
        url: '/api/recruitment',
        description: 'Job openings and recruitment',
        endpoints: {
          query: 'POST /api/recruitment/query',
          openings: 'GET /api/recruitment/openings'
        }
      },
      performance: {
        url: '/api/performance',
        description: 'Performance management and goals',
        endpoints: {
          query: 'POST /api/performance/query',
          goals: 'GET /api/performance/goals'
        }
      }
    }
  });
});

// 404 handler
app.use('*', (req, res) => {
  res.status(404).json({
    error: 'Not Found',
    message: `Route ${req.originalUrl} not found`,
    availableRoutes: [
      '/health',
      '/health/services',
      '/api/docs',
      '/api/auth/*',
      '/api/coordinator/*',
      '/api/faq/*',
      '/api/payroll/*',
      '/api/leave/*',
      '/api/recruitment/*',
      '/api/performance/*'
    ]
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

// Start server
app.listen(PORT, () => {
  console.log('='.repeat(50));
  console.log('🚀 API Gateway Started');
  console.log('='.repeat(50));
  console.log(`Port: ${PORT}`);
  console.log(`Environment: ${process.env.NODE_ENV || 'development'}`);
  console.log('\nConfigured Services:');
  Object.entries(SERVICES).forEach(([name, url]) => {
    console.log(`  - ${name.padEnd(15)} → ${url}`);
  });
  console.log('='.repeat(50));
  console.log(`\n📖 API Docs: http://localhost:${PORT}/api/docs`);
  console.log(`💚 Health Check: http://localhost:${PORT}/health\n`);
});

module.exports = app;
