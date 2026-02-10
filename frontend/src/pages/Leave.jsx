import React, { useState, useEffect } from 'react';
import { toast } from 'react-toastify';
import { leaveAPI } from '../services/api';
import { useAuthStore } from '../stores/authStore';

const Leave = () => {
  const { user } = useAuthStore();
  const [balance, setBalance] = useState(null);
  const [query, setQuery] = useState('');
  const [conversation, setConversation] = useState([]);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    type: 'annual',
    start_date: '',
    end_date: '',
    reason: ''
  });

  useEffect(() => {
    loadBalance();
  }, []);

  const loadBalance = async () => {
    try {
      const res = await leaveAPI.getBalance();
      setBalance(res.data.balances);
    } catch (error) {
      toast.error('Failed to load balance');
    }
  };

  const handleQuerySubmit = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setConversation(prev => [...prev, { type: 'user', text: query }]);
    setLoading(true);

    try {
      const response = await leaveAPI.query(query);
      
      setConversation(prev => [...prev, { 
        type: 'ai', 
        text: response.data.answer
      }]);
      
      setQuery('');
      toast.success('Got answer from Leave AI!');
    } catch (error) {
      toast.error('Failed to get answer');
      setConversation(prev => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  const handleLeaveSubmit = async (e) => {
    e.preventDefault();
    try {
      const res = await leaveAPI.request(formData);
      toast.success(`Leave request ${res.data.request_id} submitted!`);
      setFormData({ type: 'annual', start_date: '', end_date: '', reason: '' });
      loadBalance(); // Refresh balance
    } catch (error) {
      toast.error(error.response?.data?.details || 'Failed to submit');
    }
  };

  const quickQuestions = [
    "How many leave days do I have?",
    "What's the leave policy?",
    "How do I request sick leave?",
    "When should I submit my leave?",
    "What types of leave are available?"
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">📅 Leave Management</h1>
        <p className="page-subtitle">
          <span className="badge badge-success">✅ AI-POWERED</span> Request and track your leave
        </p>
      </div>

      {/* Leave Balance */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '24px' }}>
        {balance && Object.entries(balance).map(([type, data]) => (
          <div key={type} className="card" style={{ textAlign: 'center' }}>
            <h4 style={{ textTransform: 'capitalize', marginBottom: '12px', fontSize: '16px' }}>{type} Leave</h4>
            <div style={{ fontSize: '36px', fontWeight: 'bold', color: '#1976d2' }}>{data.remaining}</div>
            <div style={{ fontSize: '13px', color: '#666', marginTop: '4px' }}>of {data.total} days remaining</div>
            <div style={{ fontSize: '12px', color: '#999', marginTop: '8px' }}>Used: {data.used} days</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '20px' }}>
        {/* AI Chat */}
        <div>
          <div className="card">
            <h3 className="card-title">💬 Ask About Leave</h3>
            <div style={{ minHeight: '200px', maxHeight: '200px', overflowY: 'auto', padding: '16px', background: '#f8f9fa', borderRadius: '8px', marginBottom: '16px' }}>
              {conversation.length === 0 ? (
                <div style={{ textAlign: 'center', color: '#999', paddingTop: '40px' }}>
                  <div style={{ fontSize: '48px' }}>📅</div>
                  <p>Ask me about leave policies and your balance!</p>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {conversation.map((msg, index) => (
                    <div key={index} style={{ 
                      display: 'flex',
                      justifyContent: msg.type === 'user' ? 'flex-end' : 'flex-start'
                    }}>
                      <div style={{
                        maxWidth: '70%',
                        padding: '10px 14px',
                        borderRadius: '12px',
                        background: msg.type === 'user' ? '#1976d2' : 'white',
                        color: msg.type === 'user' ? 'white' : '#333',
                        boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                      }}>
                        {msg.text}
                      </div>
                    </div>
                  ))}
                  {loading && (
                    <div style={{ display: 'flex' }}>
                      <div style={{ padding: '10px 14px', background: 'white', borderRadius: '12px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
                        <div className="typing-indicator">
                          <span></span><span></span><span></span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            <form onSubmit={handleQuerySubmit} style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                className="form-input"
                placeholder="Ask about leave policies..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={loading}
              />
              <button type="submit" className="btn btn-primary" disabled={loading || !query.trim()}>
                Send
              </button>
            </form>
          </div>

          {/* Leave Request Form */}
          <div className="card" style={{ marginTop: '20px' }}>
            <h3 className="card-title">📝 Request Leave</h3>
            <form onSubmit={handleLeaveSubmit}>
              <div className="form-group">
                <label className="form-label">Leave Type</label>
                <select className="form-select" value={formData.type} onChange={(e) => setFormData({...formData, type: e.target.value})}>
                  <option value="annual">Annual Leave</option>
                  <option value="sick">Sick Leave</option>
                  <option value="personal">Personal Leave</option>
                </select>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div className="form-group">
                  <label className="form-label">Start Date</label>
                  <input type="date" className="form-input" value={formData.start_date} onChange={(e) => setFormData({...formData, start_date: e.target.value})} required />
                </div>
                <div className="form-group">
                  <label className="form-label">End Date</label>
                  <input type="date" className="form-input" value={formData.end_date} onChange={(e) => setFormData({...formData, end_date: e.target.value})} required />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Reason (Optional)</label>
                <textarea className="form-textarea" style={{ minHeight: '60px' }} value={formData.reason} onChange={(e) => setFormData({...formData, reason: e.target.value})} />
              </div>
              <button type="submit" className="btn btn-success">Submit Leave Request</button>
            </form>
          </div>
        </div>

        {/* Sidebar */}
        <div>
          <div className="card">
            <h3 className="card-title">Quick Questions</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {quickQuestions.map((q, index) => (
                <button
                  key={index}
                  style={{
                    background: '#f5f5f5',
                    border: '1px solid #e0e0e0',
                    padding: '10px',
                    borderRadius: '6px',
                    textAlign: 'left',
                    cursor: 'pointer',
                    fontSize: '13px',
                    transition: 'all 0.3s'
                  }}
                  onClick={() => setQuery(q)}
                  onMouseEnter={(e) => {
                    e.target.style.background = '#e3f2fd';
                    e.target.style.borderColor = '#1976d2';
                  }}
                  onMouseLeave={(e) => {
                    e.target.style.background = '#f5f5f5';
                    e.target.style.borderColor = '#e0e0e0';
                  }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Leave;
