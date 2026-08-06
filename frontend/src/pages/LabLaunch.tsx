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
} from 'lucide-react';

import { mockApi, getAuth } from '../api/mocks';
import { DeployButton } from '../components/DeployButton';
import type { DeploymentConfig, DeploymentOptions, VMDeploymentSpec } from '../types/api';


export const LabLaunch = () => {
  const labId = 3;
  const auth = getAuth();
  const isTeacher = auth?.role === 'teacher' || auth?.role === 'admin';
  const [userId, setUserId] = useState(auth?.username || 'student');
  const [isDeploying, setIsDeploying] = useState(false);
  const [standId, setStandId] = useState<string | null>(null);
  const [options, setOptions] = useState<DeploymentOptions | null>(null);
  const [deployment, setDeployment] = useState<DeploymentConfig | null>(null);
  const [showSettings, setShowSettings] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    mockApi.getDeploymentOptions()
      .then((data) => {
        setOptions(data);
        setDeployment(data.default);
      })
      .catch((error: unknown) => {
        toast.error(error instanceof Error ? error.message : 'Не удалось загрузить параметры OpenStack');
      });
  }, []);

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
    if (!deployment) return;
    setIsDeploying(true);
    try {
      const res = await mockApi.deploy({
        user_id: userId,
        lab_id: labId,
        role: isTeacher ? 'teacher' : 'student',
        deployment,
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
    'Проверка выбранных образов, flavor и IP-адресов',
    'Проверка квоты с учётом выбранных vCPU',
    'Выделение проекта из пула',
    'Создание изолированной сети и пяти ВМ',
    'Настройка SSH, Security Group и Floating IP',
  ];

  if (!deployment || !options) {
    return <div className="max-w-5xl mx-auto p-10 text-center text-cyber-gray-light">Загрузка каталога OpenStack…</div>;
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <section className="bg-white rounded-brand border border-cyber-gray-border overflow-hidden">
        <div className="h-1 bg-cyber-blue-accent" />
        <div className="px-8 py-7 border-b border-cyber-gray-border flex items-center justify-between">
          <div>
            <p className="text-[11px] font-bold text-cyber-gray-light uppercase tracking-[0.18em]">Лабораторные работы</p>
            <h1 className="text-[22px] font-bold text-cyber-gray-dark mt-1 flex items-center">
              <Server className="w-5 h-5 mr-2.5 text-cyber-blue-accent" />
              Запуск лабораторной работы №3
            </h1>
          </div>
          <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-cyber-blue/5 border border-cyber-blue/15 text-cyber-blue text-[11px] font-semibold uppercase tracking-wider">
            Интерактивная топология
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-5 divide-y lg:divide-y-0 lg:divide-x divide-cyber-gray-border">
          <div className="lg:col-span-3 p-8 space-y-5">
            {isTeacher ? (
              <div>
                <label className="block text-[11px] font-bold text-cyber-gray-light uppercase tracking-[0.14em] mb-2">Идентификатор студента</label>
                <input value={userId} onChange={(event) => setUserId(event.target.value)} className="w-full px-4 py-2.5 border border-cyber-gray-border rounded-brand text-sm" />
              </div>
            ) : (
              <div className="w-full px-4 py-2.5 bg-cyber-gray-surface border border-cyber-gray-border rounded-brand text-sm">
                {auth?.display_name} <span className="font-mono text-cyber-gray-light text-xs">({auth?.username})</span>
              </div>
            )}

            <div className="grid grid-cols-3 gap-3">
              <Summary icon={<Cpu className="w-4 h-4" />} label="Виртуальные машины" value={`${enabledVMs.length} ВМ`} />
              <Summary icon={<Network className="w-4 h-4" />} label="Подсеть" value={deployment.network.cidr} />
              <Summary icon={<Clock className="w-4 h-4" />} label="TTL" value="2 часа" />
            </div>

            <button type="button" onClick={() => setShowSettings((value) => !value)} className="w-full flex items-center justify-between px-4 py-3 bg-cyber-gray-surface border border-cyber-gray-border rounded-brand text-sm font-semibold text-cyber-gray-dark">
              <span className="flex items-center"><Settings2 className="w-4 h-4 mr-2 text-cyber-blue-accent" />Параметры развёртывания</span>
              {showSettings ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {showSettings && (
              <div className="space-y-5 border border-cyber-gray-border rounded-brand p-5">
                {options.catalog_error && <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-3">{options.catalog_error}</p>}
                <div>
                  <h2 className="text-xs font-bold uppercase tracking-wider text-cyber-gray-light mb-3">Сеть стенда</h2>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    <Field label="CIDR" value={deployment.network.cidr} onChange={(value) => updateNetwork('cidr', value)} />
                    <Field label="Шлюз" value={deployment.network.gateway} onChange={(value) => updateNetwork('gateway', value)} />
                    <Field label="Внешняя сеть" value={deployment.network.external_network} list="external-networks" onChange={(value) => updateNetwork('external_network', value)} />
                    <Field label="DHCP: начало" value={deployment.network.dhcp_start} onChange={(value) => updateNetwork('dhcp_start', value)} />
                    <Field label="DHCP: конец" value={deployment.network.dhcp_end} onChange={(value) => updateNetwork('dhcp_end', value)} />
                    <Field label="DNS (через запятую)" value={deployment.network.dns_nameservers.join(', ')} onChange={(value) => updateNetwork('dns_nameservers', value)} />
                  </div>
                </div>

                <div>
                  <h2 className="text-xs font-bold uppercase tracking-wider text-cyber-gray-light mb-3">Виртуальные машины</h2>
                  <div className="space-y-3">
                    {deployment.vms.map((vm, index) => (
                      <div key={vm.role} className="grid grid-cols-1 md:grid-cols-[110px_1fr_150px_130px] gap-2 items-end p-3 bg-cyber-gray-surface rounded-brand border border-gray-200">
                        <div className="font-mono font-bold text-sm text-cyber-blue pb-2.5">{vm.role}</div>
                        <Field label="Образ" value={vm.image} list="image-options" onChange={(value) => updateVM(index, 'image', value)} />
                        <Field label="Flavor" value={vm.flavor} list="flavor-options" onChange={(value) => updateVM(index, 'flavor', value)} />
                        <Field label="IP-адрес" value={vm.ip} onChange={(value) => updateVM(index, 'ip', value)} />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <datalist id="image-options">{options.images.map((value) => <option key={value} value={value} />)}</datalist>
            <datalist id="flavor-options">{options.flavors.map((value) => <option key={value} value={value} />)}</datalist>
            <datalist id="external-networks">{options.external_networks.map((value) => <option key={value} value={value} />)}</datalist>

            <DeployButton onClick={handleDeploy} isLoading={isDeploying} className="w-full">
              <ArrowRight className="w-4 h-4 mr-2" /> Проверить параметры и запустить
            </DeployButton>
          </div>

          <div className="lg:col-span-2 p-8 bg-cyber-gray-surface">
            <p className="text-[11px] font-bold text-cyber-gray-light uppercase tracking-[0.14em] mb-4">Процесс развёртывания</p>
            <ol className="space-y-3">
              {steps.map((step, index) => (
                <li key={step} className="flex items-start text-sm text-cyber-gray-dark">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-white border border-cyber-blue-accent/30 text-cyber-blue-accent text-[11px] font-bold flex items-center justify-center mr-3 mt-0.5">{index + 1}</span>
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
          Стенд <code className="font-mono bg-white border border-emerald-200 px-1.5 py-0.5 rounded">{standId}</code> принят в работу. Перенаправление…
        </div>
      )}
    </div>
  );
};


const Summary = ({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) => (
  <div className="p-3 rounded-brand border border-cyber-gray-border bg-cyber-gray-surface">
    <div className="text-cyber-blue-accent mb-1.5">{icon}</div>
    <p className="text-[10px] font-bold text-cyber-gray-light uppercase tracking-wider">{label}</p>
    <p className="text-sm font-bold text-cyber-gray-dark mt-0.5 truncate">{value}</p>
  </div>
);


const Field = ({ label, value, onChange, list }: { label: string; value: string; onChange: (value: string) => void; list?: string }) => (
  <label className="block min-w-0">
    <span className="block text-[10px] font-bold text-cyber-gray-light uppercase tracking-wider mb-1">{label}</span>
    <input value={value} list={list} onChange={(event) => onChange(event.target.value)} className="w-full px-3 py-2 bg-white border border-cyber-gray-border rounded text-xs font-mono focus:outline-none focus:border-cyber-blue-accent" />
  </label>
);
