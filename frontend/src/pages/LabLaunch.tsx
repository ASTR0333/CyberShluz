import { useState } from 'react';
import { mockApi, getAuth } from '../api/mocks';
import { DeployButton } from '../components/DeployButton';
import { Server, Cpu, HardDrive, Clock, CheckCircle2, ArrowRight } from 'lucide-react';
import toast from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';

export const LabLaunch = () => {
  const labId = 3;
  const auth = getAuth();
  const isTeacher = auth?.role === 'teacher' || auth?.role === 'admin';


  const [userId, setUserId] = useState(auth?.username || 'student');
  const [isDeploying, setIsDeploying] = useState(false);
  const [standId, setStandId] = useState<string | null>(null);
  const navigate = useNavigate();

  const handleDeploy = async () => {
    setIsDeploying(true);
    try {
      const res = await mockApi.deploy({
        user_id: userId,
        lab_id: labId,
        role: isTeacher ? 'teacher' : 'student',
      });
      toast.success('Стенд зарезервирован! Деплой запущен.');
      setStandId(res.stand_id);
      localStorage.setItem('my_stand_id', res.stand_id);
      localStorage.setItem('my_user_id', userId);
      setTimeout(() => navigate(`/status/${res.stand_id}`), 1500);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Ошибка при запуске стенда');
    } finally {
      setIsDeploying(false);
    }
  };

  const steps = [
    'Проверка ёмкости кластера (<90%)',
    'Выделение проекта из пула',
    'Генерация SSH-ключей',
    'Создание ВМ и Floating IP',
    'Настройка Security Groups',
  ];

  return (
    <div className="max-w-5xl mx-auto space-y-6">

      <section className="bg-white rounded-brand border border-cyber-gray-border overflow-hidden">
        <div className="h-1 bg-cyber-blue-accent" />
        <div className="px-8 py-7 border-b border-cyber-gray-border flex items-center justify-between">
          <div>
            <p className="text-[11px] font-bold text-cyber-gray-light uppercase tracking-[0.18em]">
              Лабораторные работы
            </p>
            <h1 className="text-[22px] font-bold text-cyber-gray-dark mt-1 flex items-center">
              <Server className="w-5 h-5 mr-2.5 text-cyber-blue-accent" />
              Запуск лабораторной работы
            </h1>
          </div>
          <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-cyber-blue/5 border border-cyber-blue/15 text-cyber-blue text-[11px] font-semibold uppercase tracking-wider">
            Кибер Инфраструктура
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-5 divide-y lg:divide-y-0 lg:divide-x divide-cyber-gray-border">

          <div className="lg:col-span-3 p-8 space-y-5">
            {isTeacher ? (
              <div>
                <label className="block text-[11px] font-bold text-cyber-gray-light uppercase tracking-[0.14em] mb-2">
                  Идентификатор студента (тест-деплой)
                </label>
                <input
                  type="text"
                  value={userId}
                  onChange={(e) => setUserId(e.target.value)}
                  className="w-full px-4 py-2.5 bg-white border border-cyber-gray-border rounded-brand focus:ring-2 focus:ring-cyber-blue-accent/30 focus:border-cyber-blue-accent outline-none transition-all text-cyber-gray-dark text-sm"
                  placeholder="student-001"
                />
              </div>
            ) : (
              <div>
                <label className="block text-[11px] font-bold text-cyber-gray-light uppercase tracking-[0.14em] mb-2">
                  Пользователь
                </label>
                <div className="w-full px-4 py-2.5 bg-cyber-gray-surface border border-cyber-gray-border rounded-brand text-cyber-gray-dark text-sm">
                  {auth?.display_name} <span className="font-mono text-cyber-gray-light text-xs">({auth?.username})</span>
                </div>
              </div>
            )}

            <div>
              <label className="block text-[11px] font-bold text-cyber-gray-light uppercase tracking-[0.14em] mb-2">
                Лабораторная работа
              </label>
              <div className="w-full px-4 py-2.5 bg-cyber-gray-surface border border-cyber-gray-border rounded-brand text-cyber-gray-dark text-sm flex items-center justify-between">
                <span><span className="font-mono font-bold text-cyber-blue mr-2">№3</span> Подключение хранилища</span>
                <span className="text-[11px] text-cyber-gray-light uppercase tracking-wider">Кибер Инфраструктура</span>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div className="p-3 rounded-brand border border-cyber-gray-border bg-cyber-gray-surface">
                <Cpu className="w-4 h-4 text-cyber-blue-accent mb-1.5" />
                <p className="text-[10px] font-bold text-cyber-gray-light uppercase tracking-wider">ВМ</p>
                <p className="text-base font-bold text-cyber-gray-dark mt-0.5">5 × 2 vCPU</p>
              </div>
              <div className="p-3 rounded-brand border border-cyber-gray-border bg-cyber-gray-surface">
                <HardDrive className="w-4 h-4 text-cyber-blue-accent mb-1.5" />
                <p className="text-[10px] font-bold text-cyber-gray-light uppercase tracking-wider">ОЗУ</p>
                <p className="text-base font-bold text-cyber-gray-dark mt-0.5">4 ГБ × 5</p>
              </div>
              <div className="p-3 rounded-brand border border-cyber-gray-border bg-cyber-gray-surface">
                <Clock className="w-4 h-4 text-cyber-blue-accent mb-1.5" />
                <p className="text-[10px] font-bold text-cyber-gray-light uppercase tracking-wider">TTL</p>
                <p className="text-base font-bold text-cyber-gray-dark mt-0.5">2 часа</p>
              </div>
            </div>

            <DeployButton onClick={handleDeploy} isLoading={isDeploying} className="w-full">
              <ArrowRight className="w-4 h-4 mr-2" /> Запустить стенд
            </DeployButton>
          </div>


          <div className="lg:col-span-2 p-8 bg-cyber-gray-surface">
            <p className="text-[11px] font-bold text-cyber-gray-light uppercase tracking-[0.14em] mb-4">
              Процесс развертывания
            </p>
            <ol className="space-y-3">
              {steps.map((step, i) => (
                <li key={i} className="flex items-start text-sm text-cyber-gray-dark">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-white border border-cyber-blue-accent/30 text-cyber-blue-accent text-[11px] font-bold flex items-center justify-center mr-3 mt-0.5">
                    {i + 1}
                  </span>
                  {step}
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      {standId && (
        <div className="flex items-center gap-3 bg-emerald-50 border border-emerald-200 rounded-brand p-4 text-emerald-800 text-sm">
          <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
          <p>
            Стенд <code className="font-mono bg-white border border-emerald-200 px-1.5 py-0.5 rounded">{standId}</code> принят в работу. Перенаправление…
          </p>
        </div>
      )}
    </div>
  );
};
