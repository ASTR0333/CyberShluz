import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { mockApi } from '../api/mocks';
import type { StandStatusResponse, CheckResultResponse } from '../types/api';
import { ProgressBadge } from '../components/ProgressBadge';
import { StandTerminal } from '../components/StandTerminal';
import {
  ShieldCheck, Loader2, Globe, Clock, Terminal as TerminalIcon,
  Info, Snowflake, Trash2, Server, Monitor, Copy, Rocket, Key, CheckCircle2
} from 'lucide-react';
import toast from 'react-hot-toast';



async function copyToClipboard(text: string) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    toast.success('Скопировано');
  } catch {
    toast.error('Не удалось скопировать');
  }
}

function useCountdown(targetIso: string | null) {
  const [remaining, setRemaining] = useState('');

  useEffect(() => {
    if (!targetIso) { setRemaining(''); return; }

    const tick = () => {
      const diff = new Date(targetIso).getTime() - Date.now();
      if (diff <= 0) { setRemaining('00:00:00'); return; }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setRemaining(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`);
    };

    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [targetIso]);

  return remaining;
}


function NoStandScreen() {
  const navigate = useNavigate();
  return (
    <div className="max-w-lg mx-auto mt-16 text-center">
      <div className="bg-white rounded-brand shadow-sm border border-gray-200 p-12">
        <div className="w-16 h-16 bg-cyber-gray-surface rounded-full flex items-center justify-center mx-auto mb-6 border border-gray-200">
          <Server className="w-8 h-8 text-cyber-gray-light" />
        </div>
        <h2 className="text-xl font-bold text-cyber-gray-dark mb-2">Активный стенд не найден</h2>
        <p className="text-cyber-gray-light text-sm mb-8">
          У вас нет запущенных лабораторных стендов.<br />
          Запустите стенд, чтобы начать работу.
        </p>
        <button
          onClick={() => navigate('/launch')}
          className="inline-flex items-center px-6 py-3 bg-cyber-blue-accent text-white rounded-brand font-semibold hover:bg-cyber-blue transition-colors shadow-sm"
        >
          <Rocket className="w-5 h-5 mr-2" />
          Запустить стенд
        </button>
      </div>
    </div>
  );
}

export const StandStatus = () => {
  const { stand_id: paramId } = useParams<{ stand_id: string }>();
  const navigate = useNavigate();


  const [resolvedId, setResolvedId] = useState<string | null>(null);
  const [noStand, setNoStand] = useState(false);

  useEffect(() => {


    setNoStand(false);
    setResolvedId(!paramId || paramId === 'my' ? 'my' : paramId);
  }, [paramId]);

  const [status, setStatus] = useState<StandStatusResponse | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [checkResult, setCheckResult] = useState<CheckResultResponse | null>(null);
  const [isFreezing, setIsFreezing] = useState(false);
  const [isCleaning, setIsCleaning] = useState(false);
  const [pubkeyInput, setPubkeyInput] = useState('');
  const [isSubmittingKey, setIsSubmittingKey] = useState(false);
  const [keySubmitted, setKeySubmitted] = useState(false);
  const [terminalOpen, setTerminalOpen] = useState(false);

  const isFrozenStatus = status?.status === 'FREEZE';
  const countdownTarget = isFrozenStatus ? (status?.frozen_until ?? null) : (status?.expires_at ?? null);
  const countdown = useCountdown(countdownTarget);


  const standId = status?.stand_id ?? (resolvedId && resolvedId !== 'my' ? resolvedId : null);

  const poll = useCallback(async () => {
    if (!resolvedId) return;
    try {
      const data = await mockApi.getStatus(resolvedId);
      setStatus(data);
      setNoStand(false);

      if (data.status === 'FREE') {
        localStorage.removeItem('my_stand_id');
      } else if (data.stand_id) {
        localStorage.setItem('my_stand_id', data.stand_id);
      }
    } catch (err) {

      if (resolvedId === 'my' && err instanceof Error && /найд/i.test(err.message)) {
        setStatus(null);
        setNoStand(true);
      }

    }
  }, [resolvedId]);

  useEffect(() => {
    if (!resolvedId) return;
    poll();
    const interval = setInterval(poll, 3000);
    return () => clearInterval(interval);
  }, [poll, resolvedId]);

  const handleRunCheck = async () => {
    if (!standId) return;
    setIsChecking(true);
    setCheckResult(null);
    try {
      await mockApi.check(standId);
      await new Promise(r => setTimeout(r, 4000));
      const result = await mockApi.getCheckResult(standId);
      setCheckResult(result);
      if (result.status === 'PASSED') toast.success('Все проверки пройдены!');
      else toast.error('Обнаружены проблемы — изучите лог');
    } catch {
      toast.error('Ошибка проверки');
    } finally {
      setIsChecking(false);
    }
  };

  const handleFreeze = async () => {
    if (!standId) return;
    setIsFreezing(true);
    try {
      await mockApi.freeze(standId, 'Студент запросил помощь');
      toast.success('Стенд заморожен на 24ч. Преподаватель уведомлён.');
      poll();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Ошибка');
    } finally {
      setIsFreezing(false);
    }
  };

  const handleCleanup = async () => {
    if (!standId) return;
    setIsCleaning(true);
    try {
      await mockApi.cleanup(standId);
      toast.success('Стенд отправлен на очистку');
      localStorage.removeItem('my_stand_id');
      setTimeout(() => navigate('/launch'), 2000);
    } catch {
      toast.error('Ошибка завершения');
    } finally {
      setIsCleaning(false);
    }
  };

  const handleSubmitPubkey = async () => {
    if (!standId) return;
    const key = pubkeyInput.trim();
    if (!key) { toast.error('Вставьте публичный ключ'); return; }
    setIsSubmittingKey(true);
    try {
      const res = await mockApi.submitPubkey(standId, { public_key: key });
      toast.success(res.message);
      setKeySubmitted(true);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Ошибка отправки ключа');
    } finally {
      setIsSubmittingKey(false);
    }
  };



  if (noStand) return <NoStandScreen />;

  if (!resolvedId || !status) return (
    <div className="flex justify-center items-center h-64">
      <Loader2 className="w-8 h-8 animate-spin text-cyber-blue" />
    </div>
  );


  if (status.status === 'FREE') {
    return (
      <div className="max-w-lg mx-auto mt-16 text-center">
        <div className="bg-white rounded-brand shadow-sm border border-gray-200 p-12">
          <div className="w-16 h-16 bg-green-50 rounded-full flex items-center justify-center mx-auto mb-6 border border-green-200">
            <ShieldCheck className="w-8 h-8 text-green-500" />
          </div>
          <h2 className="text-xl font-bold text-cyber-gray-dark mb-2">Стенд освобождён</h2>
          <p className="text-cyber-gray-light text-sm mb-8">Лабораторная работа завершена. Все ресурсы очищены.</p>
          <button
            onClick={() => navigate('/launch')}
            className="inline-flex items-center px-6 py-3 bg-cyber-blue-accent text-white rounded-brand font-semibold hover:bg-cyber-blue transition-colors"
          >
            <Rocket className="w-5 h-5 mr-2" />
            Запустить новый стенд
          </button>
        </div>
      </div>
    );
  }

  const isActive = ['READY', 'DEPLOYING', 'PENDING'].includes(status.status);
  const isFrozen = status.status === 'FREEZE';
  const sshUser = 'student';
  const sshCmd = status.ip_address ? `ssh ${sshUser}@${status.ip_address}` : null;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">


        <div className="lg:col-span-2 bg-white rounded-brand shadow-sm border border-gray-200 p-8 relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-1 bg-cyber-blue"></div>

          <div className="flex justify-between items-start mb-8">
            <div>
              <h1 className="text-xs font-bold text-cyber-gray-light uppercase tracking-widest mb-1">Стенд</h1>
              <code className="text-cyber-gray-dark font-mono text-lg bg-gray-50 px-2 py-1 rounded border border-gray-200">
                #{standId}
              </code>
            </div>
            <ProgressBadge status={status.status} />
          </div>

          <div className="grid grid-cols-2 gap-6">
            <div className="flex items-center p-5 bg-cyber-gray-surface rounded-brand border border-gray-200">
              <div className="w-12 h-12 bg-white rounded-full flex items-center justify-center shadow-sm border border-gray-100 mr-4">
                <Globe className="w-6 h-6 text-cyber-blue" />
              </div>
              <div>
                <p className="text-xs text-cyber-gray-light font-bold uppercase tracking-wider mb-1">Публичный IP</p>
                <p className="text-lg font-mono font-bold text-cyber-gray-dark">
                  {status.ip_address || 'Ожидание...'}
                </p>
              </div>
            </div>
            <div className="flex items-center p-5 bg-cyber-gray-surface rounded-brand border border-gray-200">
              <div className="w-12 h-12 bg-white rounded-full flex items-center justify-center shadow-sm border border-gray-100 mr-4">
                <Clock className="w-6 h-6 text-cyber-blue" />
              </div>
              <div>
                <p className="text-xs text-cyber-gray-light font-bold uppercase tracking-wider mb-1">
                  {isFrozen ? 'Заморожен до' : 'Осталось'}
                </p>
                <p className={`text-lg font-mono font-bold ${countdown === '00:00:00' ? 'text-red-600' : 'text-cyber-gray-dark'}`}>
                  {countdown || '—'}
                </p>
              </div>
            </div>
          </div>


          {status.message && status.status === 'DEPLOYING' && (
            <div className="mt-4 text-sm text-yellow-700 bg-yellow-50 p-3 rounded-brand border border-yellow-200 flex items-center">
              <Loader2 className="w-4 h-4 mr-2 animate-spin flex-shrink-0" />
              {status.message}
            </div>
          )}
          {status.status === 'PENDING' && (
            <div className="mt-4 text-sm text-gray-600 bg-gray-50 p-3 rounded-brand border border-gray-200 flex items-center">
              <Info className="w-4 h-4 mr-2 flex-shrink-0" />
              Стенд в очереди на развертывание. Пожалуйста, подождите...
            </div>
          )}


          <div className="mt-8 pt-6 border-t border-gray-200 flex flex-wrap gap-3">
            <button
              onClick={handleRunCheck}
              disabled={status.status !== 'READY' || isChecking}
              className="flex items-center px-5 py-2.5 bg-cyber-gray-dark text-white rounded-brand font-semibold hover:bg-black disabled:bg-gray-200 disabled:text-gray-400 transition-colors shadow-sm"
            >
              {isChecking
                ? <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                : <ShieldCheck className="w-5 h-5 mr-2 text-cyber-blue-light" />}
              Завершить и проверить
            </button>

            <button
              onClick={() => setTerminalOpen(true)}
              disabled={status.status !== 'READY' || !status.ip_address}
              className="flex items-center px-5 py-2.5 bg-cyber-blue text-white rounded-brand font-semibold hover:bg-cyber-blue-accent disabled:bg-gray-200 disabled:text-gray-400 transition-colors shadow-sm"
            >
              <TerminalIcon className="w-5 h-5 mr-2" />
              Веб-терминал
            </button>

            <button
              onClick={handleFreeze}
              disabled={!isActive || isFreezing}
              className="flex items-center px-5 py-2.5 bg-cyber-blue-accent text-white rounded-brand font-semibold hover:bg-cyber-blue disabled:bg-gray-200 disabled:text-gray-400 transition-colors shadow-sm"
            >
              {isFreezing
                ? <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                : <Snowflake className="w-5 h-5 mr-2" />}
              Нужна помощь (24ч)
            </button>

            <button
              onClick={handleCleanup}
              disabled={(!isActive && !isFrozen) || isCleaning}
              className="flex items-center px-5 py-2.5 bg-red-600 text-white rounded-brand font-semibold hover:bg-red-700 disabled:bg-gray-200 disabled:text-gray-400 transition-colors shadow-sm"
            >
              {isCleaning
                ? <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                : <Trash2 className="w-5 h-5 mr-2" />}
              Завершить работу
            </button>
          </div>
        </div>


        <div className="bg-cyber-gray-dark rounded-brand p-6 text-white shadow-md border-t-4 border-cyber-blue-accent">
          <h3 className="text-lg font-bold mb-5 flex items-center">
            <ShieldCheck className="mr-2 text-cyber-blue-light" /> Параметры доступа
          </h3>
          <div className="space-y-5 text-sm">


            <div className="space-y-4">


              <div>
                <p className="font-bold mb-1.5 text-gray-300 text-xs uppercase tracking-wider flex items-center gap-1.5">
                  <span className="bg-cyber-blue text-white rounded-full w-4 h-4 inline-flex items-center justify-center text-[10px] font-bold flex-shrink-0">1</span>
                  Генерируй ключ (один раз)
                </p>
                <div className="bg-black p-2.5 rounded border border-gray-700 flex justify-between items-center group">
                  <code className="text-cyber-blue-light text-[11px] break-all pr-2">ssh-keygen -t ed25519 -C "vm-key"</code>
                  <button
                    onClick={() => copyToClipboard('ssh-keygen -t ed25519 -C "vm-key"')}
                    className="text-gray-400 hover:text-white flex-shrink-0 transition-colors"
                  ><Copy size={12} /></button>
                </div>
                <p className="text-gray-500 text-[10px] mt-1">На все вопросы жми Enter — оставляй пустой passphrase.</p>
              </div>


              <div>
                <p className="font-bold mb-1.5 text-gray-300 text-xs uppercase tracking-wider flex items-center gap-1.5">
                  <span className="bg-cyber-blue text-white rounded-full w-4 h-4 inline-flex items-center justify-center text-[10px] font-bold flex-shrink-0">2</span>
                  Скопируй публичный ключ
                </p>
                <div className="bg-black p-2.5 rounded border border-gray-700 flex justify-between items-center group">
                  <code className="text-cyber-blue-light text-[11px] pr-2">cat ~/.ssh/id_ed25519.pub</code>
                  <button
                    onClick={() => copyToClipboard('cat ~/.ssh/id_ed25519.pub')}
                    className="text-gray-400 hover:text-white flex-shrink-0 transition-colors"
                  ><Copy size={12} /></button>
                </div>
                <p className="text-gray-500 text-[10px] mt-1">Запусти в терминале и скопируй строку, начинающуюся с <span className="font-mono">ssh-ed25519 AAAA...</span></p>
              </div>


              <div>
                <p className="font-bold mb-1.5 text-gray-300 text-xs uppercase tracking-wider flex items-center gap-1.5">
                  <span className="bg-cyber-blue text-white rounded-full w-4 h-4 inline-flex items-center justify-center text-[10px] font-bold flex-shrink-0">3</span>
                  Вставь ключ и отправь
                </p>
                {keySubmitted ? (
                  <div className="flex items-center gap-2 text-green-400 text-xs bg-green-900/20 border border-green-800 rounded p-2.5">
                    <CheckCircle2 size={14} className="flex-shrink-0" />
                    Ключ добавлен — можешь подключаться!
                  </div>
                ) : (
                  <div className="space-y-2">
                    <textarea
                      value={pubkeyInput}
                      onChange={e => setPubkeyInput(e.target.value)}
                      placeholder="ssh-ed25519 AAAA..."
                      rows={3}
                      className="w-full bg-black border border-gray-700 rounded p-2 text-[11px] text-gray-300 font-mono resize-none focus:outline-none focus:border-cyber-blue placeholder-gray-600"
                    />
                    <button
                      onClick={handleSubmitPubkey}
                      disabled={isSubmittingKey || status.status !== 'READY'}
                      className="w-full inline-flex items-center justify-center px-4 py-2 bg-cyber-blue-accent text-white rounded-brand text-sm font-semibold hover:bg-cyber-blue disabled:bg-gray-700 disabled:text-gray-500 transition-colors"
                    >
                      {isSubmittingKey
                        ? <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        : <Key className="w-4 h-4 mr-2" />}
                      Добавить ключ на стенд
                    </button>
                  </div>
                )}
              </div>


              <div>
                <p className="font-bold mb-1.5 text-gray-300 text-xs uppercase tracking-wider flex items-center gap-1.5">
                  <span className={`${keySubmitted ? 'bg-green-600' : 'bg-gray-600'} text-white rounded-full w-4 h-4 inline-flex items-center justify-center text-[10px] font-bold flex-shrink-0`}>4</span>
                  Подключайся
                </p>
                {sshCmd ? (
                  <div className="bg-black p-2.5 rounded border border-gray-700 flex justify-between items-center group">
                    <code className="text-cyber-blue-light text-[11px] break-all pr-2">{sshCmd}</code>
                    <button
                      onClick={() => copyToClipboard(sshCmd)}
                      className="text-gray-400 hover:text-white flex-shrink-0 transition-colors"
                    ><Copy size={12} /></button>
                  </div>
                ) : (
                  <div className="bg-black/50 p-2.5 rounded border border-gray-800 text-[11px] text-gray-500 italic">
                    Команда появится, когда стенд получит IP
                  </div>
                )}
              </div>

            </div>

            <div className="pt-4 border-t border-gray-700 text-gray-400 text-xs leading-relaxed space-y-1">
              <p>Через L-MS доступны все ВМ стенда по внутренней сети 10.0.0.0/24</p>
              <p className="font-mono text-gray-500 text-[11px]">
                L-NFS: 10.0.0.70 &nbsp;|&nbsp; L-PGSQL: 10.0.0.55<br />
                W-DC: 10.0.0.5 &nbsp;|&nbsp; V-HV: 10.0.0.65
              </p>
            </div>
          </div>
        </div>
      </div>


      {status.vms && Object.keys(status.vms).length > 0 && (
        <div className="bg-white rounded-brand shadow-sm border border-gray-200 p-6">
          <h3 className="text-sm font-bold text-cyber-gray-dark mb-4 flex items-center uppercase tracking-wider">
            <Server className="w-4 h-4 mr-2 text-cyber-blue" />
            Топология стенда ({Object.keys(status.vms).length} ВМ)
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {Object.entries(status.vms).map(([role, vm]: [string, any]) => {
              const isVmActive = vm.status === 'ACTIVE';
              const isVmBuilding = vm.status === 'BUILD' || vm.status === 'BUILD-ERROR';
              return (
                <div
                  key={role}
                  className={`p-3 rounded-brand border text-center ${
                    isVmActive ? 'bg-green-50 border-green-200'
                    : isVmBuilding ? 'bg-yellow-50 border-yellow-200'
                    : 'bg-red-50 border-red-200'
                  }`}
                >
                  <Monitor className={`w-5 h-5 mx-auto mb-1 ${
                    isVmActive ? 'text-green-600' : isVmBuilding ? 'text-yellow-600' : 'text-red-500'
                  }`} />
                  <p className="font-mono font-bold text-xs text-cyber-gray-dark">{role}</p>
                  <p className="font-mono text-[11px] text-gray-500 mt-0.5">{vm.ip || vm.expected_ip}</p>
                  <p className={`text-xs font-bold mt-1 ${
                    isVmActive ? 'text-green-600' : isVmBuilding ? 'text-yellow-600' : 'text-red-500'
                  }`}>
                    {isVmActive ? 'Активна' : isVmBuilding ? 'Создаётся...' : 'Ошибка'}
                  </p>
                </div>
              );
            })}
          </div>
          {status.vms && Object.values(status.vms).some((v: any) => v.status !== 'ACTIVE') && (
            <p className="text-xs text-gray-400 mt-3">
              * ВМ с ошибкой (W-DC, V-HYPERV) — нехватка дисковой квоты. Linux-машины (L-MS, L-NFS, L-PGSQL) готовы к работе.
            </p>
          )}
        </div>
      )}


      {(isChecking || checkResult) && (
        <div className="bg-[#1E1E1E] rounded-brand overflow-hidden shadow-lg border border-gray-700">
          <div className="bg-[#2D2D2D] px-4 py-2 border-b border-gray-900 flex items-center justify-between">
            <div className="flex items-center">
              <TerminalIcon className="w-4 h-4 text-gray-400 mr-2" />
              <span className="text-xs font-mono text-gray-300 uppercase tracking-widest">Результат проверки (Ansible)</span>
            </div>
            <div className="flex space-x-2">
              <div className="w-3 h-3 rounded-full bg-red-500"></div>
              <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
              <div className="w-3 h-3 rounded-full bg-green-500"></div>
            </div>
          </div>
          <div className="p-6 font-mono text-sm min-h-[160px] text-gray-300 bg-black">
            {isChecking && (
              <div className="text-cyber-blue-light animate-pulse space-y-1">
                <p>$ ansible-playbook lab03_cyber.yml -i {status?.ip_address},</p>
                <p className="text-gray-500"># Подключение к L-MS ({status?.ip_address})...</p>
                <p className="text-gray-500"># Проверка порта 9877 (Snapdrive)...</p>
                <p className="text-gray-500"># Проверка модуля snapapi (L-NFS)...</p>
                <p className="text-gray-500"># Проверка служб Acronis...</p>
              </div>
            )}
            {checkResult && (
              <div className={checkResult.status === 'PASSED' ? 'text-green-400' : 'text-red-400'}>
                {checkResult.log.split('\n').map((line, i) => (
                  <div key={i} className="mb-1 leading-relaxed">{line}</div>
                ))}
                <div className="mt-6 pt-3 border-t border-gray-800 flex items-center">
                  <span className="text-white font-bold mr-2">ИТОГ:</span>
                  <span className={checkResult.status === 'PASSED'
                    ? 'bg-green-900/50 text-green-400 px-3 py-0.5 rounded font-bold'
                    : 'bg-red-900/50 text-red-400 px-3 py-0.5 rounded font-bold'}>
                    {checkResult.status === 'PASSED' ? '✓ ВЫПОЛНЕНО' : '✗ НЕ ВЫПОЛНЕНО'}
                  </span>
                </div>
                {checkResult.details && Object.keys(checkResult.details).length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-3 text-xs text-gray-400">
                    {Object.entries(checkResult.details).map(([k, v]) => (
                      <span key={k}>{v ? '✅' : '❌'} {k}</span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {terminalOpen && standId && (
        <StandTerminal standId={standId} onClose={() => setTerminalOpen(false)} />
      )}
    </div>
  );
};
