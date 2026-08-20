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
    <div className="min-h-screen w-full grid lg:grid-cols-[1.05fr_0.95fr] bg-white">
      <section className="hidden lg:flex relative overflow-hidden bg-cyber-blue-dark text-white p-12 xl:p-16 flex-col justify-between">
        <div className="absolute inset-0 brand-grid opacity-40" />
        <div className="absolute -right-28 top-[12%] w-80 h-80 border-[70px] border-cyber-blue-accent/30 rotate-45 rounded-[3rem]" />
        <div className="absolute right-[18%] bottom-[8%] w-48 h-48 bg-cyber-blue-light/20 rotate-45 rounded-[2rem]" />

        <img
          src={cyberWordmark}
          alt="КИБЕРПРОТЕКТ"
          className="relative h-11 w-auto self-start brightness-0 invert select-none"
          draggable={false}
        />

        <div className="relative max-w-xl py-14">
          <h1 className="text-5xl xl:text-6xl font-black leading-[0.98] tracking-[-0.045em]">
            Управляйте<br />КиберШлюзом<br />в едином окне
          </h1>
          <p className="max-w-md mt-7 text-base leading-7 text-white/70">
            Изолированные лабораторные стенды, прозрачный контроль ресурсов и безопасная оркестрация инфраструктуры.
          </p>
        </div>

      </section>

      <section className="brand-surface flex min-h-screen items-center justify-center px-5 py-12 sm:px-10">
        <div className="w-full max-w-md">
          <img
            src={cyberWordmark}
            alt="КИБЕРПРОТЕКТ"
            className="lg:hidden h-10 w-auto mb-12 select-none"
            draggable={false}
          />

          <div className="mb-8">
            <h2 className="text-3xl sm:text-4xl font-black tracking-[-0.035em] text-cyber-blue-dark">Вход в систему</h2>
            <p className="text-sm text-cyber-gray-light mt-3">Используйте учётную запись учебной платформы.</p>
          </div>

          <form onSubmit={onSubmit} className="brand-card p-6 sm:p-8">
            <label className="block mb-5">
              <span className="block text-xs font-bold text-cyber-blue-dark mb-2">Логин</span>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Введите логин"
                autoComplete="username"
                autoFocus
                className="w-full px-4 py-3.5 bg-white border border-cyber-gray-border rounded-brand text-cyber-gray-dark placeholder:text-cyber-gray-light/70 text-sm focus:outline-none focus:ring-2 focus:ring-cyber-blue-accent/20 focus:border-cyber-blue-accent transition-all"
              />
            </label>

            <label className="block mb-7 relative">
              <span className="block text-xs font-bold text-cyber-blue-dark mb-2">Пароль</span>
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Введите пароль"
                autoComplete="current-password"
                className="w-full px-4 py-3.5 pr-12 bg-white border border-cyber-gray-border rounded-brand text-cyber-gray-dark placeholder:text-cyber-gray-light/70 text-sm focus:outline-none focus:ring-2 focus:ring-cyber-blue-accent/20 focus:border-cyber-blue-accent transition-all"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? 'Скрыть пароль' : 'Показать пароль'}
                className="absolute right-3 bottom-2.5 text-cyber-blue-accent hover:text-cyber-blue p-1.5"
              >
                {showPassword ? <Eye size={18} /> : <EyeOff size={18} />}
              </button>
            </label>

            <button
              type="submit"
              disabled={submitting}
              className="w-full flex items-center justify-center px-4 py-3.5 bg-cyber-blue-accent hover:bg-cyber-blue-dark text-white font-semibold rounded-brand shadow-[0_8px_22px_rgba(0,63,255,0.2)] disabled:bg-gray-300 disabled:text-gray-500 transition-all"
            >
              {submitting ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Войти'}
            </button>
          </form>
        </div>
      </section>
    </div>
  );
};
