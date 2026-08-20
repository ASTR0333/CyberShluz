import type {
  DeployResponse,
  StandStatusResponse,
  CheckResponse,
  CheckResultResponse,
  DeployRequest,
  PubkeyRequest,
  GlobalSettings,
  CapacitySnapshot,
  AuditEntry,
  PoolProject,
  StudentStand,
  DeploymentOptions,
  MyStandSummary,
  ConsoleLinkResponse,
} from '../types/api';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';
const SSH_KEY_INSTALL_TIMEOUT_MS = 180_000;




export interface AuthInfo {
  access_token: string;
  username: string;
  role: 'student' | 'teacher' | 'admin';
  display_name: string;
  user_id: number;
}

const AUTH_KEY = 'cyber_auth';

export function getAuth(): AuthInfo | null {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    return raw ? (JSON.parse(raw) as AuthInfo) : null;
  } catch {
    return null;
  }
}

export function saveAuth(info: AuthInfo) {
  localStorage.setItem(AUTH_KEY, JSON.stringify(info));
}

export function clearAuth() {
  localStorage.removeItem(AUTH_KEY);
  localStorage.removeItem('my_stand_id');
  localStorage.removeItem('my_user_id');
}




async function apiFetch<T>(url: string, options?: RequestInit, timeoutMs = 15_000): Promise<T> {
  const auth = getAuth();
  const timeoutController = new AbortController();
  const timeoutId = window.setTimeout(() => timeoutController.abort(), timeoutMs);
  if (options?.signal) {
    if (options.signal.aborted) timeoutController.abort(options.signal.reason);
    else options.signal.addEventListener('abort', () => timeoutController.abort(options.signal?.reason), { once: true });
  }
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options?.headers as Record<string, string>) || {}),
  };
  if (auth?.access_token) {
    headers['Authorization'] = `Bearer ${auth.access_token}`;
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${url}`, { ...options, headers, signal: timeoutController.signal });
  } catch (error) {
    if (timeoutController.signal.aborted && !options?.signal?.aborted) {
      throw new Error(`Сервер не ответил за ${Math.ceil(timeoutMs / 1000)} секунд`, { cause: error });
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
  if (res.status === 401) {

    clearAuth();
    if (!window.location.pathname.startsWith('/login')) {
      window.location.assign('/login');
    }
    throw new Error('Сессия истекла, войдите снова');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  const txt = await res.text();
  return txt ? JSON.parse(txt) : ({} as T);
}




export const authApi = {
  login: (username: string, password: string): Promise<AuthInfo> =>
    apiFetch('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  me: (): Promise<{ username: string; role: string; display_name: string; user_id: number }> =>
    apiFetch('/auth/me'),
};

export const mockApi = {

  getDeploymentOptions: (): Promise<DeploymentOptions> =>
    apiFetch('/deployment-options'),

  deploy: (request: DeployRequest): Promise<DeployResponse> =>
    apiFetch('/deploy', {
      method: 'POST',
      body: JSON.stringify(request),
    }),

  getStatus: (stand_id: string): Promise<StandStatusResponse> =>
    apiFetch(`/status/${stand_id}`),

  getMyStands: (): Promise<MyStandSummary[]> => apiFetch('/stands/my'),

  freeze: (stand_id: string, reason?: string): Promise<{ stand_id: string; status: string; frozen_until: string }> =>
    apiFetch(`/freeze/${stand_id}`, {
      method: 'POST',
      body: JSON.stringify({ reason: reason || 'Запрос помощи' }),
    }),

  check: (stand_id: string, manual_confirmations: string[] = [], lab_template?: string): Promise<CheckResponse> =>
    apiFetch(`/check/${stand_id}`, {
      method: 'POST',
      body: JSON.stringify({
        lab_template: lab_template || 'lab03_cyber',
        manual_confirmations,
      }),
    }),

  getCheckResult: (stand_id: string): Promise<CheckResultResponse> =>
    apiFetch(`/check/${stand_id}/result`),

  cleanup: (stand_id: string): Promise<{ stand_id: string; status: string }> =>
    apiFetch(`/cleanup/${stand_id}`, { method: 'POST' }),

  submitPubkey: (stand_id: string, req: PubkeyRequest): Promise<{ message: string }> =>
    apiFetch(`/stand/${stand_id}/pubkey`, {
      method: 'POST',
      body: JSON.stringify(req),
    }, SSH_KEY_INSTALL_TIMEOUT_MS),

  createConsoleLink: (stand_id: string, vm_role: string): Promise<ConsoleLinkResponse> =>
    apiFetch(`/stand/${stand_id}/console/${encodeURIComponent(vm_role)}`, { method: 'POST' }),


  getStands: (): Promise<StudentStand[]> => apiFetch('/admin/stands'),

  getStandDetail: (stand_id: string): Promise<StudentStand> =>
    apiFetch(`/admin/stands/${stand_id}`),

  deleteStand: (stand_id: string): Promise<{ stand_id: string; status: string }> =>
    apiFetch(`/admin/stands/${stand_id}`, { method: 'DELETE' }),

  updateTTL: (stand_id: string, ttl_hours: number): Promise<{ stand_id: string; new_expires_at: string }> =>
    apiFetch(`/admin/stands/${stand_id}/ttl`, {
      method: 'PUT',
      body: JSON.stringify({ ttl_hours }),
    }),

  thawStand: (stand_id: string): Promise<{ stand_id: string; status: string; new_expires_at: string }> =>
    apiFetch(`/admin/stands/${stand_id}/thaw`, { method: 'POST' }),

  getSettings: (): Promise<GlobalSettings> => apiFetch('/admin/settings'),

  updateSettings: (payload: GlobalSettings): Promise<GlobalSettings> =>
    apiFetch('/admin/settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  getCapacity: (): Promise<CapacitySnapshot> => apiFetch('/admin/capacity'),

  getPool: (): Promise<PoolProject[]> => apiFetch('/admin/pool'),

  getAudit: (limit = 50): Promise<AuditEntry[]> => apiFetch(`/admin/audit?limit=${limit}`),
};
