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
        flex items-center justify-center px-6 py-2.5 rounded-brand font-semibold transition-colors text-sm
        bg-cyber-blue-accent text-white hover:bg-cyber-blue disabled:bg-gray-300 disabled:text-gray-500 disabled:cursor-not-allowed
        shadow-sm active:scale-[0.98]
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
