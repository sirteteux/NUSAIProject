const express = require('express');
const axios = require('axios');

const router = express.Router();

const RECRUITMENT_URL = process.env.RECRUITMENT_URL || 'http://localhost:5003';

// Query recruitment AI
router.post('/query', async (req, res) => {
  try {
    const { query, context } = req.body;

    if (!query) {
      return res.status(400).json({ error: 'Query is required' });
    }

    const response = await axios.post(`${RECRUITMENT_URL}/api/recruitment/query`, {
      query,
      context
    });

    res.json(response.data);
  } catch (error) {
    console.error('Recruitment Agent Error:', error.message);
    res.status(500).json({ 
      error: 'Failed to get recruitment information',
      details: error.response?.data?.detail || error.message 
    });
  }
});

// Get job openings
router.get('/openings', async (req, res) => {
  try {
    const { department, location } = req.query;

    const response = await axios.get(`${RECRUITMENT_URL}/api/recruitment/openings`, {
      params: { department, location }
    });

    res.json(response.data);
  } catch (error) {
    console.error('Recruitment Agent Error:', error.message);
    res.status(500).json({ error: 'Failed to get openings' });
  }
});

// Get specific job opening
router.get('/opening/:id', async (req, res) => {
  try {
    const response = await axios.get(
      `${RECRUITMENT_URL}/api/recruitment/opening/${req.params.id}`
    );

    res.json(response.data);
  } catch (error) {
    console.error('Recruitment Agent Error:', error.message);
    const status = error.response?.status || 500;
    res.status(status).json({ error: 'Failed to get job details' });
  }
});

module.exports = router;
