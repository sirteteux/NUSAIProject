const express = require('express');
const axios = require('axios');

const router = express.Router();

const PERFORMANCE_URL = process.env.PERFORMANCE_URL || 'http://localhost:5004';

// Query performance AI
router.post('/query', async (req, res) => {
  try {
    const { query } = req.body;

    if (!query) {
      return res.status(400).json({ error: 'Query is required' });
    }

    const response = await axios.post(`${PERFORMANCE_URL}/api/performance/query`, {
      query,
      employee_id: req.user.employeeId || 'EMP000001'
    });

    res.json(response.data);
  } catch (error) {
    console.error('Performance Agent Error:', error.message);
    res.status(500).json({ 
      error: 'Failed to get performance information',
      details: error.response?.data?.detail || error.message 
    });
  }
});

// Get employee goals
router.get('/goals', async (req, res) => {
  try {
    const employeeId = req.user.employeeId || 'EMP000001';

    const response = await axios.get(
      `${PERFORMANCE_URL}/api/performance/goals`,
      { params: { employee_id: employeeId } }
    );

    res.json(response.data);
  } catch (error) {
    console.error('Performance Agent Error:', error.message);
    res.status(500).json({ error: 'Failed to get goals' });
  }
});

// Create goal
router.post('/goal/create', async (req, res) => {
  try {
    const goalData = {
      ...req.body,
      employee_id: req.user.employeeId || 'EMP000001'
    };

    const response = await axios.post(
      `${PERFORMANCE_URL}/api/performance/goal/create`,
      goalData
    );

    res.json(response.data);
  } catch (error) {
    console.error('Performance Agent Error:', error.message);
    res.status(500).json({ error: 'Failed to create goal' });
  }
});

// Update goal
router.put('/goal/update', async (req, res) => {
  try {
    const response = await axios.put(
      `${PERFORMANCE_URL}/api/performance/goal/update`,
      req.body
    );

    res.json(response.data);
  } catch (error) {
    console.error('Performance Agent Error:', error.message);
    const status = error.response?.status || 500;
    res.status(status).json({ error: 'Failed to update goal' });
  }
});

// Get performance reviews
router.get('/reviews', async (req, res) => {
  try {
    const employeeId = req.user.employeeId || 'EMP000001';

    const response = await axios.get(
      `${PERFORMANCE_URL}/api/performance/reviews`,
      { params: { employee_id: employeeId } }
    );

    res.json(response.data);
  } catch (error) {
    console.error('Performance Agent Error:', error.message);
    res.status(500).json({ error: 'Failed to get reviews' });
  }
});

module.exports = router;
