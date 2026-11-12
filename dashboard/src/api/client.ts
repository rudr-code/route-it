import type {
  DynamicEventCreate,
  EventInjectResponse,
  HealthResponse,
  ProblemCreateRequest,
  ProblemResponse,
  SolutionResponse,
  SolveJob,
  SolveRequest,
} from './types';

export const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

function formatApiError(status: number, data: unknown): string {
  if (data && typeof data === 'object') {
    const d = data as Record<string, unknown>;
    if (Array.isArray(d.detail)) {
      const msgs = (d.detail as Array<{ loc?: unknown[]; msg?: string }>).map((e) => {
        const loc = Array.isArray(e.loc) ? e.loc.join('.') : 'request';
        return `${loc}: ${e.msg ?? JSON.stringify(e)}`;
      });
      return `[${status}] Validation error:\n${msgs.join('\n')}`;
    }
    if (typeof d.detail === 'string') return `[${status}] ${d.detail}`;
    if (typeof d.message === 'string') return `[${status}] ${d.message}`;
    return `[${status}] ${JSON.stringify(data)}`;
  }
  return `[${status}] ${String(data)}`;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem('routeit_token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options?.headers as Record<string, string> | undefined),
  };

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
  if (!res.ok) {
    let data: unknown = await res.text();
    try { data = JSON.parse(data as string); } catch {}
    throw new Error(formatApiError(res.status, data));
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export const api = {
  // Original Solver & Problem Endpoints
  health: (): Promise<HealthResponse> => request('/health'),
  createProblem: (body: ProblemCreateRequest): Promise<ProblemResponse> =>
    request('/problems', { method: 'POST', body: JSON.stringify(body) }),
  listProblems: (): Promise<ProblemResponse[]> => request('/problems'),
  solveProblem: (problemId: string, body: SolveRequest): Promise<SolveJob> =>
    request(`/problems/${problemId}/solve`, { method: 'POST', body: JSON.stringify(body) }),
  getJob: (problemId: string, jobId: string): Promise<SolveJob> =>
    request(`/problems/${problemId}/jobs/${jobId}`),
  getSolution: (problemId: string): Promise<SolutionResponse> =>
    request(`/problems/${problemId}/solution`),
  injectEvent: (problemId: string, event: DynamicEventCreate): Promise<EventInjectResponse> =>
    request(`/problems/${problemId}/events`, { method: 'POST', body: JSON.stringify(event) }),
  deleteProblem: (problemId: string): Promise<void> =>
    request(`/problems/${problemId}`, { method: 'DELETE' }),

  // New Intelligent Delivery Management Endpoints
  login: (username: string, password: string): Promise<any> =>
    request('/delivery/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  getOverview: (): Promise<any> => request('/delivery/admin/overview'),
  listLocations: (): Promise<any[]> => request('/delivery/locations'),
  createLocation: (body: any): Promise<any> =>
    request('/delivery/locations', { method: 'POST', body: JSON.stringify(body) }),
  updateLocation: (id: string, body: any): Promise<any> =>
    request(`/delivery/locations/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteLocation: (id: string): Promise<void> =>
    request(`/delivery/locations/${id}`, { method: 'DELETE' }),

  listVehicles: (): Promise<any[]> => request('/delivery/vehicles'),
  createVehicle: (body: any): Promise<any> =>
    request('/delivery/vehicles', { method: 'POST', body: JSON.stringify(body) }),

  listDrivers: (): Promise<any[]> => request('/delivery/drivers'),
  createDriver: (body: any): Promise<any> =>
    request('/delivery/drivers', { method: 'POST', body: JSON.stringify(body) }),

  optimizeBatch: (body: any): Promise<any> =>
    request('/delivery/batches/optimize', { method: 'POST', body: JSON.stringify(body) }),
  listBatches: (): Promise<any[]> => request('/delivery/batches'),
  getBatch: (batchId: string): Promise<any> => request(`/delivery/batches/${batchId}`),
  injectBatchIncident: (batchId: string, body: any): Promise<any> =>
    request(`/delivery/batches/${batchId}/incidents`, { method: 'POST', body: JSON.stringify(body) }),

  listDispatchJobs: (driverId?: string): Promise<any[]> =>
    request(`/delivery/dispatch/jobs${driverId ? `?driver_id=${driverId}` : ''}`),
  assignDriver: (jobId: string, driverId: string): Promise<any> =>
    request(`/delivery/dispatch/jobs/${jobId}/assign`, {
      method: 'POST',
      body: JSON.stringify({ driver_id: driverId }),
    }),
  cancelJob: (jobId: string): Promise<any> =>
    request(`/delivery/dispatch/jobs/${jobId}/cancel`, { method: 'POST' }),
  acceptJob: (jobId: string, driverId: string): Promise<any> =>
    request(`/delivery/driver/jobs/${jobId}/accept?driver_id=${encodeURIComponent(driverId)}`, {
      method: 'POST',
    }),

  updateDeliveryProgress: (deliveryId: string, status: 'IN_TRANSIT' | 'ARRIVED'): Promise<any> =>
    request(`/delivery/deliveries/${deliveryId}/progress`, {
      method: 'POST',
      body: JSON.stringify({ status }),
    }),
  verifyOtp: (deliveryId: string, otpCode: string, driverId?: string): Promise<any> =>
    request(`/delivery/deliveries/${deliveryId}/verify-otp`, {
      method: 'POST',
      body: JSON.stringify({ otp_code: otpCode, driver_id: driverId }),
    }),
  failDelivery: (deliveryId: string, reason: string, driverId?: string): Promise<any> =>
    request(`/delivery/deliveries/${deliveryId}/fail`, {
      method: 'POST',
      body: JSON.stringify({ reason, driver_id: driverId }),
    }),
  verifyReturnToHub: (deliveryId: string): Promise<any> =>
    request(`/delivery/deliveries/${deliveryId}/return-to-hub`, { method: 'POST' }),

  trackDelivery: (token: string): Promise<any> =>
    request(`/delivery/track/${encodeURIComponent(token)}`),
  getHistory: (): Promise<any[]> => request('/delivery/history'),

  // Multi-Algorithm Benchmarking Endpoints
  runBenchmark: (body?: any): Promise<any> =>
    request('/benchmarks/run', { method: 'POST', body: JSON.stringify(body || {}) }),
  getLatestBenchmark: (): Promise<any> => request('/benchmarks/latest'),
  getScalability: (): Promise<any[]> => request('/benchmarks/scalability'),
};
