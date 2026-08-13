import React from 'react';
import { Loader2 } from 'lucide-react';

interface DeployButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  isLoading?: boolean;
}

export const DeployButton: React.FC<DeployButtonProps> = ({
  children,
  isLoading,
  className = '',
  ...props
}) => {
  return (
    <button
      disabled={isLoading || props.disabled}
      className={`
        flex items-center justify-center px-6 py-3 rounded-brand font-semibold transition-all text-sm
        bg-cyber-blue-accent text-white hover:bg-cyber-blue-dark disabled:bg-gray-300 disabled:text-gray-500 disabled:cursor-not-allowed
        shadow-[0_8px_22px_rgba(0,63,255,0.18)] hover:shadow-[0_10px_26px_rgba(0,32,77,0.2)] active:translate-y-px
        ${className}
      `}
      {...props}
    >
      {isLoading ? (
        <>
          <Loader2 className="w-5 h-5 mr-2 animate-spin" />
          Выполнение...
        </>
      ) : (
        children
      )}
    </button>
  );
};
