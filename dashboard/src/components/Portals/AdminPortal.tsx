import { useState, useEffect, useCallback } from 'react';
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
