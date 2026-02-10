const express = require('express');
const axios = require('axios');

const router = express.Router();

const FAQ_AGENT_URL = process.env.FAQ_URL || 'http://localhost:5005';

// Ask FAQ question (proxies to FAQ agent)
router.post('/ask', async (req, res) => {
  try {
    const { question } = req.body;

    if (!question) {
      return res.status(400).json({ error: 'Question is required' });
    }

    // Call FAQ agent
    const response = await axios.post(`${FAQ_AGENT_URL}/api/faq/ask`, {
      question,
      user_id: req.user.userId
    });

    res.json(response.data);
  } catch (error) {
    console.error('FAQ Agent Error:', error.message);
    res.status(500).json({ 
      error: 'Failed to get answer',
      details: error.message 
    });
  }
});

// Get FAQ categories
router.get('/categories', async (req, res) => {
  try {
    const response = await axios.get(`${FAQ_AGENT_URL}/api/faq/categories`);
    res.json(response.data);
  } catch (error) {
    console.error('FAQ Agent Error:', error.message);
    res.status(500).json({ error: 'Failed to get categories' });
  }
});

// Get popular questions
router.get('/popular', async (req, res) => {
  try {
    const response = await axios.get(`${FAQ_AGENT_URL}/api/faq/popular`);
    res.json(response.data);
  } catch (error) {
    console.error('FAQ Agent Error:', error.message);
    res.status(500).json({ error: 'Failed to get popular questions' });
  }
});

module.exports = router;
