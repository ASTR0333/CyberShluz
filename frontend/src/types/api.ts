export type StandStatus = 'PENDING' | 'DEPLOYING' | 'READY' | 'FREEZE' | 'CLEANING' | 'FREE' | 'FAILED';

export interface PubkeyRequest {
  public_key: string;
}

export interface DeployRequest {
  user_id: string;
  lab_id: number;
  role: 'student' | 'teacher';
}

export interface DeployResponse {
  stand_id: string;
  project_id: string;
  status: StandStatus;
  message: string;
}

export interface VMInfo {
  server_id: string;
  name: string;
  expected_ip: string;
  ip?: string;
  floating_ip?: string;
  status: string;
}

export interface StandStatusResponse {
  stand_id: string;
  status: StandStatus;
  ip_address: string | null;
  expires_at: string | null;
  frozen_until: string | null;
  message?: string;
  vms?: Record<string, VMInfo>;
}

export interface CheckResponse {
  stand_id: string;
  check_task_id: string;
  status: 'CHECKING';
}

export interface CheckResultResponse {
  status: 'PASSED' | 'FAILED' | 'CHECKING' | 'ERROR';
  log: string;
  details?: Record<string, boolean>;
}

export interface StudentStand {
  id: number;
  student_name: string | null;
  status: string;
  ip_address: string | null;
  expires_at: string | null;
  frozen_until: string | null;
  created_at?: string | null;
  vm_count?: number;
  vms?: Record<string, VMInfo>;
  last_check_result?: { status: string; log: string; details?: Record<string, boolean> } | null;
}

export interface GlobalSettings {
  default_ttl_hours: number;
  freeze_duration_hours: number;
  max_cluster_utilization: number;
}

export interface CapacitySnapshot {
  utilization_pct: number;
  threshold_pct: number;
  over_threshold: boolean;
  pool_total: number;
  pool_free: number;
  pool_active: number;
  pool_frozen: number;
  pool_cleaning: number;
}

export interface AuditEntry {
  timestamp: string;
  actor: string;
  action: string;
  target: string | null;
  detail: string | null;
}

export interface PoolProject {
  project_id: number;
  name: string;
  openstack_project_id: string;
  network_id: string;
  stand_count: number;
  stand_statuses: string[];
}
