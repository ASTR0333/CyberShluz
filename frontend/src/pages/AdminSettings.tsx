import { useCallback, useEffect, useRef, useState } from 'react';
import { mockApi } from '../api/mocks';
import type { AuditEntry, CapacitySnapshot, GlobalSettings, PoolProject } from '../types/api';
import {
  Server,
  Activity,
  AlertTriangle,
  Settings as SettingsIcon,
  Database,
  Loader2,
  Save,
  ScrollText,
  ShieldAlert,
  Snowflake,
} from 'lucide-react';
import toast from 'react-hot-toast';

function StatBox({
  label,
  value,
  accent,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  accent: 'blue' | 'green' | 'amber' | 'red' | 'gray';
  hint?: string;
}) {
  const palette: Record<typeof accent, { bar: string; text: string }> = {
    blue: { bar: 'bg-cyber-blue-accent', text: 'text-cyber-blue-accent' },
    green: { bar: 'bg-emerald-500', text: 'text-emerald-700' },
    amber: { bar: 'bg-amber-500', text: 'text-amber-700' },
    red: { bar: 'bg-red-500', text: 'text-red-700' },
    gray: { bar: 'bg-cyber-gray-light', text: 'text-cyber-gray-dark' },
  };
  const p = palette[accent];
  return (
    <div className="relative p-5 rounded-brand border border-cyber-gray-border bg-white overflow-hidden">
      <div className={`absolute top-0 left-0 right-0 h-0.5 ${p.bar}`} />
      <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-cyber-gray-light">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${p.text}`}>{value}</p>
      {hint && <p className="text-[11px] text-cyber-gray-light mt-1">{hint}</p>}
    </div>
  );
}

export const AdminSettings = () => {
  const draftsInitialized = useRef(false);
  const [settings, setSettings] = useState<GlobalSettings | null>(null);
  const [capacity, setCapacity] = useState<CapacitySnapshot | null>(null);
  const [pool, setPool] = useState<PoolProject[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);


  const [draftTTL, setDraftTTL] = useState(2);
  const [draftFreeze, setDraftFreeze] = useState(24);
  const [draftCap, setDraftCap] = useState(0.9);

  const refresh = useCallback(async () => {
    try {
      const [s, c, p, a] = await Promise.all([
        mockApi.getSettings(),
        mockApi.getCapacity(),
        mockApi.getPool(),
        mockApi.getAudit(50),
      ]);
      setSettings(s);
      setCapacity(c);
      setPool(p);
      setAudit(a);
    } catch (err) {
      console.error('Admin refresh failed', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);


  useEffect(() => {
    if (settings && !draftsInitialized.current) {
      setDraftTTL(settings.default_ttl_hours);
      setDraftFreeze(settings.freeze_duration_hours);
      setDraftCap(settings.max_cluster_utilization);
      draftsInitialized.current = true;
    }

  }, [settings]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await mockApi.updateSettings({
        default_ttl_hours: draftTTL,
        freeze_duration_hours: draftFreeze,
        max_cluster_utilization: draftCap,
      });
      setSettings(updated);
      toast.success('Настройки применены к новым стендам');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-cyber-blue-accent" />
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <p className="text-[11px] font-bold text-cyber-gray-light uppercase tracking-[0.18em]">
          Администрирование
        </p>
        <h1 className="text-[22px] font-bold text-cyber-gray-dark flex items-center mt-1">
          <SettingsIcon className="mr-2.5 w-5 h-5 text-cyber-blue-accent" />
          Стенд администратора
        </h1>
        <p className="text-sm text-cyber-gray-light mt-1">
          Управление лимитами времени жизни, ёмкостью кластера КИ и аудит действий.
        </p>
      </div>


      <div className="bg-white rounded-brand border border-cyber-gray-border p-6">
        <h2 className="text-[11px] font-bold text-cyber-gray-dark mb-4 uppercase tracking-[0.16em] flex items-center">
          <Activity className="w-4 h-4 mr-2 text-cyber-blue-accent" /> Состояние кластера
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatBox
            label="Утилизация КИ"
            value={`${capacity?.utilization_pct ?? 0}%`}
            accent={capacity?.over_threshold ? 'red' : capacity && capacity.utilization_pct > 60 ? 'amber' : 'green'}
            hint={`Порог: ${capacity?.threshold_pct ?? 90}%`}
          />
          <StatBox label="Свободно в пуле" value={`${capacity?.pool_free ?? 0}/${capacity?.pool_total ?? 0}`} accent="green" />
          <StatBox label="Активных стендов" value={capacity?.pool_active ?? 0} accent="blue" />
          <StatBox label="Заморожено" value={capacity?.pool_frozen ?? 0} accent="amber" />
        </div>
        {capacity?.over_threshold && (
          <div className="mt-4 flex items-start p-3 rounded-brand bg-red-50 border border-red-200">
            <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mr-2" />
            <p className="text-sm text-red-700">
              Утилизация выше {capacity.threshold_pct}%. Новые стенды будут отклоняться API до освобождения ресурсов.
            </p>
          </div>
        )}
      </div>


      <div className="bg-white rounded-brand border border-cyber-gray-border p-6">
        <h2 className="text-[11px] font-bold text-cyber-gray-dark mb-1 uppercase tracking-[0.16em] flex items-center">
          <SettingsIcon className="w-4 h-4 mr-2 text-cyber-blue-accent" /> Глобальные настройки
        </h2>
        <p className="text-xs text-cyber-gray-light mb-4">
          Применяются к новым стендам мгновенно. У уже запущенных стендов TTL не меняется до явного override.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <label className="block text-xs font-bold text-cyber-gray-light uppercase tracking-wider mb-2">
              Время жизни лабы (ч)
            </label>
            <input
              type="number"
              min={1}
              max={72}
              value={draftTTL}
              onChange={(e) => setDraftTTL(parseInt(e.target.value || '1', 10))}
              className="w-full px-4 py-2.5 border border-cyber-gray-border rounded-brand focus:ring-2 focus:ring-cyber-blue-accent/30 focus:border-cyber-blue-accent outline-none bg-white text-sm"
            />
            <p className="text-xs text-cyber-gray-light mt-1">по умолчанию 2 ч (минимум 1, максимум 72)</p>
          </div>

          <div>
            <label className="block text-xs font-bold text-cyber-gray-light uppercase tracking-wider mb-2">
              Заморозка (ч)
            </label>
            <input
              type="number"
              min={1}
              max={168}
              value={draftFreeze}
              onChange={(e) => setDraftFreeze(parseInt(e.target.value || '1', 10))}
              className="w-full px-4 py-2.5 border border-cyber-gray-border rounded-brand focus:ring-2 focus:ring-cyber-blue-accent/30 focus:border-cyber-blue-accent outline-none bg-white text-sm"
            />
            <p className="text-xs text-cyber-gray-light mt-1">сколько держим стенд в FREEZE для аудита</p>
          </div>

          <div>
            <label className="block text-xs font-bold text-cyber-gray-light uppercase tracking-wider mb-2">
              Порог утилизации (%)
            </label>
            <input
              type="number"
              min={10}
              max={100}
              step={1}
              value={Math.round(draftCap * 100)}
              onChange={(e) => setDraftCap(parseFloat(e.target.value || '90') / 100)}
              className="w-full px-4 py-2.5 border border-cyber-gray-border rounded-brand focus:ring-2 focus:ring-cyber-blue-accent/30 focus:border-cyber-blue-accent outline-none bg-white text-sm"
            />
            <p className="text-xs text-cyber-gray-light mt-1">блокирует новые деплои выше этого значения</p>
          </div>
        </div>

        <div className="mt-6 flex items-center justify-end gap-3">
          <span className="text-xs text-cyber-gray-light">
            Текущие: ttl={settings?.default_ttl_hours}ч | freeze={settings?.freeze_duration_hours}ч | cap={Math.round((settings?.max_cluster_utilization ?? 0) * 100)}%
          </span>
          <button
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center px-5 py-2.5 bg-cyber-blue-accent text-white rounded-brand font-semibold hover:bg-cyber-blue disabled:bg-gray-300 shadow-sm"
          >
            {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
            Сохранить
          </button>
        </div>
      </div>


      <div className="bg-white rounded-brand border border-cyber-gray-border p-6">
        <h2 className="text-[11px] font-bold text-cyber-gray-dark mb-4 uppercase tracking-[0.16em] flex items-center">
          <Database className="w-4 h-4 mr-2 text-cyber-blue-accent" /> Пул предсозданных проектов КИ ({pool.length})
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {pool.map((p) => {
            const status = p.stand_statuses[0] || 'FREE';
            const accent =
              status === 'FREE'
                ? 'border-emerald-200 bg-emerald-50'
                : status === 'FREEZE'
                ? 'border-amber-200 bg-amber-50'
                : status === 'CLEANING'
                ? 'border-cyber-gray-border bg-cyber-gray-surface'
                : 'border-cyber-blue-accent/30 bg-cyber-blue-accent/5';
            return (
              <div key={p.project_id} className={`p-3 rounded-brand border ${accent}`}>
                <div className="flex justify-between items-start">
                  <div>
                    <p className="font-mono font-bold text-sm text-cyber-gray-dark">{p.name}</p>
                    <p className="font-mono text-[10px] text-cyber-gray-light break-all">{p.openstack_project_id}</p>
                  </div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-cyber-gray-dark">{status}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>


      <div className="bg-white rounded-brand border border-cyber-gray-border p-6">
        <h2 className="text-[11px] font-bold text-cyber-gray-dark mb-4 uppercase tracking-[0.16em] flex items-center">
          <ScrollText className="w-4 h-4 mr-2 text-cyber-blue-accent" /> Аудит-лог действий
        </h2>
        {audit.length === 0 ? (
          <p className="text-sm text-cyber-gray-light text-center py-6">Пока нет событий.</p>
        ) : (
          <div className="font-mono text-[12px] space-y-1 max-h-96 overflow-y-auto">
            {audit.map((entry, i) => (
              <div key={i} className="flex gap-3 py-1.5 border-b border-gray-100 last:border-0">
                <span className="text-cyber-gray-light flex-shrink-0">{new Date(entry.timestamp).toLocaleString('ru-RU')}</span>
                <span className="font-bold text-cyber-blue-accent flex-shrink-0">{entry.actor}</span>
                <span className="font-bold text-cyber-gray-dark flex-shrink-0">{entry.action}</span>
                {entry.target && <span className="text-cyber-gray-light flex-shrink-0">{entry.target}</span>}
                {entry.detail && <span className="text-cyber-gray-light truncate">{entry.detail}</span>}
              </div>
            ))}
          </div>
        )}
      </div>


      <div className="bg-white rounded-brand border border-cyber-gray-border p-6">
        <h2 className="text-[11px] font-bold text-cyber-gray-dark mb-4 uppercase tracking-[0.16em] flex items-center">
          <ShieldAlert className="w-4 h-4 mr-2 text-cyber-blue-accent" /> Безопасность & DevSecOps
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
          <div className="p-3 rounded-brand border border-green-200 bg-green-50">
            <p className="font-bold text-green-700 flex items-center"><Server className="w-4 h-4 mr-1.5" /> Контейнеры non-root</p>
            <p className="text-xs text-green-700/80 mt-1">Все образы запускаются от UID 1000.</p>
          </div>
          <div className="p-3 rounded-brand border border-green-200 bg-green-50">
            <p className="font-bold text-green-700">Native SSH-ключи КИ</p>
            <p className="text-xs text-green-700/80 mt-1">Пароли в коде запрещены, ключи генерирует Nova.</p>
          </div>
          <div className="p-3 rounded-brand border border-green-200 bg-green-50">
            <p className="font-bold text-green-700">Ruff + Bandit + Gitleaks + Trivy</p>
            <p className="text-xs text-green-700/80 mt-1">В пайплайне CI/CD.</p>
          </div>
        </div>
      </div>

      <div className="text-xs text-cyber-gray-light flex items-center gap-1.5">
        <Snowflake className="w-3 h-3" />
        Изменения настроек применяются <span className="font-bold">только к новым стендам</span>. Для активных используйте слайдер TTL в дашборде.
      </div>
    </div>
  );
};
