/**
 * Backend Server - Phase 1
 * API Gateway for HR Agentic AI
 */

const express = require('express');
const cors = require('cors');
const rateLimit = require('express-rate-limit');
require('dotenv').config();

const connectDB = require('./config/database');
const authMiddleware = require('./middleware/auth');
const errorHandler = require('./middleware/errorHandler');

// Import routes
const authRoutes = require('./routes/auth');
const coordinatorRoutes = require('./routes/coordinator');
const faqRoutes = require('./routes/faq');
const payrollRoutes = require('./routes/payroll');
const recruitmentRoutes = require('./routes/recruitment');
const performanceRoutes = require('./routes/performance');
const leaveRoutes = require('./routes/leave');

// Initialize Express
const app = express();
const PORT = process.env.PORT || 4000;

// Middleware
app.use(cors({
  origin: process.env.FRONTEND_URL || 'http://localhost:3000',
  credentials: true
}));

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Rate limiting
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100
});
app.use('/api/', limiter);

// Connect to MongoDB
connectDB();

// Health check
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'backend-api',
    timestamp: new Date().toISOString()
  });
});

// API Documentation
app.get('/api/docs', (req, res) => {
  res.json({
    name: 'HR Agentic AI - Phase 1',
    version: '1.0.0',
    description: 'FAQ Agent Working | Other agents return mock data',
    endpoints: {
      auth: {
        login: 'POST /api/auth/login',
        register: 'POST /api/auth/register'
      },
      faq: {
        ask: 'POST /api/faq/ask - ✅ WORKING with OpenAI',
        categories: 'GET /api/faq/categories',
        popular: 'GET /api/faq/popular'
      },
      payroll: {
        query: 'POST /api/payroll/query - 🎨 Mock data',
        payslip: 'GET /api/payroll/payslip/:employeeId'
      },
      recruitment: {
        openings: 'GET /api/recruitment/openings - 🎨 Mock data',
        apply: 'POST /api/recruitment/apply'
      },
      performance: {
        goals: 'GET /api/performance/goals - 🎨 Mock data',
        reviews: 'GET /api/performance/reviews'
      },
      leave: {
        request: 'POST /api/leave/request - 🎨 Mock data',
        balance: 'GET /api/leave/balance'
      }
    }
  });
});

// Routes
app.use('/api/auth', authRoutes);
app.use('/api/coordinator', authMiddleware, coordinatorRoutes);
app.use('/api/faq', authMiddleware, faqRoutes);
app.use('/api/payroll', authMiddleware, payrollRoutes);
app.use('/api/recruitment', authMiddleware, recruitmentRoutes);
app.use('/api/performance', authMiddleware, performanceRoutes);
app.use('/api/leave', authMiddleware, leaveRoutes);

// 404 handler
app.use('*', (req, res) => {
  res.status(404).json({
    error: 'Route not found',
    path: req.originalUrl
  });
});

// Error handler
app.use(errorHandler);

// Start server
app.listen(PORT, () => {
  console.log(`🚀 Backend API running on port ${PORT}`);
  console.log(`📝 API Docs: http://localhost:${PORT}/api/docs`);
  console.log(`💚 Health: http://localhost:${PORT}/health`);
});

module.exports = app;
