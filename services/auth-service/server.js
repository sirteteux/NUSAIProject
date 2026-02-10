/**
 * Auth Service - User Authentication Microservice
 * Handles: Registration, Login, JWT generation, User profiles
 */

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 8001;

// Middleware
app.use(helmet());
app.use(cors());
app.use(express.json());

// MongoDB Connection
const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://localhost:27017/auth_db';

mongoose.connect(MONGODB_URI)
  .then(() => console.log('✓ Connected to MongoDB (auth_db)'))
  .catch(err => console.error('MongoDB connection error:', err));

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

// Health check
app.get('/health', (req, res) => {
  const dbStatus = mongoose.connection.readyState === 1 ? 'connected' : 'disconnected';
  res.json({
    status: 'healthy',
    service: 'auth-service',
    port: PORT,
    database: dbStatus,
    version: '1.0.0',
    timestamp: new Date().toISOString()
  });
});

// Register endpoint
app.post('/api/auth/register', async (req, res) => {
  try {
    const { employee_id, name, email, password, department, position } = req.body;

    // Validation
    if (!employee_id || !name || !email || !password) {
      return res.status(400).json({ error: 'All fields are required' });
    }

    // Check if user exists
    const existingUser = await User.findOne({ 
      $or: [{ email }, { employee_id }] 
    });
    
    if (existingUser) {
      return res.status(409).json({ error: 'User already exists' });
    }

    // Hash password
    const hashedPassword = await bcrypt.hash(password, 10);

    // Create user
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

    // Find user
    const user = await User.findOne({ email });
    if (!user) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    // Check password
    const isValidPassword = await bcrypt.compare(password, user.password);
    if (!isValidPassword) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    // Generate JWT
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

// Validate token endpoint (for other services)
app.post('/api/auth/validate', (req, res) => {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];

  if (!token) {
    return res.status(401).json({ valid: false, error: 'No token provided' });
  }

  jwt.verify(token, process.env.JWT_SECRET || 'your-secret-key', (err, user) => {
    if (err) {
      return res.status(403).json({ valid: false, error: 'Invalid token' });
    }
    res.json({ valid: true, user });
  });
});

// Seed initial admin user
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
  console.log('🔐 Auth Service Started');
  console.log('='.repeat(50));
  console.log(`Port: ${PORT}`);
  console.log(`Database: ${MONGODB_URI}`);
  console.log('='.repeat(50));
  
  // Seed admin user
  await seedAdmin();
  
  console.log(`\nEndpoints:`);
  console.log(`  POST /api/auth/register`);
  console.log(`  POST /api/auth/login`);
  console.log(`  GET  /api/auth/profile (protected)`);
  console.log(`  PUT  /api/auth/profile (protected)`);
  console.log(`  POST /api/auth/validate`);
  console.log(`  GET  /health\n`);
});

module.exports = app;
