import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}





export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '' };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error?.message || 'Неизвестная ошибка' };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {

    console.error('[UI ErrorBoundary]', error, info.componentStack);
  }

  handleReset = () => {
    this.setState({ hasError: false, message: '' });
    window.location.assign('/');
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="max-w-lg mx-auto mt-16 text-center">
        <div className="bg-white rounded-brand shadow-sm border border-gray-200 p-12">
          <h2 className="text-xl font-bold text-cyber-gray-dark mb-2">Что-то пошло не так</h2>
          <p className="text-cyber-gray-light text-sm mb-6">
            Интерфейс столкнулся с ошибкой при отображении страницы.
          </p>
          <code className="block text-xs text-red-600 bg-red-50 border border-red-100 rounded p-3 mb-8 break-all">
            {this.state.message}
          </code>
          <button
            onClick={this.handleReset}
            className="inline-flex items-center px-6 py-3 bg-cyber-blue-accent text-white rounded-brand font-semibold hover:bg-cyber-blue transition-colors"
          >
            Вернуться на главную
          </button>
        </div>
      </div>
    );
  }
}
