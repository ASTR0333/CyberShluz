import { Fragment, useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { mockApi } from '../api/mocks';
import type { StudentStand, StandStatus } from '../types/api';
import { ProgressBadge } from '../components/ProgressBadge';
import {
  Users,
  Snowflake,
  Search,
  SlidersHorizontal,
  Trash2,
  Loader2,
  Sun,
  Download,
  ChevronDown,
  ChevronRight,
  Plus,
} from 'lucide-react';
import toast from 'react-hot-toast';

export const TeacherDashboard = () => {
  const navigate = useNavigate();
  const [students, setStudents] = useState<StudentStand[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [ttlDraft, setTtlDraft] = useState<Record<number, number>>({});

  const fetchStands = useCallback(async () => {
    try {
      const data = await mockApi.getStands();
      setStudents(data);
    } catch (error) {
      console.error('Не удалось обновить список стендов', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStands();
    const interval = setInterval(fetchStands, 5000);
    return () => clearInterval(interval);
  }, [fetchStands]);

  const handleFreeze = async (id: number) => {
    try {
      await mockApi.freeze(String(id), 'Заморожено преподавателем');
      toast.success('Стенд заморожен на 24ч');
      fetchStands();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Ошибка заморозки');
    }
  };

  const handleThaw = async (id: number) => {
    try {
      await mockApi.thawStand(String(id));
      toast.success('Стенд разморожен');
      fetchStands();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Ошибка разморозки');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await mockApi.deleteStand(String(id));
      toast.success('Стенд отправлен на удаление');
      fetchStands();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Ошибка удаления');
    }
  };

  const handleTtlChange = async (id: number, ttlHours: number) => {
    try {
      await mockApi.updateTTL(String(id), ttlHours);
      toast.success(`TTL обновлен: ${ttlHours}ч`);
      fetchStands();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Ошибка обновления TTL');
    }
  };

  const downloadKey = (id: number) => {
    const base = import.meta.env.VITE_API_URL || '/api/v1';
    window.open(`${base}/stand/${id}/privkey`, '_blank');
  };

  const filteredStudents = students.filter((s) =>
    (s.student_name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    String(s.id).includes(searchTerm),
  );

  const activeCount = students.filter((s) => !['FREE', 'CLEANING'].includes(s.status)).length;
  const freeCount = students.filter((s) => s.status === 'FREE').length;
  const frozenCount = students.filter((s) => s.status === 'FREEZE').length;

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div>
        <p className="text-[11px] font-bold text-cyber-blue-accent uppercase tracking-[0.18em]">Киберполигон</p>
        <h1 className="text-2xl sm:text-[28px] text-cyber-blue-dark font-black tracking-[-0.025em] mt-1 mb-5">Мониторинг инфраструктуры</h1>

        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 bg-white p-3 rounded-t-brand border border-cyber-gray-border border-b-0 shadow-[0_8px_24px_rgba(0,32,77,0.04)]">
          <div className="relative w-full sm:w-80">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-cyber-gray-light w-4 h-4" />
            <input
              type="text"
              placeholder="Поиск по ID или имени студента"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-9 pr-4 py-2 border border-cyber-gray-border rounded focus:ring-2 focus:ring-cyber-blue-accent/30 focus:border-cyber-blue-accent outline-none w-full transition-all text-sm bg-white"
            />
          </div>

          <button
            onClick={() => navigate('/launch')}
            className="flex items-center gap-2 px-4 py-2 border border-cyber-blue-accent text-cyber-blue-accent rounded-brand bg-white hover:bg-[#E7F2FB] transition-colors text-sm font-bold"
          >
            <Plus className="w-4 h-4" />
            Новый стенд
          </button>
        </div>
      </div>


      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-white rounded-brand border border-cyber-gray-border p-4 relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-0.5 bg-cyber-blue-accent" />
          <p className="text-[10px] font-bold text-cyber-gray-light uppercase tracking-[0.16em]">Всего стендов</p>
          <p className="text-2xl font-bold text-cyber-gray-dark mt-1">{students.length}</p>
        </div>
        <div className="bg-white rounded-brand border border-cyber-gray-border p-4 relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-0.5 bg-emerald-500" />
          <p className="text-[10px] font-bold text-cyber-gray-light uppercase tracking-[0.16em]">Активные</p>
          <p className="text-2xl font-bold text-cyber-gray-dark mt-1">{activeCount}</p>
        </div>
        <div className="bg-white rounded-brand border border-cyber-gray-border p-4 relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-0.5 bg-amber-500" />
          <p className="text-[10px] font-bold text-cyber-gray-light uppercase tracking-[0.16em]">Заморожено</p>
          <p className="text-2xl font-bold text-cyber-gray-dark mt-1">{frozenCount}</p>
        </div>
        <div className="bg-white rounded-brand border border-cyber-gray-border p-4 relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-0.5 bg-cyber-gray-light" />
          <p className="text-[10px] font-bold text-cyber-gray-light uppercase tracking-[0.16em]">Свободно в пуле</p>
          <p className="text-2xl font-bold text-cyber-gray-dark mt-1">{freeCount}</p>
        </div>
      </div>

      <div className="bg-white rounded-b-brand border border-cyber-gray-border overflow-hidden">
        {loading ? (
          <div className="p-16 flex justify-center">
            <Loader2 className="w-8 h-8 animate-spin text-cyber-blue-accent" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead className="bg-white border-b border-cyber-gray-border">
                <tr>
                  <th className="px-4 py-3 text-sm font-medium text-cyber-gray-dark w-10" aria-label="Раскрыть строку"></th>
                  <th className="px-4 py-3 text-sm font-medium text-cyber-gray-dark">ID</th>
                  <th className="px-4 py-3 text-sm font-medium text-cyber-gray-dark">Студент</th>
                  <th className="px-4 py-3 text-sm font-medium text-cyber-gray-dark">Состояние</th>
                  <th className="px-4 py-3 text-sm font-medium text-cyber-gray-dark">IP-адрес</th>
                  <th className="px-4 py-3 text-sm font-medium text-cyber-gray-dark text-center">ВМ</th>
                  <th className="px-4 py-3 text-sm font-medium text-cyber-gray-dark">TTL</th>
                  <th className="px-4 py-3 text-sm font-medium text-cyber-gray-dark text-right">Управление</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredStudents.map((student) => {
                  const isActive = !['FREE', 'CLEANING'].includes(student.status);
                  const isFrozen = student.status === 'FREEZE';
                  const isExpanded = expandedId === student.id;
                  return (
                    <Fragment key={student.id}>
                      <tr className="hover:bg-gray-50 transition-colors">
                        <td className="px-4 py-3">
                          {(student.vms || student.last_check_result) ? (
                            <button
                              onClick={() => setExpandedId(isExpanded ? null : student.id)}
                              className="text-cyber-gray-light hover:text-cyber-blue"
                              aria-label="Toggle details"
                            >
                              {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                            </button>
                          ) : null}
                        </td>
                        <td className="px-4 py-3 font-mono text-sm text-cyber-gray-light">{student.id}</td>
                        <td className="px-4 py-3">
                          {student.student_name ? (
                            <div className="flex items-center">
                              <div className="w-8 h-8 rounded-full bg-cyber-blue-accent/10 text-cyber-blue-accent flex items-center justify-center font-bold mr-3 border border-cyber-blue-accent/20">
                                {student.student_name[0]?.toUpperCase() || '?'}
                              </div>
                              <span className="font-semibold text-cyber-gray-dark text-sm">{student.student_name}</span>
                            </div>
                          ) : (
                            <span className="text-cyber-gray-light">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <ProgressBadge status={student.status as StandStatus} />
                        </td>
                        <td className="px-4 py-3 font-mono text-sm text-cyber-gray-light">
                          {student.ip_address ? (
                            <span className="bg-gray-100 px-2 py-1 rounded border border-gray-200">{student.ip_address}</span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="px-4 py-3 text-sm text-cyber-gray-light text-center">{student.vm_count || 0}</td>
                        <td className="px-4 py-3 min-w-[180px]">
                          {isActive && (
                            <div className="flex items-center gap-2">
                              <SlidersHorizontal className="w-4 h-4 text-gray-400" />
                              <input
                                type="range"
                                min={1}
                                max={24}
                                value={ttlDraft[student.id] ?? 2}
                                onChange={(e) =>
                                  setTtlDraft((s) => ({ ...s, [student.id]: parseInt(e.target.value, 10) }))
                                }
                                onMouseUp={() =>
                                  handleTtlChange(student.id, ttlDraft[student.id] ?? 2)
                                }
                                onTouchEnd={() =>
                                  handleTtlChange(student.id, ttlDraft[student.id] ?? 2)
                                }
                                className="flex-1 h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-cyber-blue"
                              />
                              <span className="font-mono text-xs text-cyber-gray-dark w-8 text-right tabular-nums">
                                {ttlDraft[student.id] ?? 2}ч
                              </span>
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right space-x-2 whitespace-nowrap">
                          {isActive && (
                            <button
                              onClick={() => downloadKey(student.id)}
                              className="inline-flex items-center text-cyber-gray-light hover:text-cyber-gray-dark font-semibold text-sm transition-colors"
                              title="Скачать приватный ключ (только для администратора)"
                            >
                              <Download className="w-4 h-4 mr-1" />
                              Ключ
                            </button>
                          )}
                          {isActive && !isFrozen && (
                            <button
                              onClick={() => handleFreeze(student.id)}
                              className="inline-flex items-center text-cyber-blue-accent hover:text-cyber-blue font-semibold text-sm transition-colors"
                              title="Заморозить на 24ч"
                            >
                              <Snowflake className="w-4 h-4 mr-1" />
                              Freeze
                            </button>
                          )}
                          {isFrozen && (
                            <button
                              onClick={() => handleThaw(student.id)}
                              className="inline-flex items-center text-amber-600 hover:text-amber-700 font-semibold text-sm transition-colors"
                              title="Разморозить"
                            >
                              <Sun className="w-4 h-4 mr-1" />
                              Thaw
                            </button>
                          )}
                          {(isActive || isFrozen) && (
                            <button
                              onClick={() => handleDelete(student.id)}
                              className="inline-flex items-center text-red-600 hover:text-red-700 font-semibold text-sm transition-colors"
                              title="Удалить стенд"
                            >
                              <Trash2 className="w-4 h-4 mr-1" />
                              Drop
                            </button>
                          )}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr key={`exp-${student.id}`} className="bg-gray-50/60">
                          <td colSpan={8} className="px-6 py-4 text-xs">
                            {student.vms && (
                              <div className="mb-3">
                                <p className="font-bold text-cyber-gray-light uppercase tracking-wider mb-2">Топология</p>
                                <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                                  {Object.entries(student.vms).map(([role, vm]) => (
                                    <div
                                      key={role}
                                      className={`p-2 rounded border text-center ${
                                        vm.status === 'ACTIVE'
                                          ? 'bg-green-50 border-green-200'
                                          : 'bg-red-50 border-red-200'
                                      }`}
                                    >
                                      <p className="font-mono font-bold text-xs">{role}</p>
                                      <p className="font-mono text-[10px] text-gray-500">{vm.ip || vm.expected_ip}</p>
                                      <p className="text-[10px] font-bold mt-1">{vm.status}</p>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                            {student.last_check_result && (
                              <div>
                                <p className="font-bold text-cyber-gray-light uppercase tracking-wider mb-2">
                                  Последняя проверка: {student.last_check_result.status}
                                </p>
                                <pre className="font-mono text-[11px] text-cyber-gray-dark bg-black/5 p-3 rounded whitespace-pre-wrap leading-relaxed">
                                  {student.last_check_result.log}
                                </pre>
                              </div>
                            )}
                            {!student.vms && !student.last_check_result && (
                              <p className="text-cyber-gray-light">Нет данных о стенде.</p>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {!loading && filteredStudents.length === 0 && (
          <div className="p-16 text-center text-cyber-gray-light flex flex-col items-center bg-gray-50/50">
            <Users className="w-12 h-12 text-gray-300 mb-4" />
            <p className="font-medium text-lg">Записи не найдены</p>
          </div>
        )}
      </div>
    </div>
  );
};
