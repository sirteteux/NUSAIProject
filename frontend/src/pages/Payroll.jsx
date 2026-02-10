import React, { useState, useEffect } from 'react';
import { toast } from 'react-toastify';
import { payrollAPI } from '../services/api';
import { useAuthStore } from '../stores/authStore';
import '../pages/FAQ.css';  // Reuse FAQ styles for chat interface

const Payroll = () => {
  const { user } = useAuthStore();
  const [query, setQuery] = useState('');
  const [conversation, setConversation] = useState([]);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState([]);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    try {
      const response = await payrollAPI.getHistory();
      setHistory(response.data.history || []);
    } catch (error) {
      console.error('Failed to load history');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setConversation(prev => [...prev, { type: 'user', text: query }]);
    setLoading(true);

    try {
      const response = await payrollAPI.query(query);
      
      setConversation(prev => [...prev, { 
        type: 'ai', 
        text: response.data.answer
      }]);
      
      setQuery('');
      toast.success('Got answer from Payroll AI!');
    } catch (error) {
      toast.error('Failed to get answer');
      setConversation(prev => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  const quickQuestions = [
    "What's my current salary?",
    "Show me my last payslip",
    "Explain my salary deductions",
    "What's my annual salary?",
    "How is my tax calculated?"
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">💰 Payroll</h1>
        <p className="page-subtitle">
          <span className="badge badge-success">✅ AI-POWERED</span> Ask about your salary and payslips
        </p>
      </div>

      <div className="faq-layout">
        {/* Chat Interface */}
        <div className="faq-chat-section">
          <div className="card">
            <div className="chat-container">
              {conversation.length === 0 ? (
                <div className="chat-empty">
                  <div className="empty-icon">💵</div>
                  <p>Ask me anything about your salary, payslips, or deductions!</p>
                  <p style={{ fontSize: '13px', color: '#999', marginTop: '8px' }}>
                    Employee: {user?.name} ({user?.employeeId})
                  </p>
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
                placeholder="Ask about your salary..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={loading}
              />
              <button 
                type="submit" 
                className="btn btn-primary"
                disabled={loading || !query.trim()}
              >
                {loading ? '...' : 'Send'}
              </button>
            </form>
          </div>
        </div>

        {/* Sidebar */}
        <div className="faq-sidebar">
          <div className="card">
            <h3 className="card-title">Quick Questions</h3>
            <div className="popular-questions">
              {quickQuestions.map((q, index) => (
                <button
                  key={index}
                  className="popular-question-btn"
                  onClick={() => setQuery(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>

          {history.length > 0 && (
            <div className="card">
              <h3 className="card-title">Recent Payslips</h3>
              <div style={{ display: 'grid', gap: '8px' }}>
                {history.slice(0, 3).map((item, index) => (
                  <div key={index} style={{
                    padding: '10px',
                    background: '#f8f9fa',
                    borderRadius: '4px',
                    fontSize: '13px'
                  }}>
                    <div style={{ fontWeight: '500' }}>{item.month} {item.year}</div>
                    <div style={{ color: '#666', marginTop: '4px' }}>
                      Net: SGD {item.net.toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Payroll;
