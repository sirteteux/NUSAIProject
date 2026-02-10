const express = require('express');
const axios = require('axios');

const router = express.Router();

const PAYROLL_AGENT_URL = process.env.PAYROLL_URL || 'http://localhost:5002';

// Query payroll (proxies to Payroll agent)
router.post('/query', async (req, res) => {
  try {
    const { query } = req.body;

    if (!query) {
      return res.status(400).json({ error: 'Query is required' });
    }

    // Call Payroll agent with employee context
    const response = await axios.post(`${PAYROLL_AGENT_URL}/api/payroll/query`, {
      query,
      employee_id: req.user.employeeId || 'EMP000001'
    });

    res.json(response.data);
  } catch (error) {
    console.error('Payroll Agent Error:', error.message);
    res.status(500).json({ 
      error: 'Failed to get payroll information',
      details: error.response?.data?.detail || error.message 
    });
  }
});

// Get payslip
router.get('/payslip/:employeeId', async (req, res) => {
  try {
    const { employeeId } = req.params;
    const { month, year } = req.query;

    const response = await axios.get(
      `${PAYROLL_AGENT_URL}/api/payroll/payslip/${employeeId}`,
      { params: { month, year } }
    );

    res.json(response.data);
  } catch (error) {
    console.error('Payroll Agent Error:', error.message);
    res.status(500).json({ error: 'Failed to get payslip' });
  }
});

// Get salary history
router.get('/history', async (req, res) => {
  try {
    const employeeId = req.user.employeeId || 'EMP000001';

    const response = await axios.get(
      `${PAYROLL_AGENT_URL}/api/payroll/history/${employeeId}`
    );

    res.json(response.data);
  } catch (error) {
    console.error('Payroll Agent Error:', error.message);
    res.status(500).json({ error: 'Failed to get history' });
  }
});

module.exports = router;
