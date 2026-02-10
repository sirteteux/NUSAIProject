import React from 'react';
import { useAuthStore } from '../stores/authStore';

const Profile = () => {
  const { user } = useAuthStore();

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">👤 Profile</h1>
        <p className="page-subtitle">Your account information</p>
      </div>

      <div className="card">
        <h3 className="card-title">Personal Information</h3>
        <div style={{ display: 'grid', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '13px', color: '#666', marginBottom: '4px' }}>Name</label>
            <div style={{ fontSize: '16px' }}>{user?.name}</div>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '13px', color: '#666', marginBottom: '4px' }}>Email</label>
            <div style={{ fontSize: '16px' }}>{user?.email}</div>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '13px', color: '#666', marginBottom: '4px' }}>Employee ID</label>
            <div style={{ fontSize: '16px' }}>{user?.employeeId}</div>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '13px', color: '#666', marginBottom: '4px' }}>Department</label>
            <div style={{ fontSize: '16px' }}>{user?.department || 'Not specified'}</div>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '13px', color: '#666', marginBottom: '4px' }}>Role</label>
            <div style={{ fontSize: '16px', textTransform: 'capitalize' }}>{user?.role}</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Profile;
