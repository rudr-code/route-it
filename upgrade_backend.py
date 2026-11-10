"""Automated Frontend Portal & Vercel Configuration Upgrade Script for Route.it.

Upgrades dashboard/src/ with:
- Environment-aware API & WebSocket configuration (VITE_API_BASE_URL, VITE_WS_BASE_URL)
- Top Portal Switcher (Quantum Fleet Studio IDE | Admin Portal | Driver Cockpit | Customer Tracking)
- Complete Admin Portal (Overview, Locations, Vehicles, Drivers, QPSO Batch Builder, Dispatch, Incidents, Return-to-Hub, History)
- Complete Driver Portal (Login/Selector, Atomic Job Acceptance, Cockpit with Stop 0 Hub, Real Google Maps links, 6-Digit OTP Modal, Failed Delivery)
- Public Customer Tracking Portal (Zero-login token lookup, Live Progress Stepper, ETA, Conditional 6-Digit OTP Reveal)
- Preserves existing LeftPanel, RouteMap, RightPanel, EventControls, and TierBanner without regressions.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
DASH = ROOT / "dashboard"

# ---------------------------------------------------------------------------
# 1. dashboard/src/api/client.ts — Environment-based URL + Full Delivery API
# ---------------------------------------------------------------------------
CLIENT_TS = '''import type {
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
      return `[${status}] Validation error:\\n${msgs.join('\\n')}`;
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
};
'''

# ---------------------------------------------------------------------------
# 2. dashboard/src/api/ws.ts — Production Environment WebSocket Support
# ---------------------------------------------------------------------------
WS_TS = '''import { useEffect, useRef, useCallback } from 'react';
import type { WsMessage } from './types';

type WsHandler = (msg: WsMessage) => void;

export function getWsBaseUrl(): string {
  if (import.meta.env.VITE_WS_BASE_URL) {
    return import.meta.env.VITE_WS_BASE_URL.replace(/\\/$/, '');
  }
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host = window.location.hostname === 'localhost' ? 'localhost:8000' : window.location.host;
  return `${proto}://${host}`;
}

export function useWebSocket(problemId: string | null, onMessage: WsHandler) {
  const wsRef = useRef<WebSocket | null>(null);
  const handlerRef = useRef<WsHandler>(onMessage);
  handlerRef.current = onMessage;

  const connect = useCallback(() => {
    if (!problemId) return;
    const url = `${getWsBaseUrl()}/ws/problems/${problemId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as WsMessage;
        handlerRef.current(msg);
      } catch {}
    };

    ws.onerror = () => console.warn('[WS] connection error');
    ws.onclose = () => {
      wsRef.current = null;
    };
  }, [problemId]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);
}
'''

# ---------------------------------------------------------------------------
# 3. dashboard/src/components/Portals/AdminPortal.tsx
# ---------------------------------------------------------------------------
ADMIN_PORTAL_TSX = '''import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api/client';
import { RouteMap } from '../Map/RouteMap';
import type { GeoJsonFeatureCollection } from '../../api/types';

type AdminTab =
  | 'overview'
  | 'batches'
  | 'locations'
  | 'vehicles'
  | 'drivers'
  | 'dispatch'
  | 'incidents'
  | 'returns'
  | 'history';

interface AdminPortalProps {
  onOpenTracking: (token: string) => void;
}

function fmtClock(sec: number): string {
  const mins = Math.floor(sec / 60);
  const h = Math.floor(mins / 60) % 24;
  const m = mins % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

export function AdminPortal({ onOpenTracking }: AdminPortalProps) {
  const [activeTab, setActiveTab] = useState<AdminTab>('overview');
  const [overview, setOverview] = useState<any>(null);
  const [locations, setLocations] = useState<any[]>([]);
  const [vehicles, setVehicles] = useState<any[]>([]);
  const [drivers, setDrivers] = useState<any[]>([]);
  const [batches, setBatches] = useState<any[]>([]);
  const [dispatchJobs, setDispatchJobs] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);

  const [selectedLocs, setSelectedLocs] = useState<string[]>([]);
  const [selectedVehs, setSelectedVehs] = useState<string[]>([]);
  const [batchName, setBatchName] = useState('Vadodara Express Wave #1');
  const [particles, setParticles] = useState(25);
  const [iters, setIters] = useState(50);
  const [activeBatchGeojson, setActiveBatchGeojson] = useState<GeoJsonFeatureCollection | null>(null);
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);

  const [banner, setBanner] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [busy, setBusy] = useState(false);

  // Forms
  const [locForm, setLocForm] = useState({
    customer_name: '',
    customer_phone: '+91-9825099881',
    address: '',
    lat: 22.3125,
    lon: 73.1785,
    demand: 10,
    priority: 1,
    ready_time: 28800,
    due_time: 50400,
    service_time: 600,
  });

  const [vehForm, setVehForm] = useState({
    registration_number: 'GJ-06-BZ-4040',
    name: 'Tata Ace EV Fleet',
    capacity: 80,
    cost_per_km: 15,
  });

  const [drvForm, setDrvForm] = useState({
    username: '',
    password: 'driver123',
    full_name: '',
    phone: '+91-98250',
    license_number: 'GJ-06-DL-',
    assigned_vehicle_id: 'V_5',
  });

  const refreshAll = useCallback(async () => {
    try {
      const [ov, locs, vehs, drvs, bts, jobs, hist] = await Promise.all([
        api.getOverview(),
        api.listLocations(),
        api.listVehicles(),
        api.listDrivers(),
        api.listBatches(),
        api.listDispatchJobs(),
        api.getHistory(),
      ]);
      setOverview(ov);
      setLocations(locs);
      setVehicles(vehs);
      setDrivers(drvs);
      setBatches(bts);
      setDispatchJobs(jobs);
      setHistory(hist);
      if (selectedLocs.length === 0 && locs.length > 0) {
        setSelectedLocs(locs.slice(0, 8).map((l: any) => l.id));
      }
      if (selectedVehs.length === 0 && vehs.length > 0) {
        setSelectedVehs(vehs.slice(0, 3).map((v: any) => v.id));
      }
      if (!activeBatchId && bts.length > 0) {
        setActiveBatchId(bts[0].id);
        const detail = await api.getBatch(bts[0].id);
        if (detail?.geojson?.features) setActiveBatchGeojson(detail.geojson);
      }
    } catch (e: any) {
      setBanner({ type: 'err', msg: e.message || String(e) });
    }
  }, [selectedLocs.length, selectedVehs.length, activeBatchId]);

  useEffect(() => {
    refreshAll();
  }, []);

  const handleCreateBatchAndOptimize = async () => {
    if (selectedLocs.length === 0 || selectedVehs.length === 0) {
      setBanner({ type: 'err', msg: 'Select at least 1 delivery location and 1 vehicle.' });
      return;
    }
    setBusy(true);
    setBanner(null);
    try {
      const res = await api.optimizeBatch({
        name: batchName,
        location_ids: selectedLocs,
        vehicle_ids: selectedVehs,
        num_particles: particles,
        max_iters: iters,
        seed: 42,
      });
      setActiveBatchGeojson(res.geojson);
      setActiveBatchId(res.batch_id);
      setBanner({
        type: 'ok',
        msg: `Batch ${res.batch_id} optimized via QPSO + Prins Split! Created ${res.dispatch_jobs.length} vehicle routes (${(res.total_distance_m / 1000).toFixed(2)} km).`,
      });
      await refreshAll();
    } catch (e: any) {
      setBanner({ type: 'err', msg: e.message });
    } finally {
      setBusy(false);
    }
  };

  const handleAddLocation = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createLocation(locForm);
      setLocForm({ ...locForm, customer_name: '', address: '' });
      setBanner({ type: 'ok', msg: 'Delivery location added successfully.' });
      await refreshAll();
    } catch (err: any) {
      setBanner({ type: 'err', msg: err.message });
    } finally {
      setBusy(false);
    }
  };

  const handleAddVehicle = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createVehicle(vehForm);
      setBanner({ type: 'ok', msg: 'Vehicle added to fleet.' });
      await refreshAll();
    } catch (err: any) {
      setBanner({ type: 'err', msg: err.message });
    } finally {
      setBusy(false);
    }
  };

  const handleAddDriver = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createDriver(drvForm);
      setBanner({ type: 'ok', msg: `Driver ${drvForm.full_name} registered.` });
      await refreshAll();
    } catch (err: any) {
      setBanner({ type: 'err', msg: err.message });
    } finally {
      setBusy(false);
    }
  };

  const handleTriggerIncident = async (type: 'edge_congestion' | 'road_blockage' | 'vehicle_delay') => {
    const targetBatch = activeBatchId || batches[0]?.id;
    if (!targetBatch) {
      setBanner({ type: 'err', msg: 'Create and optimize a delivery batch first.' });
      return;
    }
    setBusy(true);
    try {
      const res = await api.injectBatchIncident(targetBatch, {
        event_type: type,
        trigger_time: 28800,
        duration: 2400,
        origin_id: 'depot',
        dest_id: selectedLocs[0] || 'C01',
        multiplier: type === 'edge_congestion' ? 2.8 : 999.0,
        delay_seconds: 900,
        description: `Live Admin Incident: ${type.toUpperCase()} on active batch ${targetBatch}`,
      });
      if (res.geojson) setActiveBatchGeojson(res.geojson);
      setBanner({
        type: 'ok',
        msg: `Reoptimized via ${res.tier_selected} in ${res.wall_clock_time_ms.toFixed(1)} ms | Changed stops: ${res.stops_changed_count}`,
      });
      await refreshAll();
    } catch (err: any) {
      setBanner({ type: 'err', msg: err.message });
    } finally {
      setBusy(false);
    }
  };

  const allDeliveries = dispatchJobs.flatMap((j) => j.stops || []);
  const failedDeliveries = allDeliveries.filter(
    (d) => d.status === 'NOT_DELIVERED' || d.status === 'RETURNED_TO_HUB',
  );

  const selectedDemand = locations
    .filter((l) => selectedLocs.includes(l.id))
    .reduce((acc, l) => acc + Number(l.demand), 0);
  const selectedCap = vehicles
    .filter((v) => selectedVehs.includes(v.id))
    .reduce((acc, v) => acc + Number(v.capacity), 0);

  return (
    <div className="portal-shell">
      {/* Sidebar Navigation */}
      <aside className="portal-sidebar glass-panel">
        <div className="sidebar-group-title">Operations Control</div>
        {[
          { id: 'overview', icon: '📊', label: 'Overview & KPIs' },
          { id: 'batches', icon: '⚛', label: 'QPSO Batch Optimizer' },
          { id: 'dispatch', icon: '📡', label: 'Dispatch Management' },
          { id: 'locations', icon: '📍', label: 'Delivery Locations' },
          { id: 'vehicles', icon: '🚛', label: 'Vehicle Fleet' },
          { id: 'drivers', icon: '🪪', label: 'Driver Management' },
          { id: 'incidents', icon: '🚦', label: 'Dynamic Incidents' },
          { id: 'returns', icon: '📦', label: 'Return-to-Hub' },
          { id: 'history', icon: '📜', label: 'Audit & History' },
        ].map((t) => (
          <button
            key={t.id}
            className={`sidebar-nav-btn ${activeTab === t.id ? 'active' : ''}`}
            onClick={() => setActiveTab(t.id as AdminTab)}
          >
            <span>{t.icon}</span>
            <span>{t.label}</span>
          </button>
        ))}
      </aside>

      {/* Main Content Area */}
      <main className="portal-main">
        {banner && (
          <div className={`portal-alert ${banner.type}`}>
            <span>{banner.type === 'ok' ? '✓' : '⚠'} {banner.msg}</span>
            <button onClick={() => setBanner(null)} className="dismiss-btn">✕</button>
          </div>
        )}

        {activeTab === 'overview' && overview && (
          <div className="portal-section">
            <div className="section-header-row">
              <h2>Enterprise Delivery Command Center</h2>
              <button className="btn btn-primary" onClick={refreshAll}>↻ Refresh Live Data</button>
            </div>
            <div className="kpi-grid">
              <div className="kpi-card"><span className="kpi-label">Delivery Batches</span><strong className="kpi-val">{overview.total_batches}</strong></div>
              <div className="kpi-card"><span className="kpi-label">Total Deliveries</span><strong className="kpi-val">{overview.total_deliveries}</strong></div>
              <div className="kpi-card"><span className="kpi-label">Pending Dispatch</span><strong className="kpi-val amber">{overview.pending_deliveries}</strong></div>
              <div className="kpi-card"><span className="kpi-label">Active In-Transit</span><strong className="kpi-val primary">{overview.active_deliveries}</strong></div>
              <div className="kpi-card"><span className="kpi-label">Completed (OTP)</span><strong className="kpi-val emerald">{overview.completed_deliveries}</strong></div>
              <div className="kpi-card"><span className="kpi-label">Failed / Returned</span><strong className="kpi-val red">{overview.failed_deliveries}</strong></div>
              <div className="kpi-card"><span className="kpi-label">Available Vehicles</span><strong className="kpi-val">{overview.available_vehicles} / {overview.total_vehicles}</strong></div>
              <div className="kpi-card"><span className="kpi-label">Active Drivers</span><strong className="kpi-val">{overview.active_drivers}</strong></div>
              <div className="kpi-card"><span className="kpi-label">Optimized Distance</span><strong className="kpi-val">{overview.total_optimized_distance_km} km</strong></div>
              <div className="kpi-card"><span className="kpi-label">Est. Operating Cost</span><strong className="kpi-val">₹{overview.estimated_operating_cost_inr}</strong></div>
            </div>

            <div className="split-view-grid" style={{ marginTop: 18 }}>
              <div className="card-box">
                <h3>Active Optimized Fleet Map (MapLibre GL)</h3>
                <div style={{ height: 360, borderRadius: 10, overflow: 'hidden', marginTop: 10 }}>
                  <RouteMap
                    geojson={activeBatchGeojson}
                    customers={locations}
                    placementMode="idle"
                    onMapClick={() => {}}
                  />
                </div>
              </div>
              <div className="card-box">
                <h3>Recent Delivery Batches</h3>
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr><th>Batch ID</th><th>Name</th><th>Stops</th><th>Dist</th><th>Status</th><th>Action</th></tr>
                    </thead>
                    <tbody>
                      {batches.map((b) => (
                        <tr key={b.id}>
                          <td className="mono">{b.id}</td>
                          <td>{b.name}</td>
                          <td>{b.num_stops}</td>
                          <td>{(b.total_distance_m / 1000).toFixed(1)} km</td>
                          <td><span className="state-pill">{b.status}</span></td>
                          <td>
                            <button
                              className="btn-xs"
                              onClick={async () => {
                                setActiveBatchId(b.id);
                                const d = await api.getBatch(b.id);
                                setActiveBatchGeojson(d.geojson);
                              }}
                            >
                              View Map
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'batches' && (
          <div className="portal-section">
            <h2>Connect Delivery Batches with QPSO + Prins Split</h2>
            <div className="batch-controls-bar card-box">
              <div className="form-inline-grid">
                <label>
                  Batch Name
                  <input className="setting-input" style={{ width: '100%' }} value={batchName} onChange={(e) => setBatchName(e.target.value)} />
                </label>
                <label>
                  QPSO Particles
                  <input type="number" className="setting-input" style={{ width: '100%' }} value={particles} onChange={(e) => setParticles(Number(e.target.value))} />
                </label>
                <label>
                  Max Iterations
                  <input type="number" className="setting-input" style={{ width: '100%' }} value={iters} onChange={(e) => setIters(Number(e.target.value))} />
                </label>
                <div className="capacity-meter">
                  <span>Selected Demand: <strong>{selectedDemand.toFixed(1)}</strong> units</span>
                  <span>Fleet Capacity: <strong style={{ color: selectedDemand <= selectedCap ? '#10b981' : '#ef4444' }}>{selectedCap.toFixed(1)}</strong> units</span>
                </div>
                <button className="btn btn-solve" disabled={busy || selectedDemand > selectedCap} onClick={handleCreateBatchAndOptimize}>
                  {busy ? 'Running QPSO + Prins Split…' : '⚛ Optimize & Create Dispatch Jobs'}
                </button>
              </div>
            </div>

            <div className="split-view-grid" style={{ marginTop: 14 }}>
              <div className="card-box">
                <div className="section-header-row">
                  <h3>1. Select Delivery Locations ({selectedLocs.length})</h3>
                  <div>
                    <button className="btn-xs" onClick={() => setSelectedLocs(locations.map((l) => l.id))}>Select All</button>{' '}
                    <button className="btn-xs" onClick={() => setSelectedLocs([])}>Clear</button>
                  </div>
                </div>
                <div className="table-scroll" style={{ maxHeight: 320 }}>
                  <table className="data-table">
                    <thead>
                      <tr><th></th><th>ID</th><th>Customer</th><th>Demand</th><th>Window</th><th>Priority</th></tr>
                    </thead>
                    <tbody>
                      {locations.map((l) => (
                        <tr key={l.id}>
                          <td>
                            <input
                              type="checkbox"
                              checked={selectedLocs.includes(l.id)}
                              onChange={(e) =>
                                setSelectedLocs((prev) =>
                                  e.target.checked ? [...prev, l.id] : prev.filter((x) => x !== l.id),
                                )
                              }
                            />
                          </td>
                          <td className="mono">{l.id}</td>
                          <td>{l.customer_name}</td>
                          <td>{l.demand}</td>
                          <td>{fmtClock(l.ready_time)}–{fmtClock(l.due_time)}</td>
                          <td>P{l.priority}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="card-box">
                <h3>2. Select Available Vehicles ({selectedVehs.length})</h3>
                <div className="table-scroll" style={{ maxHeight: 320 }}>
                  <table className="data-table">
                    <thead>
                      <tr><th></th><th>ID</th><th>Registration</th><th>Capacity</th><th>Driver</th><th>Status</th></tr>
                    </thead>
                    <tbody>
                      {vehicles.map((v) => (
                        <tr key={v.id}>
                          <td>
                            <input
                              type="checkbox"
                              checked={selectedVehs.includes(v.id)}
                              onChange={(e) =>
                                setSelectedVehs((prev) =>
                                  e.target.checked ? [...prev, v.id] : prev.filter((x) => x !== v.id),
                                )
                              }
                            />
                          </td>
                          <td className="mono">{v.id}</td>
                          <td>{v.registration_number}</td>
                          <td>{v.capacity} units</td>
                          <td>{v.assigned_driver_id || 'Unassigned'}</td>
                          <td><span className="state-pill">{v.status}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'dispatch' && (
          <div className="portal-section">
            <h2>Dispatch Pool & Route Assignments</h2>
            <div className="table-scroll card-box">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Job ID</th>
                    <th>Batch</th>
                    <th>Vehicle</th>
                    <th>Load / Cap</th>
                    <th>Stops</th>
                    <th>Distance</th>
                    <th>Driver Assignment</th>
                    <th>Status</th>
                    <th>Customer Tracking Links</th>
                  </tr>
                </thead>
                <tbody>
                  {dispatchJobs.map((j) => (
                    <tr key={j.id}>
                      <td className="mono">{j.id}</td>
                      <td className="mono">{j.batch_id}</td>
                      <td>{j.vehicle_id}</td>
                      <td>{j.total_load} / {j.vehicle_capacity}</td>
                      <td>{j.stop_count}</td>
                      <td>{(j.planned_distance_m / 1000).toFixed(2)} km</td>
                      <td>
                        <select
                          className="setting-input"
                          style={{ width: 150 }}
                          value={j.driver_id || ''}
                          onChange={async (e) => {
                            if (e.target.value) {
                              await api.assignDriver(j.id, e.target.value);
                              refreshAll();
                            }
                          }}
                        >
                          <option value="">-- Assign Driver --</option>
                          {drivers.map((d) => (
                            <option key={d.id} value={d.id}>{d.full_name} ({d.id})</option>
                          ))}
                        </select>
                      </td>
                      <td><span className="state-pill">{j.status}</span></td>
                      <td>
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                          {(j.stops || []).map((s: any) => (
                            <button
                              key={s.id}
                              className="btn-xs"
                              title={`Track ${s.customer_name}`}
                              onClick={() => onOpenTracking(s.tracking_token)}
                            >
                              🔗 Stop #{s.stop_sequence} ({s.status})
                            </button>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'locations' && (
          <div className="portal-section">
            <h2>Delivery Location Management</h2>
            <div className="split-view-grid">
              <form className="card-box form-stack" onSubmit={handleAddLocation}>
                <h3>Add Customer Delivery Stop</h3>
                <input required placeholder="Customer / Business Name" className="setting-input full" value={locForm.customer_name} onChange={(e) => setLocForm({ ...locForm, customer_name: e.target.value })} />
                <input required placeholder="Phone Number" className="setting-input full" value={locForm.customer_phone} onChange={(e) => setLocForm({ ...locForm, customer_phone: e.target.value })} />
                <input required placeholder="Street Address, Vadodara" className="setting-input full" value={locForm.address} onChange={(e) => setLocForm({ ...locForm, address: e.target.value })} />
                <div className="two-col">
                  <label>Latitude <input type="number" step="0.0001" className="setting-input full" value={locForm.lat} onChange={(e) => setLocForm({ ...locForm, lat: Number(e.target.value) })} /></label>
                  <label>Longitude <input type="number" step="0.0001" className="setting-input full" value={locForm.lon} onChange={(e) => setLocForm({ ...locForm, lon: Number(e.target.value) })} /></label>
                </div>
                <div className="two-col">
                  <label>Demand (units) <input type="number" className="setting-input full" value={locForm.demand} onChange={(e) => setLocForm({ ...locForm, demand: Number(e.target.value) })} /></label>
                  <label>Priority (1-5) <input type="number" min={1} max={5} className="setting-input full" value={locForm.priority} onChange={(e) => setLocForm({ ...locForm, priority: Number(e.target.value) })} /></label>
                </div>
                <button type="submit" className="btn btn-solve" disabled={busy}>+ Save Location</button>
              </form>

              <div className="card-box table-scroll">
                <table className="data-table">
                  <thead>
                    <tr><th>ID</th><th>Customer</th><th>Address</th><th>GPS</th><th>Demand</th><th>Window</th><th></th></tr>
                  </thead>
                  <tbody>
                    {locations.map((l) => (
                      <tr key={l.id}>
                        <td className="mono">{l.id}</td>
                        <td>{l.customer_name}<br /><small>{l.customer_phone}</small></td>
                        <td>{l.address}</td>
                        <td className="mono">{l.lat.toFixed(4)}, {l.lon.toFixed(4)}</td>
                        <td>{l.demand}</td>
                        <td>{fmtClock(l.ready_time)}–{fmtClock(l.due_time)}</td>
                        <td>
                          <button className="btn-xs" onClick={async () => { await api.deleteLocation(l.id); refreshAll(); }}>🗑</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'vehicles' && (
          <div className="portal-section">
            <h2>Fleet Vehicle Management</h2>
            <div className="split-view-grid">
              <form className="card-box form-stack" onSubmit={handleAddVehicle}>
                <h3>Register Fleet Vehicle</h3>
                <input required placeholder="Registration (e.g. GJ-06-AX-1007)" className="setting-input full" value={vehForm.registration_number} onChange={(e) => setVehForm({ ...vehForm, registration_number: e.target.value })} />
                <input required placeholder="Vehicle Model Name" className="setting-input full" value={vehForm.name} onChange={(e) => setVehForm({ ...vehForm, name: e.target.value })} />
                <label>Payload Capacity (Units) <input type="number" className="setting-input full" value={vehForm.capacity} onChange={(e) => setVehForm({ ...vehForm, capacity: Number(e.target.value) })} /></label>
                <button type="submit" className="btn btn-solve" disabled={busy}>+ Add Vehicle</button>
              </form>
              <div className="card-box table-scroll">
                <table className="data-table">
                  <thead><tr><th>ID</th><th>Registration</th><th>Model</th><th>Capacity</th><th>Driver</th><th>Status</th></tr></thead>
                  <tbody>
                    {vehicles.map((v) => (
                      <tr key={v.id}>
                        <td className="mono">{v.id}</td>
                        <td className="mono">{v.registration_number}</td>
                        <td>{v.name}</td>
                        <td>{v.capacity} units</td>
                        <td>{v.assigned_driver_id || '—'}</td>
                        <td><span className="state-pill">{v.status}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'drivers' && (
          <div className="portal-section">
            <h2>Driver Management & Credentials</h2>
            <div className="split-view-grid">
              <form className="card-box form-stack" onSubmit={handleAddDriver}>
                <h3>Register New Driver</h3>
                <input required placeholder="Login Username (e.g. driver5)" className="setting-input full" value={drvForm.username} onChange={(e) => setDrvForm({ ...drvForm, username: e.target.value })} />
                <input required placeholder="Full Name" className="setting-input full" value={drvForm.full_name} onChange={(e) => setDrvForm({ ...drvForm, full_name: e.target.value })} />
                <input required placeholder="Mobile Phone" className="setting-input full" value={drvForm.phone} onChange={(e) => setDrvForm({ ...drvForm, phone: e.target.value })} />
                <input required placeholder="Driving License Number" className="setting-input full" value={drvForm.license_number} onChange={(e) => setDrvForm({ ...drvForm, license_number: e.target.value })} />
                <button type="submit" className="btn btn-solve" disabled={busy}>+ Register Driver</button>
              </form>
              <div className="card-box table-scroll">
                <table className="data-table">
                  <thead><tr><th>Driver ID</th><th>Name</th><th>Phone</th><th>License</th><th>Vehicle</th><th>Completed</th><th>Status</th></tr></thead>
                  <tbody>
                    {drivers.map((d) => (
                      <tr key={d.id}>
                        <td className="mono">{d.id}</td>
                        <td>{d.full_name}</td>
                        <td>{d.phone}</td>
                        <td className="mono">{d.license_number}</td>
                        <td>{d.assigned_vehicle_id || '—'}</td>
                        <td>{d.completed_deliveries}</td>
                        <td><span className="state-pill">{d.status}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'incidents' && (
          <div className="portal-section">
            <h2>Dynamic 3-Tier Incident Reoptimization (Active Batches)</h2>
            <div className="card-box">
              <p style={{ color: 'var(--text-secondary)', marginBottom: 12 }}>
                Inject real-time road disruptions into active delivery batch <strong>{activeBatchId || batches[0]?.id || 'None'}</strong>.
                Completed (`DELIVERED`) and imminent (`ARRIVED`) stops are strictly frozen while uncommitted stops are repaired via Tier 1 (Path Repair), Tier 2 (Local Relocate/Swap), or Tier 3 (QPSO Warm Start).
              </p>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <button className="btn btn-event congestion" disabled={busy} onClick={() => handleTriggerIncident('edge_congestion')}>
                  🚦 Inject Corridor Traffic Congestion (2.8x Slowdown)
                </button>
                <button className="btn btn-event blockage" disabled={busy} onClick={() => handleTriggerIncident('road_blockage')}>
                  🚧 Inject Full Road Blockage (Tier 2/3 Reroute)
                </button>
                <button className="btn btn-primary" disabled={busy} onClick={() => handleTriggerIncident('vehicle_delay')}>
                  ⏱ Inject Vehicle Breakdown / Delay (+15 min)
                </button>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'returns' && (
          <div className="portal-section">
            <h2>Failed Deliveries & Return-to-Hub Verification</h2>
            <div className="card-box table-scroll">
              <table className="data-table">
                <thead>
                  <tr><th>Delivery ID</th><th>Customer</th><th>Vehicle</th><th>Failure Reason</th><th>Status</th><th>Hub Action</th></tr>
                </thead>
                <tbody>
                  {failedDeliveries.length === 0 ? (
                    <tr><td colSpan={6} style={{ textAlign: 'center', padding: 24 }}>No failed or returned packages pending verification.</td></tr>
                  ) : (
                    failedDeliveries.map((d: any) => (
                      <tr key={d.id}>
                        <td className="mono">{d.id}</td>
                        <td>{d.customer_name}</td>
                        <td>{d.vehicle_id}</td>
                        <td style={{ color: '#fca5a5' }}>{d.failure_reason}</td>
                        <td><span className="state-pill">{d.status}</span></td>
                        <td>
                          {d.status === 'NOT_DELIVERED' ? (
                            <button
                              className="btn btn-solve"
                              style={{ padding: '4px 10px', fontSize: 11 }}
                              onClick={async () => {
                                await api.verifyReturnToHub(d.id);
                                setBanner({ type: 'ok', msg: `Package ${d.id} verified as RETURNED_TO_HUB.` });
                                refreshAll();
                              }}
                            >
                              ✓ Verify Return at Hub
                            </button>
                          ) : (
                            <span style={{ color: '#10b981', fontWeight: 600 }}>✓ Hub Verified</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'history' && (
          <div className="portal-section">
            <h2>Immutable System Audit & Delivery History</h2>
            <div className="card-box table-scroll">
              <table className="data-table">
                <thead>
                  <tr><th>Time</th><th>Actor</th><th>Event Type</th><th>Batch / Delivery</th><th>Transition</th><th>Details</th></tr>
                </thead>
                <tbody>
                  {history.map((h) => (
                    <tr key={h.id}>
                      <td className="mono">{new Date(h.timestamp * 1000).toLocaleTimeString()}</td>
                      <td>{h.actor_role} ({h.actor_id})</td>
                      <td className="mono">{h.event_type}</td>
                      <td className="mono">{h.delivery_id || h.batch_id || '—'}</td>
                      <td>{h.old_status ? `${h.old_status} → ${h.new_status}` : '—'}</td>
                      <td>{h.details}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
'''

# ---------------------------------------------------------------------------
# 4. dashboard/src/components/Portals/DriverPortal.tsx
# ---------------------------------------------------------------------------
DRIVER_PORTAL_TSX = '''import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api/client';

interface DriverPortalProps {
  onOpenTracking: (token: string) => void;
}

function fmtEta(sec: number): string {
  const mins = Math.floor(sec / 60);
  const h = Math.floor(mins / 60) % 24;
  const m = mins % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

export function DriverPortal({ onOpenTracking }: DriverPortalProps) {
  const [drivers, setDrivers] = useState<any[]>([]);
  const [selectedDriverId, setSelectedDriverId] = useState<string>('drv_01');
  const [jobs, setJobs] = useState<any[]>([]);
  const [otpInputs, setOtpInputs] = useState<Record<string, string>>({});
  const [failInputs, setFailInputs] = useState<Record<string, string>>({});
  const [banner, setBanner] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const loadDriverData = useCallback(async () => {
    try {
      const [drvs, js] = await Promise.all([
        api.listDrivers(),
        api.listDispatchJobs(selectedDriverId),
      ]);
      setDrivers(drvs);
      setJobs(js);
    } catch (e: any) {
      setBanner({ type: 'err', msg: e.message });
    }
  }, [selectedDriverId]);

  useEffect(() => {
    loadDriverData();
  }, [loadDriverData]);

  const currentDriver = drivers.find((d) => d.id === selectedDriverId) || drivers[0];
  const availableJobs = jobs.filter((j) => j.status === 'PENDING_DISPATCH' || j.status === 'ASSIGNED');
  const activeJobs = jobs.filter((j) => j.status === 'ACCEPTED' || j.status === 'IN_TRANSIT' || j.status === 'DELIVERED');

  const handleAcceptJob = async (jobId: string) => {
    setBusy(true);
    setBanner(null);
    try {
      await api.acceptJob(jobId, selectedDriverId);
      setBanner({ type: 'ok', msg: `Job ${jobId} accepted atomically! Driver Cockpit unlocked.` });
      await loadDriverData();
    } catch (e: any) {
      setBanner({ type: 'err', msg: e.message });
    } finally {
      setBusy(false);
    }
  };

  const handleProgress = async (deliveryId: string, st: 'IN_TRANSIT' | 'ARRIVED') => {
    setBusy(true);
    try {
      await api.updateDeliveryProgress(deliveryId, st);
      setBanner({ type: 'ok', msg: `Stop ${deliveryId} marked ${st}. Customer notified.` });
      await loadDriverData();
    } catch (e: any) {
      setBanner({ type: 'err', msg: e.message });
    } finally {
      setBusy(false);
    }
  };

  const handleVerifyOtp = async (deliveryId: string) => {
    const code = (otpInputs[deliveryId] || '').trim();
    if (code.length !== 6) {
      setBanner({ type: 'err', msg: 'Please enter the 6-digit OTP provided by the customer.' });
      return;
    }
    setBusy(true);
    try {
      const res = await api.verifyOtp(deliveryId, code, selectedDriverId);
      setBanner({ type: 'ok', msg: res.message });
      await loadDriverData();
    } catch (e: any) {
      setBanner({ type: 'err', msg: e.message });
    } finally {
      setBusy(false);
    }
  };

  const handleFailDelivery = async (deliveryId: string) => {
    const reason = (failInputs[deliveryId] || 'Customer unavailable at address').trim();
    setBusy(true);
    try {
      await api.failDelivery(deliveryId, reason, selectedDriverId);
      setBanner({ type: 'ok', msg: `Stop ${deliveryId} marked NOT_DELIVERED and queued for Return-to-Hub.` });
      await loadDriverData();
    } catch (e: any) {
      setBanner({ type: 'err', msg: e.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="portal-main" style={{ padding: 20, overflowY: 'auto', height: 'calc(100vh - 54px)' }}>
      {/* Driver Header Bar */}
      <div className="card-box" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <h2>🚚 Driver Cockpit & Route Execution Portal</h2>
          {currentDriver && (
            <div style={{ color: 'var(--text-secondary)', fontSize: 12, marginTop: 4 }}>
              Driver: <strong>{currentDriver.full_name}</strong> ({currentDriver.id}) · License: <span className="mono">{currentDriver.license_number}</span> · Assigned Vehicle: <strong className="mono">{currentDriver.assigned_vehicle_id || 'V_1'}</strong> · Completed: <strong>{currentDriver.completed_deliveries}</strong>
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Active Driver Session:</span>
          <select
            className="setting-input"
            style={{ width: 210 }}
            value={selectedDriverId}
            onChange={(e) => setSelectedDriverId(e.target.value)}
          >
            {drivers.map((d) => (
              <option key={d.id} value={d.id}>{d.full_name} ({d.assigned_vehicle_id || d.id})</option>
            ))}
          </select>
          <button className="btn btn-primary" onClick={loadDriverData}>↻ Sync</button>
        </div>
      </div>

      {banner && (
        <div className={`portal-alert ${banner.type}`} style={{ marginBottom: 16 }}>
          <span>{banner.type === 'ok' ? '✓' : '⚠'} {banner.msg}</span>
          <button onClick={() => setBanner(null)} className="dismiss-btn">✕</button>
        </div>
      )}

      {/* Available Dispatch Jobs to Accept */}
      <div className="card-box" style={{ marginBottom: 18 }}>
        <h3>1. Available Delivery Batches (Atomic Job Acceptance Pool)</h3>
        {availableJobs.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', marginTop: 8 }}>No unaccepted jobs waiting in the dispatch pool.</p>
        ) : (
          <div className="kpi-grid" style={{ marginTop: 10 }}>
            {availableJobs.map((j) => (
              <div key={j.id} className="kpi-card" style={{ borderLeft: `4px solid ${j.route_color || '#6366f1'}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <strong className="mono">{j.id}</strong>
                  <span className="state-pill">{j.status}</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>
                  <div>Vehicle: <strong>{j.vehicle_id}</strong> ({j.total_load} / {j.vehicle_capacity} units)</div>
                  <div>Stops: <strong>{j.stop_count}</strong> · Distance: <strong>{(j.planned_distance_m / 1000).toFixed(2)} km</strong></div>
                </div>
                <button
                  className="btn btn-solve"
                  style={{ marginTop: 10, width: '100%' }}
                  disabled={busy}
                  onClick={() => handleAcceptJob(j.id)}
                >
                  ✓ Accept Delivery Job
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Active Driver Cockpit */}
      <div className="card-box">
        <h3>2. Active Driver Cockpit — Turn-by-Turn Sequence & 6-Digit OTP Verification</h3>
        {activeJobs.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', marginTop: 8 }}>Accept a delivery batch above to launch your active route cockpit.</p>
        ) : (
          activeJobs.map((job) => (
            <div key={job.id} style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border-glass)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <div>
                  <strong style={{ fontSize: 14 }}>Route Job {job.id}</strong> · Vehicle <span className="mono">{job.vehicle_id}</span> · Load {job.total_load}/{job.vehicle_capacity} units
                </div>
                <span className="state-pill">{job.status}</span>
              </div>

              {/* Stop Zero: Central Distribution Hub */}
              <div className="cockpit-stop-card hub">
                <div>
                  <span className="stop-badge">STOP 0 · CENTRAL HUB</span>
                  <h4>Vadodara Central Distribution Hub (Sayajigunj)</h4>
                  <p>GPS: 22.3072, 73.1812 · Departure Origin & Return Hub</p>
                </div>
                <a
                  href="https://www.google.com/maps/dir/?api=1&destination=22.3072,73.1812&travelmode=driving"
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-primary"
                >
                  🧭 Navigate to Hub (Google Maps)
                </a>
              </div>

              {/* Ordered Customer Stops */}
              {(job.stops || []).map((s: any) => {
                const gmapsUrl = `https://www.google.com/maps/dir/?api=1&destination=${s.lat},${s.lon}&travelmode=driving`;
                return (
                  <div key={s.id} className={`cockpit-stop-card ${s.status.toLowerCase()}`}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <span className="stop-badge">STOP #{s.stop_sequence}</span>
                        <span className="mono" style={{ fontSize: 11 }}>{s.id}</span>
                        <span className="state-pill">{s.status}</span>
                        <span style={{ fontSize: 11, color: 'var(--amber)' }}>ETA {fmtEta(s.eta_seconds)}</span>
                      </div>
                      <h4 style={{ marginTop: 4 }}>{s.customer_name} ({s.customer_phone})</h4>
                      <p style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                        {s.address} · GPS: {s.lat.toFixed(4)}, {s.lon.toFixed(4)} · Demand: {s.demand} units
                      </p>
                      <div style={{ marginTop: 6, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <a href={gmapsUrl} target="_blank" rel="noreferrer" className="btn-xs" style={{ textDecoration: 'none' }}>
                          🗺 Open Google Maps Navigation
                        </a>
                        <button className="btn-xs" onClick={() => onOpenTracking(s.tracking_token)}>
                          👁 Preview Customer Tracking Portal (Get OTP)
                        </button>
                      </div>
                    </div>

                    {/* Action Controls */}
                    {s.status !== 'DELIVERED' && s.status !== 'NOT_DELIVERED' && s.status !== 'RETURNED_TO_HUB' && (
                      <div className="cockpit-actions">
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button
                            className="btn btn-primary"
                            disabled={busy || s.status === 'IN_TRANSIT' || s.status === 'ARRIVED'}
                            onClick={() => handleProgress(s.id, 'IN_TRANSIT')}
                          >
                            🚚 Start Transit
                          </button>
                          <button
                            className="btn btn-primary"
                            disabled={busy || s.status === 'ARRIVED'}
                            onClick={() => handleProgress(s.id, 'ARRIVED')}
                          >
                            📍 Mark Arrived
                          </button>
                        </div>

                        <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                          <input
                            type="text"
                            maxLength={6}
                            placeholder="6-Digit OTP"
                            className="setting-input"
                            style={{ width: 110, textAlign: 'center', letterSpacing: 2 }}
                            value={otpInputs[s.id] || ''}
                            onChange={(e) => setOtpInputs({ ...otpInputs, [s.id]: e.target.value })}
                          />
                          <button className="btn btn-solve" disabled={busy} onClick={() => handleVerifyOtp(s.id)}>
                            🔐 Verify OTP
                          </button>
                        </div>

                        <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                          <select
                            className="setting-input"
                            style={{ width: 150 }}
                            value={failInputs[s.id] || 'Customer unavailable'}
                            onChange={(e) => setFailInputs({ ...failInputs, [s.id]: e.target.value })}
                          >
                            <option value="Customer unavailable">Customer unavailable</option>
                            <option value="Address unreachable / closed">Address unreachable</option>
                            <option value="Customer refused delivery">Customer refused</option>
                          </select>
                          <button className="btn btn-event blockage" disabled={busy} onClick={() => handleFailDelivery(s.id)}>
                            ✕ Not Delivered
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
'''

# ---------------------------------------------------------------------------
# 5. dashboard/src/components/Portals/CustomerPortal.tsx
# ---------------------------------------------------------------------------
CUSTOMER_PORTAL_TSX = '''import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api/client';
import { useWebSocket } from '../../api/ws';

interface CustomerPortalProps {
  initialToken: string;
}

const STEPS = ['ASSIGNED', 'ACCEPTED', 'IN_TRANSIT', 'ARRIVED', 'DELIVERED'];

function fmtEta(sec: number): string {
  const mins = Math.floor(sec / 60);
  const h = Math.floor(mins / 60) % 24;
  const m = mins % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

export function CustomerPortal({ initialToken }: CustomerPortalProps) {
  const [tokenInput, setTokenInput] = useState(initialToken);
  const [activeToken, setActiveToken] = useState(initialToken);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialToken) {
      setTokenInput(initialToken);
      setActiveToken(initialToken);
    }
  }, [initialToken]);

  const fetchTracking = useCallback(async (tk: string) => {
    if (!tk.trim()) return;
    try {
      const res = await api.trackDelivery(tk.trim());
      setData(res);
      setError(null);
    } catch (e: any) {
      setError(e.message || 'Could not find delivery for this tracking token.');
      setData(null);
    }
  }, []);

  useEffect(() => {
    if (activeToken) {
      fetchTracking(activeToken);
      const timer = setInterval(() => fetchTracking(activeToken), 5000);
      return () => clearInterval(timer);
    }
  }, [activeToken, fetchTracking]);

  // Real-time WebSocket updates on the batch channel
  useWebSocket(data?.batch_id ?? null, () => {
    if (activeToken) fetchTracking(activeToken);
  });

  const currentStepIdx = data ? STEPS.indexOf(data.status) : -1;

  return (
    <div className="portal-main" style={{ padding: 24, maxWidth: 820, margin: '0 auto', overflowY: 'auto', height: 'calc(100vh - 54px)' }}>
      <div className="card-box" style={{ marginBottom: 18 }}>
        <h2>📦 Public Customer Live Delivery Tracking</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: 12, marginTop: 4 }}>
          No account login required. Enter your secure cryptographic Tracking Token to view real-time ETA and your 6-digit Delivery Verification OTP.
        </p>
        <form
          style={{ display: 'flex', gap: 10, marginTop: 12 }}
          onSubmit={(e) => {
            e.preventDefault();
            setActiveToken(tokenInput);
          }}
        >
          <input
            className="setting-input"
            style={{ flex: 1, textAlign: 'left', padding: '8px 12px' }}
            placeholder="Paste secure tracking token..."
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
          />
          <button type="submit" className="btn btn-solve">Track Package</button>
        </form>
      </div>

      {error && <div className="portal-alert err">⚠ {error}</div>}

      {data && (
        <div className="card-box">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Delivery ID: {data.delivery_id}</span>
              <h3 style={{ fontSize: 18, marginTop: 2 }}>{data.customer_name}</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{data.address}</p>
            </div>
            <span className="state-pill" style={{ fontSize: 14, padding: '6px 14px' }}>{data.status}</span>
          </div>

          {/* Progress Stepper */}
          <div className="tracking-stepper">
            {STEPS.map((st, idx) => {
              const done = currentStepIdx >= idx || data.status === 'DELIVERED';
              return (
                <div key={st} className={`step-node ${done ? 'done' : ''}`}>
                  <div className="step-circle">{done ? '✓' : idx + 1}</div>
                  <span>{st.replace('_', ' ')}</span>
                </div>
              );
            })}
          </div>

          <div className="kpi-grid" style={{ marginTop: 16 }}>
            <div className="kpi-card">
              <span className="kpi-label">Estimated Arrival (ETA)</span>
              <strong className="kpi-val">{fmtEta(data.eta_seconds)}</strong>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">Remaining Stops Ahead</span>
              <strong className="kpi-val">{data.remaining_stops_ahead} stops</strong>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">Assigned Driver</span>
              <strong className="kpi-val" style={{ fontSize: 14 }}>{data.driver?.name || 'Assigning…'}</strong>
              <small style={{ color: 'var(--text-secondary)' }}>{data.driver?.phone || ''}</small>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">Assigned Vehicle</span>
              <strong className="kpi-val" style={{ fontSize: 14 }}>{data.vehicle?.registration_number || '—'}</strong>
              <small style={{ color: 'var(--text-secondary)' }}>{data.vehicle?.name || ''}</small>
            </div>
          </div>

          {/* Conditional Six-Digit OTP Card */}
          {data.otp_code && (
            <div className="otp-reveal-box">
              <div>
                <span className="otp-tag">🔐 SECURE SIX-DIGIT DELIVERY OTP</span>
                <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                  Share this one-time verification code with your driver upon arrival to confirm delivery:
                </p>
              </div>
              <div className="otp-digits">{data.otp_code}</div>
            </div>
          )}

          {data.status === 'DELIVERED' && (
            <div className="portal-alert ok" style={{ marginTop: 16 }}>
              ✓ Package verified via 6-digit OTP and delivered at {new Date(data.delivered_at * 1000).toLocaleTimeString()}.
            </div>
          )}

          {(data.status === 'NOT_DELIVERED' || data.status === 'RETURNED_TO_HUB') && (
            <div className="portal-alert err" style={{ marginTop: 16 }}>
              ⚠ Delivery Attempt Failed: {data.failure_reason} (Status: {data.status})
            </div>
          )}
        </div>
      )}
    </div>
  );
}
'''

# ---------------------------------------------------------------------------
# 6. dashboard/src/App.tsx — Unified Multi-Portal Navigation + Original Studio
# ---------------------------------------------------------------------------
APP_TSX = '''import { useCallback, useState } from 'react';
import { useSolver } from './hooks/useSolver';
import { useEvents } from './hooks/useEvents';
import { LeftPanel } from './components/LeftPanel/LeftPanel';
import { RouteMap } from './components/Map/RouteMap';
import { RightPanel } from './components/RightPanel/RightPanel';
import { EventControls } from './components/EventControls/EventControls';
import { TierBanner } from './components/EventControls/TierBanner';
import { AdminPortal } from './components/Portals/AdminPortal';
import { DriverPortal } from './components/Portals/DriverPortal';
import { CustomerPortal } from './components/Portals/CustomerPortal';
import { vadodaraScenario } from './data/vadodara_scenario';
import type { SolutionResponse } from './api/types';

type ActivePortal = 'studio' | 'admin' | 'driver' | 'customer';

export default function App() {
  const [activePortal, setActivePortal] = useState<ActivePortal>('studio');
  const [trackingToken, setTrackingToken] = useState<string>('');

  const [solverState, solverActions] = useSolver();
  const [eventState, eventActions] = useEvents();
  const [toggleMode, setToggleMode] = useState<'current' | 'previous'>('current');
  const [previousSolution, setPreviousSolution] = useState<SolutionResponse | null>(null);

  const handleNewSolution = useCallback((sol: SolutionResponse) => {
    solverActions.setSolution(sol);
  }, [solverActions]);

  const handleMapClick = useCallback((lat: number, lon: number) => {
    if (eventState.placementMode === 'idle') return;
    if (!solverState.problemId) return;

    if (solverState.solution) {
      setPreviousSolution(solverState.solution);
    }

    eventActions.injectAtPoint(
      solverState.problemId,
      lat,
      lon,
      vadodaraScenario.customers,
      handleNewSolution,
    );
  }, [
    eventState.placementMode,
    solverState.problemId,
    solverState.solution,
    eventActions,
    handleNewSolution,
  ]);

  const handleOpenTracking = useCallback((token: string) => {
    setTrackingToken(token);
    setActivePortal('customer');
  }, []);

  const showToggle = !!previousSolution && !!solverState.solution;

  return (
    <div className="master-shell">
      {/* Top Global Portal Navigation Bar */}
      <header className="top-portal-bar">
        <div className="top-brand">
          <span className="logo-icon">⚛</span>
          <strong>Route<span className="logo-dot">.it</span></strong>
          <span className="top-tag">SIH 2026 · PS SIH26137 · Quantum-Inspired Intelligent Delivery System</span>
        </div>

        <nav className="top-portal-tabs">
          <button
            className={`portal-tab-btn ${activePortal === 'studio' ? 'active' : ''}`}
            onClick={() => setActivePortal('studio')}
          >
            ⚛ Quantum Fleet Studio (Live IDE)
          </button>
          <button
            className={`portal-tab-btn ${activePortal === 'admin' ? 'active' : ''}`}
            onClick={() => setActivePortal('admin')}
          >
            🛡️ Admin Portal
          </button>
          <button
            className={`portal-tab-btn ${activePortal === 'driver' ? 'active' : ''}`}
            onClick={() => setActivePortal('driver')}
          >
            🚚 Driver Cockpit
          </button>
          <button
            className={`portal-tab-btn ${activePortal === 'customer' ? 'active' : ''}`}
            onClick={() => setActivePortal('customer')}
          >
            📦 Customer Tracking
          </button>
        </nav>
      </header>

      {/* Portal 1: Original Quantum Fleet Studio (Preserved 100%) */}
      {activePortal === 'studio' && (
        <div className="app-layout" style={{ height: 'calc(100vh - 54px)' }}>
          <LeftPanel
            solverState={solverState}
            convergence={solverState.convergence}
            onLoadScenario={solverActions.loadScenario}
            onSolve={solverActions.solve}
          />

          <div className="map-area">
            <div className="map-toolbar">
              <EventControls
                placementMode={eventState.placementMode}
                isInjecting={eventState.isInjecting}
                hasSolution={!!solverState.solution}
                onStartCongestion={() => eventActions.startPlacement('congestion')}
                onStartBlockage={() => eventActions.startPlacement('blockage')}
                onCancel={eventActions.cancelPlacement}
              />
            </div>

            {eventState.lastResult && (
              <TierBanner result={eventState.lastResult} onDismiss={eventActions.dismiss} />
            )}

            {eventState.isInjecting && (
              <div className="injecting-overlay">
                <span className="spinner-lg" /> Re-optimizing routes…
              </div>
            )}

            {eventState.error && (
              <div className="error-banner">⚠ {eventState.error}</div>
            )}

            <RouteMap
              geojson={
                toggleMode === 'previous'
                  ? (previousSolution?.geojson ?? null)
                  : (solverState.solution?.geojson ?? null)
              }
              customers={vadodaraScenario.customers}
              placementMode={eventState.placementMode}
              onMapClick={handleMapClick}
              showBeforeAfter={toggleMode}
              previousGeojson={previousSolution?.geojson ?? null}
            />
          </div>

          <RightPanel
            routes={
              (toggleMode === 'previous'
                ? previousSolution?.routes
                : solverState.solution?.routes) ?? []
            }
            customers={vadodaraScenario.customers}
            oracleType={solverState.oracleType}
            valhallaConnected={solverState.valhallaConnected}
            showToggle={showToggle}
            toggleMode={toggleMode}
            onToggle={() =>
              setToggleMode((m) => (m === 'current' ? 'previous' : 'current'))
            }
          />
        </div>
      )}

      {/* Portal 2: Complete Admin Portal */}
      {activePortal === 'admin' && <AdminPortal onOpenTracking={handleOpenTracking} />}

      {/* Portal 3: Dedicated Driver Cockpit */}
      {activePortal === 'driver' && <DriverPortal onOpenTracking={handleOpenTracking} />}

      {/* Portal 4: Public Customer Tracking Portal */}
      {activePortal === 'customer' && <CustomerPortal initialToken={trackingToken} />}
    </div>
  );
}
'''

# ---------------------------------------------------------------------------
# 7. Append Portal Styles to dashboard/src/index.css & Add vercel.json
# ---------------------------------------------------------------------------
PORTAL_CSS_APPEND = '''
/* ======= Multi-Portal Top Navigation & Enterprise Delivery Portals ======= */
.master-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background: var(--bg-base);
}

.top-portal-bar {
  height: 54px;
  background: rgba(8, 10, 28, 0.95);
  border-bottom: 1px solid var(--border-glass-strong);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  flex-shrink: 0;
  z-index: 50;
}

.top-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
}

.top-tag {
  font-size: 11px;
  color: var(--text-muted);
  border-left: 1px solid var(--border-glass);
  padding-left: 10px;
}

.top-portal-tabs {
  display: flex;
  gap: 8px;
}

.portal-tab-btn {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border-glass);
  color: var(--text-secondary);
  padding: 6px 14px;
  border-radius: var(--radius-md);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.portal-tab-btn:hover {
  color: var(--text-primary);
  border-color: var(--primary);
}
.portal-tab-btn.active {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.25), rgba(139, 92, 246, 0.25));
  border-color: var(--primary);
  color: white;
  box-shadow: 0 0 12px rgba(99, 102, 241, 0.3);
}

.portal-shell {
  display: grid;
  grid-template-columns: 240px 1fr;
  height: calc(100vh - 54px);
}

.portal-sidebar {
  padding: 14px 10px;
  gap: 6px;
}

.sidebar-group-title {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--text-muted);
  padding: 4px 10px 8px;
  font-weight: 700;
}

.sidebar-nav-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  text-align: left;
}
.sidebar-nav-btn:hover {
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-primary);
}
.sidebar-nav-btn.active {
  background: var(--primary-dim);
  border-color: var(--border-glass-strong);
  color: var(--primary-light);
  font-weight: 600;
}

.portal-main {
  padding: 20px;
  overflow-y: auto;
}

.portal-section {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.section-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}

.kpi-card {
  background: rgba(15, 18, 42, 0.8);
  border: 1px solid var(--border-glass);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.kpi-label {
  font-size: 11px;
  color: var(--text-secondary);
}
.kpi-val {
  font-size: 20px;
  font-family: var(--font-mono);
  color: var(--text-primary);
}
.kpi-val.emerald { color: var(--emerald); }
.kpi-val.amber { color: var(--amber); }
.kpi-val.red { color: var(--red); }
.kpi-val.primary { color: var(--primary-light); }

.card-box {
  background: rgba(15, 18, 42, 0.75);
  border: 1px solid var(--border-glass);
  border-radius: var(--radius-md);
  padding: 16px;
}

.split-view-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.table-scroll {
  overflow-x: auto;
  overflow-y: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.data-table th, .data-table td {
  padding: 8px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  text-align: left;
}
.data-table th {
  color: var(--text-muted);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.mono { font-family: var(--font-mono); }

.state-pill {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 10px;
  font-weight: 700;
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(99, 102, 241, 0.35);
  color: var(--primary-light);
}

.btn-xs {
  padding: 3px 8px;
  font-size: 11px;
  border-radius: 6px;
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(99, 102, 241, 0.35);
  color: var(--primary-light);
  cursor: pointer;
}

.portal-alert {
  padding: 10px 14px;
  border-radius: var(--radius-md);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
.portal-alert.ok {
  background: rgba(16, 185, 129, 0.15);
  border: 1px solid rgba(16, 185, 129, 0.4);
  color: #6ee7b7;
}
.portal-alert.err {
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.4);
  color: #fca5a5;
}

.form-inline-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
  align-items: end;
}

.form-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.setting-input.full {
  width: 100%;
  text-align: left;
  padding: 7px 10px;
}
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.cockpit-stop-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border-glass);
  border-radius: var(--radius-md);
  padding: 12px 16px;
  margin-bottom: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.cockpit-stop-card.hub {
  border-left: 4px solid var(--primary);
  background: rgba(99, 102, 241, 0.08);
}
.cockpit-stop-card.delivered {
  border-left: 4px solid var(--emerald);
  opacity: 0.8;
}
.stop-badge {
  background: var(--primary-dim);
  color: var(--primary-light);
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 4px;
}

.tracking-stepper {
  display: flex;
  justify-content: space-between;
  margin: 22px 0;
  position: relative;
}
.step-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-muted);
}
.step-node.done { color: var(--emerald); font-weight: 600; }
.step-circle {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2px solid var(--border-glass-strong);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-surface);
}
.step-node.done .step-circle {
  background: rgba(16, 185, 129, 0.2);
  border-color: var(--emerald);
}

.otp-reveal-box {
  margin-top: 18px;
  padding: 16px 20px;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.18), rgba(16, 185, 129, 0.15));
  border: 1px solid var(--primary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.otp-tag {
  font-size: 11px;
  font-weight: 700;
  color: var(--emerald);
  letter-spacing: 0.08em;
}
.otp-digits {
  font-family: var(--font-mono);
  font-size: 28px;
  font-weight: 800;
  letter-spacing: 6px;
  color: white;
  background: rgba(5, 7, 26, 0.8);
  padding: 8px 18px;
  border-radius: 8px;
  border: 1px solid var(--border-glass-strong);
}
'''

VERCEL_JSON = '''{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "framework": "vite",
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
'''


def main() -> None:
    portals_dir = DASH / "src" / "components" / "Portals"
    portals_dir.mkdir(parents=True, exist_ok=True)

    (DASH / "src" / "api" / "client.ts").write_text(CLIENT_TS, encoding="utf-8")
    (DASH / "src" / "api" / "ws.ts").write_text(WS_TS, encoding="utf-8")
    (portals_dir / "AdminPortal.tsx").write_text(ADMIN_PORTAL_TSX, encoding="utf-8")
    (portals_dir / "DriverPortal.tsx").write_text(DRIVER_PORTAL_TSX, encoding="utf-8")
    (portals_dir / "CustomerPortal.tsx").write_text(CUSTOMER_PORTAL_TSX, encoding="utf-8")
    (DASH / "src" / "App.tsx").write_text(APP_TSX, encoding="utf-8")
    (DASH / "vercel.json").write_text(VERCEL_JSON, encoding="utf-8")

    css_path = DASH / "src" / "index.css"
    existing_css = css_path.read_text(encoding="utf-8")
    if ".master-shell" not in existing_css:
        css_path.write_text(existing_css + "\n" + PORTAL_CSS_APPEND, encoding="utf-8")

    print("[SUCCESS] Frontend portals and Vercel configuration written successfully!")


if __name__ == "__main__":
    main()