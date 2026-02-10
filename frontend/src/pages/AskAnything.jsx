import React, { useState, useEffect } from 'react';
import { toast } from 'react-toastify';
import { coordinatorAPI } from '../services/api';
import { useAuthStore } from '../stores/authStore';
import '../pages/FAQ.css';

const AskAnything = () => {
  const { user } = useAuthStore();
  const [query, setQuery] = useState('');
  const [conversation, setConversation] = useState([]);
  const [loading, setLoading] = useState(false);
  const [agents, setAgents] = useState([]);

  useEffect(() => {
    loadAgents();
  }, []);

  const loadAgents = async () => {
    try {
      const response = await coordinatorAPI.getAgents();
      setAgents(response.data.agents || []);
    } catch (error) {
      console.error('Failed to load agents');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setConversation(prev => [...prev, { type: 'user', text: query }]);
    setLoading(true);

    try {
      const response = await coordinatorAPI.ask(query);
      
      setConversation(prev => [...prev, { 
        type: 'ai', 
        text: response.data.answer,
        agent: response.data.agent_used
      }]);
      
      setQuery('');
      toast.success(`Routed to ${response.data.agent_used} Agent!`);
    } catch (error) {
      toast.error('Failed to get answer');
      setConversation(prev => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  const sampleQuestions = [
    "What's my current salary?",
    "How many leave days do I have?",
    "What are the working hours?",
    "What job openings are available?",
    "What are my performance goals?",
    "How do I request vacation leave?",
    "When is my next payslip?",
    "What's the interview process?"
  ];

  const getAgentColor = (agentName) => {
    const colors = {
      'FAQ': '#2196f3',
      'Payroll': '#4caf50',
      'Leave': '#ff9800',
      'Recruitment': '#9c27b0',
      'Performance': '#f44336'
    };
    return colors[agentName] || '#607d8b';
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">🤖 Ask Anything</h1>
        <p className="page-subtitle">
          <span className="badge" style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white', padding: '6px 12px', borderRadius: '4px' }}>
            🧠 COORDINATOR AI - LANGCHAIN
          </span>
          <br />
          Ask any HR question - I'll intelligently route it to the right expert!
        </p>
      </div>

      <div className="faq-layout">
        {/* Chat Interface */}
        <div className="faq-chat-section">
          <div className="card">
            <div className="chat-container">
              {conversation.length === 0 ? (
                <div className="chat-empty">
                  <div className="empty-icon" style={{ fontSize: '64px' }}>🎯</div>
                  <h3>Ask me anything about HR!</h3>
                  <p style={{ fontSize: '14px', color: '#666', marginTop: '12px' }}>
                    I'm the Coordinator Agent powered by LangChain. I'll intelligently route your question to the right specialist:
                  </p>
                  <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', marginTop: '16px', flexWrap: 'wrap' }}>
                    {agents.map((agent) => (
                      <span key={agent.name} style={{
                        padding: '6px 12px',
                        borderRadius: '16px',
                        fontSize: '12px',
                        fontWeight: 'bold',
                        background: getAgentColor(agent.name),
                        color: 'white'
                      }}>
                        {agent.name}
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="chat-messages">
                  {conversation.map((msg, index) => (
                    <div key={index} className={`chat-message ${msg.type}`}>
                      <div className="message-avatar">
                        {msg.type === 'user' ? '👤' : '🤖'}
                      </div>
                      <div className="message-content">
                        {msg.type === 'ai' && msg.agent && (
                          <div style={{
                            fontSize: '11px',
                            color: getAgentColor(msg.agent),
                            fontWeight: 'bold',
                            marginBottom: '4px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px'
                          }}>
                            <span style={{
                              width: '8px',
                              height: '8px',
                              borderRadius: '50%',
                              background: getAgentColor(msg.agent),
                              display: 'inline-block'
                            }}></span>
                            {msg.agent} Agent
                          </div>
                        )}
                        <div className="message-text">{msg.text}</div>
                      </div>
                    </div>
                  ))}
                  {loading && (
                    <div className="chat-message ai">
                      <div className="message-avatar">🤖</div>
                      <div className="message-content">
                        <div style={{ fontSize: '11px', color: '#999', marginBottom: '4px' }}>
                          🧠 Routing query to appropriate agent...
                        </div>
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
                placeholder="Ask anything about HR..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={loading}
              />
              <button 
                type="submit" 
                className="btn btn-primary"
                disabled={loading || !query.trim()}
              >
                {loading ? '...' : 'Ask'}
              </button>
            </form>
          </div>
        </div>

        {/* Sidebar */}
        <div className="faq-sidebar">
          <div className="card">
            <h3 className="card-title">💡 Try Asking</h3>
            <div className="popular-questions">
              {sampleQuestions.map((q, index) => (
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

          <div className="card" style={{ marginTop: '16px' }}>
            <h3 className="card-title">🤖 Available Agents</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {agents.map((agent) => (
                <div key={agent.name} style={{
                  padding: '12px',
                  background: '#f8f9fa',
                  borderRadius: '8px',
                  borderLeft: `4px solid ${getAgentColor(agent.name)}`
                }}>
                  <div style={{ fontWeight: 'bold', fontSize: '14px', marginBottom: '4px' }}>
                    {agent.name}
                  </div>
                  <div style={{ fontSize: '12px', color: '#666', marginBottom: '8px' }}>
                    {agent.description}
                  </div>
                  <div style={{ fontSize: '11px', color: '#999' }}>
                    {agent.capabilities?.slice(0, 3).join(' • ')}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card" style={{ marginTop: '16px' }}>
            <h3 className="card-title">ℹ️ How It Works</h3>
            <p style={{ fontSize: '13px', lineHeight: '1.6', color: '#666', margin: 0 }}>
              The Coordinator uses <strong>LangChain-inspired routing</strong> with <strong>OpenAI</strong> to analyze your question and intelligently route it to the most appropriate specialist agent. No need to know which agent to ask!
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AskAnything;
