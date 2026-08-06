import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, EyeOff, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { authApi, saveAuth } from '../api/mocks';
import cyberWordmark from '../assets/cyber-wordmark.svg';

export const Login = () => {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      toast.error('Введите логин и пароль');
      return;
    }
    setSubmitting(true);
    try {
      const res = await authApi.login(username.trim(), password);
      saveAuth(res);
      toast.success(`Добро пожаловать, ${res.display_name}`);
      navigate(res.role === 'student' ? '/status/my' : '/', { replace: true });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Не удалось войти');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex flex-col items-center justify-start bg-cyber-gray-surface pt-24 px-4">
      <img
        src={cyberWordmark}
        alt="КИБЕРПРОТЕКТ"
        className="h-12 w-auto mb-8 select-none"
        draggable={false}
      />

      <form
        onSubmit={onSubmit}
        className="bg-white rounded-brand shadow-[0_6px_24px_rgba(15,23,41,0.06)] border border-cyber-gray-border w-full max-w-lg px-10 py-9"
      >
        <h1 className="text-2xl font-medium text-cyber-gray-dark text-center mb-7">Войти</h1>

        <label className="block mb-4">
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Логин"
            autoComplete="username"
            autoFocus
            className="w-full px-4 py-3 bg-white border border-[#cad5f3] rounded-brand text-cyber-gray-dark placeholder-cyber-gray-light text-sm focus:outline-none focus:ring-2 focus:ring-cyber-blue-accent/30 focus:border-cyber-blue-accent transition-all"
          />
        </label>

        <label className="block mb-7 relative">
          <input
            type={showPassword ? 'text' : 'password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Пароль"
            autoComplete="current-password"
            className="w-full px-4 py-3 pr-11 bg-white border border-[#cad5f3] rounded-brand text-cyber-gray-dark placeholder-cyber-gray-light text-sm focus:outline-none focus:ring-2 focus:ring-cyber-blue-accent/30 focus:border-cyber-blue-accent transition-all"
          />
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            tabIndex={-1}
            aria-label={showPassword ? 'Скрыть пароль' : 'Показать пароль'}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-cyber-blue-accent hover:text-cyber-blue p-1"
          >
            {showPassword ? <Eye size={18} /> : <EyeOff size={18} />}
          </button>
        </label>

        <button
          type="submit"
          disabled={submitting}
          className="w-full flex items-center justify-center px-4 py-3 bg-cyber-blue-accent hover:bg-cyber-blue text-white font-semibold rounded-brand shadow-sm disabled:bg-gray-300 disabled:text-gray-500 transition-colors"
        >
          {submitting ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Войти'}
        </button>
      </form>
    </div>
  );
};
