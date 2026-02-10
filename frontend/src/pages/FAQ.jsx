import React, { useState, useEffect } from 'react';
import { toast } from 'react-toastify';
import { faqAPI } from '../services/api';
import './FAQ.css';

const FAQ = () => {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversation, setConversation] = useState([]);
  const [popularQuestions, setPopularQuestions] = useState([]);

  useEffect(() => {
    loadPopularQuestions();
  }, []);

  const loadPopularQuestions = async () => {
    try {
      const response = await faqAPI.getPopular();
      setPopularQuestions(response.data.questions || []);
    } catch (error) {
      console.error('Failed to load popular questions');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!question.trim()) return;

    // Add user question to conversation
    setConversation(prev => [...prev, { type: 'user', text: question }]);
    setLoading(true);

    try {
      const response = await faqAPI.ask(question);
      
      // Add AI response to conversation
      setConversation(prev => [...prev, { 
        type: 'ai', 
        text: response.data.answer,
        confidence: response.data.confidence 
      }]);
      
      setQuestion('');
      toast.success('Answer received!');
    } catch (error) {
      toast.error('Failed to get answer');
      setConversation(prev => prev.slice(0, -1)); // Remove user question on error
    } finally {
      setLoading(false);
    }
  };

  const handlePopularClick = (q) => {
    setQuestion(q);
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">❓ FAQ - HR Knowledge Base</h1>
        <p className="page-subtitle">
          <span className="badge badge-success">✅ WORKING</span> Ask questions and get AI-powered answers
        </p>
      </div>

      <div className="faq-layout">
        {/* Chat Interface */}
        <div className="faq-chat-section">
          <div className="card">
            <div className="chat-container">
              {conversation.length === 0 ? (
                <div className="chat-empty">
                  <div className="empty-icon">💬</div>
                  <p>Ask me anything about HR policies, benefits, or procedures!</p>
                </div>
              ) : (
                <div className="chat-messages">
                  {conversation.map((msg, index) => (
                    <div key={index} className={`chat-message ${msg.type}`}>
                      <div className="message-avatar">
                        {msg.type === 'user' ? '👤' : '🤖'}
                      </div>
                      <div className="message-content">
                        <div className="message-text">{msg.text}</div>
                        {msg.confidence && (
                          <div className="message-meta">
                            Confidence: {(msg.confidence * 100).toFixed(0)}%
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  {loading && (
                    <div className="chat-message ai">
                      <div className="message-avatar">🤖</div>
                      <div className="message-content">
                        <div className="typing-indicator">
                          <span></span><span></span><span></span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            <form onSubmit={handleSubmit} className="chat-input-form">
              <input
                type="text"
                className="chat-input"
                placeholder="Type your question here..."
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                disabled={loading}
              />
              <button 
                type="submit" 
                className="btn btn-primary"
                disabled={loading || !question.trim()}
              >
                {loading ? '...' : 'Send'}
              </button>
            </form>
          </div>
        </div>

        {/* Sidebar with popular questions */}
        <div className="faq-sidebar">
          <div className="card">
            <h3 className="card-title">Popular Questions</h3>
            <div className="popular-questions">
              {popularQuestions.map((q, index) => (
                <button
                  key={index}
                  className="popular-question-btn"
                  onClick={() => handlePopularClick(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>

          <div className="card">
            <h3 className="card-title">💡 Tips</h3>
            <ul className="tips-list">
              <li>Ask specific questions for better answers</li>
              <li>You can ask about policies, benefits, or procedures</li>
              <li>Try clicking popular questions to get started</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FAQ;
