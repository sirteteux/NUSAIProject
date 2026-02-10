const express = require('express');
const axios = require('axios');

const router = express.Router();

const LEAVE_AGENT_URL = process.env.LEAVE_URL || 'http://localhost:5006';

// Query leave (proxies to Leave agent)
router.post('/query', async (req, res) => {
  try {
    const { query } = req.body;

    if (!query) {
      return res.status(400).json({ error: 'Query is required' });
    }

    const response = await axios.post(`${LEAVE_AGENT_URL}/api/leave/query`, {
      query,
      employee_id: req.user.employeeId || 'EMP000001'
    });

    res.json(response.data);
  } catch (error) {
    console.error('Leave Agent Error:', error.message);
    res.status(500).json({ 
      error: 'Failed to get leave information',
      details: error.response?.data?.detail || error.message 
    });
  }
});

// Get leave balance
router.get('/balance', async (req, res) => {
  try {
    const employeeId = req.user.employeeId || 'EMP000001';

    const response = await axios.get(
      `${LEAVE_AGENT_URL}/api/leave/balance`,
      { params: { employee_id: employeeId } }
    );

    res.json(response.data);
  } catch (error) {
    console.error('Leave Agent Error:', error.message);
    res.status(500).json({ error: 'Failed to get balance' });
  }
});

// Request leave
router.post('/request', async (req, res) => {
  try {
    const leaveData = {
      ...req.body,
      employee_id: req.user.employeeId || 'EMP000001'
    };

    const response = await axios.post(
      `${LEAVE_AGENT_URL}/api/leave/request`,
      leaveData
    );

    res.json(response.data);
  } catch (error) {
    console.error('Leave Agent Error:', error.message);
    const status = error.response?.status || 500;
    res.status(status).json({ 
      error: 'Failed to submit leave request',
      details: error.response?.data?.detail || error.message 
    });
  }
});

// Get leave history
router.get('/history', async (req, res) => {
  try {
    const employeeId = req.user.employeeId || 'EMP000001';

    const response = await axios.get(
      `${LEAVE_AGENT_URL}/api/leave/history`,
      { params: { employee_id: employeeId } }
    );

    res.json(response.data);
  } catch (error) {
    console.error('Leave Agent Error:', error.message);
    res.status(500).json({ error: 'Failed to get history' });
  }
});

module.exports = router;
