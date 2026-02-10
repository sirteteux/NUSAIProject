import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import './Dashboard.css';

const Dashboard = () => {
  const navigate = useNavigate();
  const { user } = useAuthStore();

  const stats = [
    { label: 'FAQ Queries Today', value: '12', icon: '❓', color: '#4caf50' },
    { label: 'Pending Leave Requests', value: '3', icon: '📅', color: '#ff9800' },
    { label: 'Open Positions', value: '5', icon: '👔', color: '#2196f3' },
    { label: 'Performance Reviews Due', value: '2', icon: '📈', color: '#9c27b0' },
  ];

  const quickActions = [
    { label: 'Ask FAQ', path: '/faq', icon: '❓', working: true },
    { label: 'Payroll Query', path: '/payroll', icon: '💰', working: true },
    { label: 'Request Leave', path: '/leave', icon: '📅', working: true },
    { label: 'View Goals', path: '/performance', icon: '🎯', working: true },
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Welcome back, {user?.name}! 👋</h1>
        <p className="page-subtitle">Here's what's happening with your HR today</p>
      </div>

      <div className="stats-grid">
        {stats.map((stat, index) => (
          <div key={index} className="stat-card" style={{ borderLeftColor: stat.color }}>
            <div className="stat-icon" style={{ color: stat.color }}>
              {stat.icon}
            </div>
            <div className="stat-info">
              <div className="stat-value">{stat.value}</div>
              <div className="stat-label">{stat.label}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="quick-actions-section">
        <h2>Quick Actions</h2>
        <div className="quick-actions-grid">
          {quickActions.map((action, index) => (
            <button
              key={index}
              className="quick-action-card"
              onClick={() => navigate(action.path)}
            >
              <div className="action-icon">{action.icon}</div>
              <div className="action-label">{action.label}</div>
              {action.working && (
                <span className="badge badge-success">Working</span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <h3 className="card-title">📢 Phase 3 Status</h3>
        <div className="status-info">
          <p><strong>✅ Working AI Agents:</strong></p>
          <ul style={{ marginLeft: '20px', marginTop: '8px' }}>
            <li>FAQ Agent - General HR questions</li>
            <li>Payroll Agent - Salary and compensation queries</li>
            <li>Leave Agent - Leave requests and balance tracking</li>
          </ul>
          <p style={{ marginTop: '16px' }}><strong>🎨 Mock Data:</strong> Recruitment, Performance (UI complete)</p>
          <p><strong>Coming in Phase 3:</strong> Recruitment & Performance AI agents</p>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
