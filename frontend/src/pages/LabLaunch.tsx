import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Cpu,
  Network,
  Server,
  Settings2,
  ToggleLeft,
  ToggleRight,
} from 'lucide-react';

import { mockApi, getAuth } from '../api/mocks';
import { DeployButton } from '../components/DeployButton';
import type { DeploymentConfig, DeploymentOptions, VMDeploymentSpec } from '../types/api';


export const LabLaunch = () => {
  const labId = 3;
  const auth = getAuth();
  const isTeacher = auth?.role === 'teacher' || auth?.role === 'admin';
  const userId = auth?.username || 'student';
  const [isDeploying, setIsDeploying] = useState(false);
  const [standId, setStandId] = useState<string | null>(null);
  const [options, setOptions] = useState<DeploymentOptions | null>(null);
  const [deployment, setDeployment] = useState<DeploymentConfig | null>(null);
  const [showSettings, setShowSettings] = useState(true);
  const [existingStandChecked, setExistingStandChecked] = useState(isTeacher);
  const navigate = useNavigate();

  useEffect(() => {
    if (isTeacher) return;
    let alive = true;
    mockApi.getMyStands()
      .then((stands) => {
        if (!alive) return;
        if (stands.length > 0) {
          navigate(`/status/${stands[0].stand_id}`, { replace: true });
          return;
        }
        setExistingStandChecked(true);
      })
      .catch(() => {
        if (alive) setExistingStandChecked(true);
      });
    return () => { alive = false; };
  }, [isTeacher, navigate]);

  useEffect(() => {
    if (!isTeacher) return;
    mockApi.getDeploymentOptions()
      .then((data) => {
        setOptions(data);
        setDeployment(data.default);
      })
      .catch((error: unknown) => {
        toast.error(error instanceof Error ? error.message : 'Не удалось загрузить параметры OpenStack');
      });
  }, [isTeacher]);

  const enabledVMs = useMemo(
    () => deployment?.vms.filter((vm) => vm.enabled) ?? [],
    [deployment],
  );

  const updateNetwork = (field: keyof DeploymentConfig['network'], value: string) => {
    setDeployment((current) => current ? {
      ...current,
      network: {
        ...current.network,
        [field]: field === 'dns_nameservers'
          ? value.split(',').map((item) => item.trim()).filter(Boolean)
          : value,
      },
    } : current);
  };

  const updateVM = (index: number, field: keyof VMDeploymentSpec, value: string | boolean) => {
    setDeployment((current) => current ? {
      ...current,
      vms: current.vms.map((vm, vmIndex) => vmIndex === index ? { ...vm, [field]: value } : vm),
    } : current);
  };

  const handleDeploy = async () => {
    if (isTeacher && !deployment) return;
    setIsDeploying(true);
    try {
      const res = await mockApi.deploy({
        user_id: userId,
        lab_id: labId,
        role: isTeacher ? 'teacher' : 'student',
        ...(isTeacher && deployment ? { deployment } : {}),
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
    'Проверка выбранных образов, конфигураций и IP-адресов',
    'Проверка квоты с учётом выбранных vCPU',
    'Выделение проекта из пула',
    'Создание изолированной сети и пяти ВМ',
    'Настройка SSH, Security Group и Floating IP',
  ];

  if (!existingStandChecked || (isTeacher && (!deployment || !options))) {
    return <div className="max-w-5xl mx-auto p-10 text-center text-cyber-gray-light">Загрузка каталога OpenStack…</div>;
  }

  if (!isTeacher) {
    return (
      <div className="max-w-xl mx-auto">
        <section className="bg-white rounded-brand border border-cyber-gray-border overflow-hidden">
          <div className="h-1 bg-cyber-blue-accent" />
          <div className="p-8">
            <p className="text-[11px] font-bold text-cyber-gray-light uppercase tracking-[0.18em]">Лабораторная работа №3</p>
            <h1 className="text-[22px] font-bold text-cyber-gray-dark mt-1 flex items-center">
              <Server className="w-5 h-5 mr-2.5 text-cyber-blue-accent" />
              Развёртывание стенда
            </h1>
            <p className="mt-3 mb-6 text-sm text-cyber-gray-light">
              Параметры виртуальных машин и изолированная сеть назначаются автоматически.
            </p>
            <DeployButton onClick={handleDeploy} isLoading={isDeploying} className="w-full">
              <ArrowRight className="w-4 h-4 mr-2" /> Развернуть
            </DeployButton>

            {standId && (
              <div className="mt-5 flex items-center gap-3 bg-emerald-50 border border-emerald-200 rounded-brand p-4 text-emerald-800 text-sm">
                <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
                Стенд принят в работу. Перенаправление…
              </div>
            )}
          </div>
        </section>
      </div>
    );
  }

  // The guards above ensure both values exist for the teacher-only editor.
  const teacherDeployment = deployment!;
  const teacherOptions = options!;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <section className="brand-card overflow-hidden">
        <div className="h-1.5 bg-cyber-blue-accent" />
        <div className="px-5 sm:px-8 py-6 sm:py-7 border-b border-cyber-gray-border flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <p className="text-[11px] font-bold text-cyber-blue-accent uppercase tracking-[0.18em]">Лабораторные работы</p>
            <h1 className="text-2xl sm:text-[28px] font-black tracking-[-0.025em] text-cyber-blue-dark mt-1 flex items-center">
              <Server className="w-5 h-5 mr-2.5 text-cyber-blue-accent" />
              Запуск лабораторной работы №3
            </h1>
          </div>
          <span className="self-start sm:self-auto inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#E7F2FB] border border-cyber-gray-border text-cyber-blue text-[11px] font-semibold uppercase tracking-wider">
            Интерактивная топология
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-5 divide-y lg:divide-y-0 lg:divide-x divide-cyber-gray-border">
          <div className="lg:col-span-3 p-5 sm:p-8 space-y-5 min-w-0">
            <div className="w-full px-4 py-3 bg-[#E7F2FB] border border-cyber-gray-border rounded-brand text-sm text-cyber-blue-dark">
              <span className="font-bold">{auth?.display_name}</span> <span className="font-mono text-cyber-gray-light text-xs">({auth?.username})</span>
              {isTeacher && <span className="block sm:inline sm:ml-2 mt-1 sm:mt-0 text-xs text-cyber-blue-accent">Стенд будет закреплён за вами</span>}
            </div>

            <div className="grid grid-cols-3 gap-3">
              <Summary icon={<Cpu className="w-4 h-4" />} label="Виртуальные машины" value={`${enabledVMs.length} ВМ`} />
              <Summary icon={<Network className="w-4 h-4" />} label="Подсеть" value={teacherDeployment.network.cidr} />
              <Summary icon={<Clock className="w-4 h-4" />} label="TTL" value="2 часа" />
            </div>

            <button type="button" onClick={() => setShowSettings((value) => !value)} className="w-full flex items-center justify-between px-4 py-3.5 bg-white hover:bg-cyber-gray-surface border border-cyber-gray-border rounded-brand text-sm font-bold text-cyber-blue-dark transition-colors" aria-expanded={showSettings}>
              <span className="flex items-center"><Settings2 className="w-4 h-4 mr-2 text-cyber-blue-accent" />Параметры развёртывания</span>
              {showSettings ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {showSettings && (
              <div className="space-y-6 border border-cyber-gray-border rounded-brand p-4 sm:p-5 bg-cyber-gray-surface/45 min-w-0">
                {teacherOptions.catalog_error && <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-3">{teacherOptions.catalog_error}</p>}
                <div>
                  <h2 className="text-xs font-bold uppercase tracking-[0.14em] text-cyber-blue-dark mb-3">Сеть стенда</h2>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    <Field label="CIDR" value={teacherDeployment.network.cidr} onChange={(value) => updateNetwork('cidr', value)} />
                    <Field label="Шлюз" value={teacherDeployment.network.gateway} onChange={(value) => updateNetwork('gateway', value)} />
                    <Field label="Внешняя сеть" value={teacherDeployment.network.external_network} list="external-networks" onChange={(value) => updateNetwork('external_network', value)} />
                    <Field label="DHCP: начало" value={teacherDeployment.network.dhcp_start} onChange={(value) => updateNetwork('dhcp_start', value)} />
                    <Field label="DHCP: конец" value={teacherDeployment.network.dhcp_end} onChange={(value) => updateNetwork('dhcp_end', value)} />
                    <Field label="DNS (через запятую)" value={teacherDeployment.network.dns_nameservers.join(', ')} onChange={(value) => updateNetwork('dns_nameservers', value)} />
                  </div>
                </div>

                <div>
                  <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-1 mb-3">
                    <h2 className="text-xs font-bold uppercase tracking-[0.14em] text-cyber-blue-dark">Виртуальные машины</h2>
                    <p className="text-[11px] text-cyber-gray-light">Включено {enabledVMs.length} из {teacherDeployment.vms.length}</p>
                  </div>
                  <div className="space-y-3">
                    {teacherDeployment.vms.map((vm, index) => (
                      <div key={vm.role} className={`min-w-0 p-4 bg-white rounded-brand border transition-colors ${vm.enabled ? 'border-cyber-gray-border' : 'border-cyber-gray-border/70 opacity-65'}`}>
                        <div className="flex items-center justify-between gap-3 mb-3 pb-3 border-b border-cyber-gray-border/70">
                          <div className="flex items-center gap-2 min-w-0">
                            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${vm.enabled ? 'bg-cyber-blue-accent' : 'bg-cyber-gray-light'}`} />
                            <span className="font-mono font-bold text-sm text-cyber-blue-dark truncate">{vm.role}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => updateVM(index, 'enabled', !vm.enabled)}
                            className={`inline-flex items-center gap-1.5 text-[11px] font-bold ${vm.enabled ? 'text-cyber-blue-accent' : 'text-cyber-gray-light'}`}
                            aria-pressed={vm.enabled}
                            aria-label={`${vm.enabled ? 'Отключить' : 'Включить'} виртуальную машину ${vm.role}`}
                          >
                            {vm.enabled ? <ToggleRight className="w-6 h-6" /> : <ToggleLeft className="w-6 h-6" />}
                            {vm.enabled ? 'Включена' : 'Отключена'}
                          </button>
                        </div>
                        <div className="vm-field-grid">
                          <Field label="Образ" value={vm.image} list="image-options" disabled={!vm.enabled} onChange={(value) => updateVM(index, 'image', value)} />
                          <SelectField label="Конфигурация" value={vm.flavor} options={teacherOptions.flavors} disabled={!vm.enabled} onChange={(value) => updateVM(index, 'flavor', value)} />
                          <Field label="IP-адрес" value={vm.ip} disabled={!vm.enabled} onChange={(value) => updateVM(index, 'ip', value)} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <datalist id="image-options">{teacherOptions.images.map((value) => <option key={value} value={value} />)}</datalist>
            <datalist id="external-networks">{teacherOptions.external_networks.map((value) => <option key={value} value={value} />)}</datalist>

            <DeployButton onClick={handleDeploy} isLoading={isDeploying} className="w-full">
              <ArrowRight className="w-4 h-4 mr-2" /> Проверить параметры и запустить
            </DeployButton>
          </div>

          <div className="lg:col-span-2 p-5 sm:p-8 bg-cyber-blue-dark text-white relative overflow-hidden">
            <div className="absolute inset-0 brand-grid opacity-20" />
            <div className="relative">
            <p className="text-[11px] font-bold text-cyber-blue-light uppercase tracking-[0.16em] mb-2">Процесс развёртывания</p>
            <h2 className="text-xl font-bold mb-6">Что произойдёт после запуска</h2>
            <ol className="space-y-4">
              {steps.map((step, index) => (
                <li key={step} className="flex items-start text-sm text-white/80 leading-5">
                  <span className="flex-shrink-0 w-6 h-6 rounded-full bg-cyber-blue-accent text-white text-[11px] font-bold flex items-center justify-center mr-3">{index + 1}</span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
            </div>
          </div>
        </div>
      </section>

      {standId && (
        <div className="flex items-center gap-3 bg-emerald-50 border border-emerald-200 rounded-brand p-4 text-emerald-800 text-sm">
          <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
          Стенд <code className="font-mono bg-white border border-emerald-200 px-1.5 py-0.5 rounded">{standId}</code> принят в работу. Перенаправление…
        </div>
      )}
    </div>
  );
};


const Summary = ({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) => (
  <div className="p-3 rounded-brand border border-cyber-gray-border bg-white min-w-0">
    <div className="text-cyber-blue-accent mb-1.5">{icon}</div>
    <p className="text-[10px] font-bold text-cyber-gray-light uppercase tracking-wider">{label}</p>
    <p className="text-sm font-bold text-cyber-blue-dark mt-0.5 truncate">{value}</p>
  </div>
);


const Field = ({ label, value, onChange, list, disabled = false }: { label: string; value: string; onChange: (value: string) => void; list?: string; disabled?: boolean }) => (
  <label className="block min-w-0">
    <span className="block text-[10px] font-bold text-cyber-gray-light uppercase tracking-wider mb-1.5">{label}</span>
    <input value={value} list={list} disabled={disabled} onChange={(event) => onChange(event.target.value)} className="w-full min-w-0 px-3 py-2.5 bg-white border border-cyber-gray-border rounded-brand text-xs font-mono text-cyber-gray-dark focus:outline-none focus:ring-2 focus:ring-cyber-blue-accent/15 focus:border-cyber-blue-accent disabled:bg-cyber-gray-surface disabled:cursor-not-allowed" />
  </label>
);

const SelectField = ({ label, value, options, onChange, disabled = false }: { label: string; value: string; options: string[]; onChange: (value: string) => void; disabled?: boolean }) => (
  <label className="block min-w-0">
    <span className="block text-[10px] font-bold text-cyber-gray-light uppercase tracking-wider mb-1.5">{label}</span>
    <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} className="w-full min-w-0 px-3 py-2.5 bg-white border border-cyber-gray-border rounded-brand text-xs font-mono text-cyber-gray-dark focus:outline-none focus:ring-2 focus:ring-cyber-blue-accent/15 focus:border-cyber-blue-accent disabled:bg-cyber-gray-surface disabled:cursor-not-allowed">
      {options.length === 0 && <option value={value}>{value || 'Нет доступных конфигураций'}</option>}
      {value && !options.includes(value) && <option value={value} disabled>{value} (недоступна)</option>}
      {options.map((option) => <option key={option} value={option}>{option}</option>)}
    </select>
  </label>
);
