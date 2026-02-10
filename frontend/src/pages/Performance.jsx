import React, { useState, useEffect } from 'react';
import { toast } from 'react-toastify';
import { performanceAPI } from '../services/api';
import { useAuthStore } from '../stores/authStore';

const Performance = () => {
  const { user } = useAuthStore();
  const [query, setQuery] = useState('');
  const [conversation, setConversation] = useState([]);
  const [loading, setLoading] = useState(false);
  const [goals, setGoals] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [showNewGoal, setShowNewGoal] = useState(false);
  const [newGoal, setNewGoal] = useState({
    title: '',
    description: '',
    target_date: ''
  });

  useEffect(() => {
    loadGoals();
    loadReviews();
  }, []);

  const loadGoals = async () => {
    try {
      const res = await performanceAPI.getGoals();
      setGoals(res.data.goals || []);
    } catch (error) {
      console.error('Failed to load goals');
    }
  };

  const loadReviews = async () => {
    try {
      const res = await performanceAPI.getReviews();
      setReviews(res.data.reviews || []);
    } catch (error) {
      console.error('Failed to load reviews');
    }
  };

  const handleQuerySubmit = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setConversation(prev => [...prev, { type: 'user', text: query }]);
    setLoading(true);

    try {
      const response = await performanceAPI.query(query);
      
      setConversation(prev => [...prev, { 
        type: 'ai', 
        text: response.data.answer
      }]);
      
      setQuery('');
      toast.success('Got answer from Performance AI!');
    } catch (error) {
      toast.error('Failed to get answer');
      setConversation(prev => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  const handleCreateGoal = async (e) => {
    e.preventDefault();
    try {
      await performanceAPI.createGoal(newGoal);
      toast.success('Goal created successfully!');
      setShowNewGoal(false);
      setNewGoal({ title: '', description: '', target_date: '' });
      loadGoals();
    } catch (error) {
      toast.error('Failed to create goal');
    }
  };

  const handleUpdateGoal = async (goalId, progress) => {
    try {
      await performanceAPI.updateGoal({ goal_id: goalId, progress });
      toast.success('Goal updated!');
      loadGoals();
    } catch (error) {
      toast.error('Failed to update goal');
    }
  };

  const getStatusColor = (status) => {
    switch(status) {
      case 'on-track': return '#4caf50';
      case 'in-progress': return '#ff9800';
      case 'needs-attention': return '#f44336';
      default: return '#999';
    }
  };

  const quickQuestions = [
    "How am I performing?",
    "What are my current goals?",
    "How do I set better goals?",
    "When is my next review?",
    "What should I focus on?"
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">📈 Performance & KPIs</h1>
        <p className="page-subtitle">
          <span className="badge badge-success">✅ AI-POWERED</span> Track goals and performance
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '20px' }}>
        {/* Main Content */}
        <div>
          {/* AI Chat */}
          <div className="card">
            <h3 className="card-title">💬 Ask About Performance</h3>
            <div style={{ minHeight: '200px', maxHeight: '200px', overflowY: 'auto', padding: '16px', background: '#f8f9fa', borderRadius: '8px', marginBottom: '16px' }}>
              {conversation.length === 0 ? (
                <div style={{ textAlign: 'center', color: '#999', paddingTop: '40px' }}>
                  <div style={{ fontSize: '48px' }}>🎯</div>
                  <p>Ask me about your performance, goals, or development!</p>
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
                placeholder="Ask about performance..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={loading}
              />
              <button type="submit" className="btn btn-primary" disabled={loading || !query.trim()}>
                Send
              </button>
            </form>
          </div>

          {/* Goals */}
          <div className="card" style={{ marginTop: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 className="card-title" style={{ margin: 0 }}>🎯 Current Goals ({goals.length})</h3>
              <button className="btn btn-primary" onClick={() => setShowNewGoal(!showNewGoal)} style={{ padding: '6px 12px', fontSize: '13px' }}>
                {showNewGoal ? 'Cancel' : '+ New Goal'}
              </button>
            </div>

            {showNewGoal && (
              <form onSubmit={handleCreateGoal} style={{ padding: '16px', background: '#f8f9fa', borderRadius: '8px', marginBottom: '16px' }}>
                <div className="form-group">
                  <label className="form-label">Goal Title</label>
                  <input type="text" className="form-input" value={newGoal.title} onChange={(e) => setNewGoal({...newGoal, title: e.target.value})} required />
                </div>
                <div className="form-group">
                  <label className="form-label">Description</label>
                  <textarea className="form-textarea" style={{ minHeight: '60px' }} value={newGoal.description} onChange={(e) => setNewGoal({...newGoal, description: e.target.value})} required />
                </div>
                <div className="form-group">
                  <label className="form-label">Target Date</label>
                  <input type="date" className="form-input" value={newGoal.target_date} onChange={(e) => setNewGoal({...newGoal, target_date: e.target.value})} required />
                </div>
                <button type="submit" className="btn btn-success">Create Goal</button>
              </form>
            )}

            <div style={{ display: 'grid', gap: '12px' }}>
              {goals.map((goal) => (
                <div key={goal.id} style={{ padding: '16px', background: '#f8f9fa', borderRadius: '8px', borderLeft: `4px solid ${getStatusColor(goal.status)}` }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <h4 style={{ margin: 0, fontSize: '15px' }}>{goal.title}</h4>
                    <span style={{
                      padding: '2px 8px',
                      borderRadius: '12px',
                      fontSize: '11px',
                      fontWeight: 'bold',
                      background: getStatusColor(goal.status),
                      color: 'white'
                    }}>
                      {goal.status}
                    </span>
                  </div>
                  <p style={{ fontSize: '13px', color: '#666', margin: '8px 0' }}>{goal.description}</p>
                  <div style={{ marginTop: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                      <span>Progress</span>
                      <span>{goal.progress}%</span>
                    </div>
                    <div style={{ height: '8px', background: '#e0e0e0', borderRadius: '4px', overflow: 'hidden' }}>
                      <div style={{ width: `${goal.progress}%`, height: '100%', background: getStatusColor(goal.status), transition: 'width 0.3s' }}></div>
                    </div>
                  </div>
                  <div style={{ marginTop: '8px', fontSize: '12px', color: '#999' }}>
                    Due: {goal.target_date}
                  </div>
                  <div style={{ marginTop: '12px', display: 'flex', gap: '8px' }}>
                    <button className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: '12px' }} onClick={() => handleUpdateGoal(goal.id, Math.min(100, goal.progress + 10))}>
                      +10%
                    </button>
                    <button className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: '12px' }} onClick={() => handleUpdateGoal(goal.id, Math.min(100, goal.progress + 25))}>
                      +25%
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Reviews */}
          {reviews.length > 0 && (
            <div className="card" style={{ marginTop: '20px' }}>
              <h3 className="card-title">📊 Performance Reviews</h3>
              <div style={{ display: 'grid', gap: '12px' }}>
                {reviews.slice(0, 2).map((review) => (
                  <div key={review.id} style={{ padding: '16px', background: '#f8f9fa', borderRadius: '8px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <h4 style={{ margin: 0, fontSize: '15px' }}>{review.period}</h4>
                      <span style={{
                        padding: '4px 12px',
                        borderRadius: '12px',
                        fontSize: '13px',
                        fontWeight: 'bold',
                        background: '#4caf50',
                        color: 'white'
                      }}>
                        {review.rating}/5.0
                      </span>
                    </div>
                    <p style={{ fontSize: '13px', color: '#666', margin: '8px 0' }}>
                      {review.summary}
                    </p>
                    <div style={{ fontSize: '12px', color: '#999', marginTop: '8px' }}>
                      Reviewed by: {review.reviewer}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
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
            <h3 className="card-title">💡 Performance Tips</h3>
            <ul style={{ fontSize: '13px', lineHeight: '1.8', paddingLeft: '20px', margin: 0 }}>
              <li>Set SMART goals</li>
              <li>Track progress weekly</li>
              <li>Seek regular feedback</li>
              <li>Document achievements</li>
              <li>Focus on development</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Performance;
