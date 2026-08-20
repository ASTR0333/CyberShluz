export type StandStatus = 'PENDING' | 'DEPLOYING' | 'READY' | 'FREEZE' | 'CLEANING' | 'FREE' | 'FAILED';

export interface PubkeyRequest {
  public_key: string;
}

export interface DeployRequest {
  user_id: string;
  lab_id: number;
  role: 'student' | 'teacher';
  deployment?: DeploymentConfig;
}

export interface NetworkDeploymentSpec {
  cidr: string;
  gateway: string;
  dhcp_start: string;
  dhcp_end: string;
  dns_nameservers: string[];
  external_network: string;
}

export type VMRole = 'L-MS' | 'L-NFS' | 'L-PGSQL' | 'W-DC' | 'V-HYPERV';

export interface VMDeploymentSpec {
  role: VMRole;
  image: string;
  flavor: string;
  ip: string;
  enabled: boolean;
}

export interface DeploymentConfig {
  network: NetworkDeploymentSpec;
  vms: VMDeploymentSpec[];
}

export interface DeploymentOptions {
  default: DeploymentConfig;
  images: string[];
  flavors: string[];
  external_networks: string[];
  catalog_error?: string | null;
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
  error?: string;
}

export interface StandStatusResponse {
  stand_id: string;
  status: StandStatus;
  ip_address: string | null;
  expires_at: string | null;
  frozen_until: string | null;
  message?: string;
  progress?: number | null;
  vms?: Record<string, VMInfo>;
  network?: {
    cidr?: string;
    gateway?: string;
    external_network?: string;
  };
}

export interface MyStandSummary {
  stand_id: string;
  status: StandStatus;
  ip_address: string | null;
  expires_at: string | null;
  created_at: string | null;
}

export interface ConsoleLinkResponse {
  launch_url: string;
  server_id: string;
}

export interface CheckResponse {
  stand_id: string;
  check_task_id: string;
  status: 'CHECKING';
}

export interface CheckResultResponse {
  status: 'PASSED' | 'FAILED' | 'CHECKING' | 'ERROR' | 'REVIEW_REQUIRED';
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
