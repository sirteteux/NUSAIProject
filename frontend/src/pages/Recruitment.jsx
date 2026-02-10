import React, { useState, useEffect } from 'react';
import { toast } from 'react-toastify';
import { recruitmentAPI } from '../services/api';
import '../pages/FAQ.css';

const Recruitment = () => {
  const [query, setQuery] = useState('');
  const [conversation, setConversation] = useState([]);
  const [loading, setLoading] = useState(false);
  const [openings, setOpenings] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);

  useEffect(() => {
    loadOpenings();
  }, []);

  const loadOpenings = async () => {
    try {
      const response = await recruitmentAPI.getOpenings();
      setOpenings(response.data.openings || []);
    } catch (error) {
      console.error('Failed to load openings');
    }
  };

  const handleQuerySubmit = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setConversation(prev => [...prev, { type: 'user', text: query }]);
    setLoading(true);

    try {
      const response = await recruitmentAPI.query(query);
      
      setConversation(prev => [...prev, { 
        type: 'ai', 
        text: response.data.answer
      }]);
      
      setQuery('');
      toast.success('Got answer from Recruitment AI!');
    } catch (error) {
      toast.error('Failed to get answer');
      setConversation(prev => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  const quickQuestions = [
    "What positions are currently open?",
    "What's the interview process?",
    "How long does hiring take?",
    "What skills are most valued?",
    "Tell me about company culture"
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">👔 Recruitment</h1>
        <p className="page-subtitle">
          <span className="badge badge-success">✅ AI-POWERED</span> Job openings and career opportunities
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '20px' }}>
        {/* Main Content */}
        <div>
          {/* AI Chat */}
          <div className="card">
            <h3 className="card-title">💬 Ask About Recruitment</h3>
            <div style={{ minHeight: '250px', maxHeight: '250px', overflowY: 'auto', padding: '16px', background: '#f8f9fa', borderRadius: '8px', marginBottom: '16px' }}>
              {conversation.length === 0 ? (
                <div style={{ textAlign: 'center', color: '#999', paddingTop: '60px' }}>
                  <div style={{ fontSize: '48px' }}>🎯</div>
                  <p>Ask me about job openings, hiring process, or career opportunities!</p>
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
                      <div style={{ padding: '10px 14px', background: 'white', borderRadius: '12px' }}>
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
                placeholder="Ask about recruitment..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={loading}
              />
              <button type="submit" className="btn btn-primary" disabled={loading || !query.trim()}>
                Send
              </button>
            </form>
          </div>

          {/* Job Openings */}
          <div className="card" style={{ marginTop: '20px' }}>
            <h3 className="card-title">📋 Current Openings ({openings.length})</h3>
            <div style={{ display: 'grid', gap: '12px' }}>
              {openings.map((job) => (
                <div key={job.id} style={{
                  padding: '16px',
                  background: '#f8f9fa',
                  borderRadius: '8px',
                  border: selectedJob?.id === job.id ? '2px solid #1976d2' : '1px solid #e0e0e0',
                  cursor: 'pointer',
                  transition: 'all 0.3s'
                }}
                onClick={() => setSelectedJob(selectedJob?.id === job.id ? null : job)}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                    <div style={{ flex: 1 }}>
                      <h4 style={{ margin: '0 0 8px 0', fontSize: '16px' }}>{job.title}</h4>
                      <div style={{ fontSize: '13px', color: '#666', marginBottom: '8px' }}>
                        🏢 {job.department} | 📍 {job.location} | 💼 {job.type}
                      </div>
                      <div style={{ fontSize: '13px', color: '#666' }}>
                        💰 {job.salary_range} | 📅 Posted: {job.posted}
                      </div>
                      {selectedJob?.id === job.id && (
                        <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid #ddd' }}>
                          <p style={{ fontSize: '13px', margin: '8px 0' }}><strong>Description:</strong> {job.description}</p>
                          <p style={{ fontSize: '13px', margin: '8px 0' }}><strong>Skills:</strong> {job.skills.join(', ')}</p>
                          <p style={{ fontSize: '13px', margin: '8px 0' }}><strong>Experience:</strong> {job.experience}</p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
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
                  className="popular-question-btn"
                  onClick={() => setQuery(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>

          <div className="card" style={{ marginTop: '16px' }}>
            <h3 className="card-title">💡 Recruitment Tips</h3>
            <ul style={{ fontSize: '13px', lineHeight: '1.8', paddingLeft: '20px', margin: 0 }}>
              <li>Tailor your resume to the job</li>
              <li>Research the company</li>
              <li>Prepare for behavioral questions</li>
              <li>Follow up after interviews</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Recruitment;
