/**
 * 表现层 - Ping 按钮组件
 */
import React from 'react';

interface PingButtonProps {
  onClick: () => void;
  isLoading: boolean;
}

export const PingButton: React.FC<PingButtonProps> = ({ onClick, isLoading }) => {
  return (
    <button
      onClick={onClick}
      disabled={isLoading}
      style={{
        padding: '12px 24px',
        fontSize: '16px',
        backgroundColor: isLoading ? '#ccc' : '#4CAF50',
        color: 'white',
        border: 'none',
        borderRadius: '4px',
        cursor: isLoading ? 'not-allowed' : 'pointer',
        transition: 'background-color 0.3s',
      }}
    >
      {isLoading ? 'Pinging...' : 'Ping Server'}
    </button>
  );
};
