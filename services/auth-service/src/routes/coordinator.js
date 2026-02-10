const express = require('express');
const axios = require('axios');

const router = express.Router();

const COORDINATOR_URL = process.env.COORDINATOR_URL || 'http://localhost:5001';

// Ask coordinator (intelligent routing)
router.post('/ask', async (req, res) => {
  try {
    const { query, context } = req.body;

    if (!query) {
      return res.status(400).json({ error: 'Query is required' });
    }

    // Call coordinator which will intelligently route to appropriate agent
    const response = await axios.post(`${COORDINATOR_URL}/api/coordinator/ask`, {
      query,
      employee_id: req.user.employeeId || 'EMP000001',
      context
    });

    res.json(response.data);
  } catch (error) {
    console.error('Coordinator Error:', error.message);
    res.status(500).json({ 
      error: 'Failed to process query',
      details: error.response?.data?.detail || error.message 
    });
  }
});

// Get list of available agents
router.get('/agents', async (req, res) => {
  try {
    const response = await axios.get(`${COORDINATOR_URL}/api/coordinator/agents`);
    res.json(response.data);
  } catch (error) {
    console.error('Coordinator Error:', error.message);
    res.status(500).json({ error: 'Failed to get agents list' });
  }
});

module.exports = router;
