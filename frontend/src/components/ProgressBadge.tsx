import React from 'react';
import type { StandStatus } from '../types/api';

interface ProgressBadgeProps {
  status: StandStatus;
}

export const ProgressBadge: React.FC<ProgressBadgeProps> = ({ status }) => {
  const config: Record<StandStatus, { color: string, label: string, animate?: boolean }> = {
    READY: { color: 'bg-green-50 text-green-700 border-green-200', label: 'ГОТОВ' },
    DEPLOYING: { color: 'bg-yellow-50 text-yellow-700 border-yellow-200', label: 'РАЗВЕРТЫВАНИЕ', animate: true },
    PENDING: { color: 'bg-gray-100 text-cyber-gray-dark border-gray-300', label: 'В ОЧЕРЕДИ' },
    FREEZE: { color: 'bg-cyber-blue-accent text-white border-cyber-blue', label: 'ЗАМОРОЖЕН' },
    CLEANING: { color: 'bg-red-50 text-red-700 border-red-200', label: 'ОЧИСТКА' },
    FREE: { color: 'bg-slate-50 text-slate-600 border-slate-200', label: 'СВОБОДЕН' },
    FAILED: { color: 'bg-red-600 text-white border-red-700', label: 'ОШИБКА' }
  };

  const { color, label, animate } = config[status] || config.PENDING;

  return (
    <span className={`
      px-3 py-1 rounded-brand text-xs font-bold border tracking-wide uppercase
      ${color}
      ${animate ? 'animate-pulse' : ''}
    `}>
      {label}
    </span>
  );
};
