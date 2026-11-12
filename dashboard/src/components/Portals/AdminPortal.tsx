import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api/client';
import { RouteMap } from '../Map/RouteMap';
import { LocationPickerMap, PRIORITY_COLORS } from '../Map/LocationPickerMap';
import { vadodaraScenario } from '../../data/vadodara_scenario';
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

  // Delivery Location Picker States
  const [activeCoords, setActiveCoords] = useState<{ lat: number; lon: number } | null>({
    lat: 22.3125,
    lon: 73.1785,
  });
  const [hoveredLocId, setHoveredLocId] = useState<string | null>(null);
  const [selectedLocId, setSelectedLocId] = useState<string | null>(null);
  const [editingLocId, setEditingLocId] = useState<string | null>(null);

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

  const handleSelectCoords = useCallback((coords: { lat: number; lon: number }, address?: string) => {
    setActiveCoords(coords);
    setLocForm((prev) => ({
      ...prev,
      lat: coords.lat,
      lon: coords.lon,
      ...(address ? { address } : {}),
    }));
  }, []);

  const handleQuickAddLocation = useCallback(async (locData: any) => {
    setBusy(true);
    try {
      await api.createLocation(locData);
      setBanner({ type: 'ok', msg: `⚡ Quick Add: Stop '${locData.customer_name}' added to fleet ledger!` });
      await refreshAll();
    } catch (err: any) {
      setBanner({ type: 'err', msg: err.message });
      throw err;
    } finally {
      setBusy(false);
    }
  }, [refreshAll]);

  const handleEditLocation = useCallback((l: any) => {
    setEditingLocId(l.id);
    setLocForm({
      customer_name: l.customer_name,
      customer_phone: l.customer_phone,
      address: l.address,
      lat: l.lat,
      lon: l.lon,
      demand: l.demand,
      priority: l.priority,
      ready_time: l.ready_time,
      due_time: l.due_time,
      service_time: l.service_time,
    });
    setActiveCoords({ lat: l.lat, lon: l.lon });
    setSelectedLocId(l.id);
  }, []);

  const handleCancelEdit = useCallback(() => {
    setEditingLocId(null);
    setLocForm({
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
    setActiveCoords({ lat: 22.3125, lon: 73.1785 });
    setSelectedLocId(null);
  }, []);

  const handleDeleteLocation = useCallback(async (id: string) => {
    setBusy(true);
    try {
      await api.deleteLocation(id);
      if (editingLocId === id) {
        handleCancelEdit();
      }
      setBanner({ type: 'ok', msg: `Delivery stop ${id} deleted.` });
      await refreshAll();
    } catch (err: any) {
      setBanner({ type: 'err', msg: err.message });
    } finally {
      setBusy(false);
    }
  }, [editingLocId, handleCancelEdit, refreshAll]);

  const handleAddLocation = async (e: React.FormEvent) => {
    e.preventDefault();

    if (isNaN(locForm.lat) || isNaN(locForm.lon) || locForm.lat === 0 || locForm.lon === 0) {
      setBanner({ type: 'err', msg: 'Please select a valid location on the map or enter valid coordinates.' });
      return;
    }
    if (locForm.demand <= 0) {
      setBanner({ type: 'err', msg: 'Demand must be greater than 0.' });
      return;
    }
    if (locForm.priority < 1 || locForm.priority > 5) {
      setBanner({ type: 'err', msg: 'Priority must be between 1 and 5.' });
      return;
    }

    // Distance warning (> 100 km from warehouse)
    const depotLat = vadodaraScenario.depot.lat || 22.3072;
    const depotLon = vadodaraScenario.depot.lon || 73.1812;
    const R = 6371;
    const dLat = ((locForm.lat - depotLat) * Math.PI) / 180;
    const dLon = ((locForm.lon - depotLon) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos((depotLat * Math.PI) / 180) *
        Math.cos((locForm.lat * Math.PI) / 180) *
        Math.sin(dLon / 2) ** 2;
    const distKm = Math.round(R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)) * 10) / 10;
    if (distKm > 100) {
      if (!window.confirm(`Notice: This delivery point is ${distKm} km away from the warehouse (> 100 km). Do you still wish to save it?`)) {
        return;
      }
    }

    // Duplicate check
    const duplicate = locations.find(
      (l) =>
        (!editingLocId || l.id !== editingLocId) &&
        Math.abs(l.lat - locForm.lat) < 0.0001 &&
        Math.abs(l.lon - locForm.lon) < 0.0001
    );
    if (duplicate) {
      setBanner({
        type: 'err',
        msg: `A delivery stop (${duplicate.customer_name}) already exists at these exact coordinates.`,
      });
      return;
    }

    setBusy(true);
    try {
      if (editingLocId) {
        await api.updateLocation(editingLocId, locForm);
        setBanner({ type: 'ok', msg: `Delivery location ${editingLocId} updated successfully.` });
        setEditingLocId(null);
      } else {
        await api.createLocation(locForm);
        setBanner({ type: 'ok', msg: 'Delivery location added and saved to fleet ledger.' });
      }
      setLocForm({ ...locForm, customer_name: '', address: '', demand: 10, priority: 1 });
      setActiveCoords(null);
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
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div>
                <h2>Delivery Location Management</h2>
                <p style={{ color: '#94a3b8', fontSize: 13, margin: 0 }}>
                  Visually configure and manage customer drop-offs on the Vadodara GIS network. Click anywhere on the map or search to drop a stop.
                </p>
              </div>
            </div>

            <div className="split-view-grid">
              <form className="card-box form-stack" onSubmit={handleAddLocation}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <h3 style={{ margin: 0 }}>
                    {editingLocId ? `✏️ Edit Customer Stop (${editingLocId})` : 'Add Customer Delivery Stop'}
                  </h3>
                  {editingLocId && (
                    <button
                      type="button"
                      className="btn-xs"
                      onClick={handleCancelEdit}
                      style={{ background: 'rgba(255,255,255,0.1)', color: '#cbd5e1' }}
                    >
                      ✕ Cancel Edit
                    </button>
                  )}
                </div>

                <input
                  required
                  placeholder="Customer / Business Name"
                  className="setting-input full"
                  value={locForm.customer_name}
                  onChange={(e) => setLocForm({ ...locForm, customer_name: e.target.value })}
                />
                <input
                  required
                  placeholder="Phone Number (+91-XXXXXXXXXX)"
                  className="setting-input full"
                  value={locForm.customer_phone}
                  onChange={(e) => setLocForm({ ...locForm, customer_phone: e.target.value })}
                />
                <input
                  required
                  placeholder="Street Address, Vadodara (Auto-filled on map click)"
                  className="setting-input full"
                  value={locForm.address}
                  onChange={(e) => setLocForm({ ...locForm, address: e.target.value })}
                />

                <div className="two-col">
                  <label>
                    Latitude
                    <input
                      type="number"
                      step="0.000001"
                      className="setting-input full"
                      value={locForm.lat}
                      onChange={(e) => {
                        const lat = parseFloat(e.target.value);
                        setLocForm((prev) => ({ ...prev, lat }));
                        if (!isNaN(lat) && !isNaN(locForm.lon)) {
                          setActiveCoords({ lat, lon: locForm.lon });
                        }
                      }}
                    />
                  </label>
                  <label>
                    Longitude
                    <input
                      type="number"
                      step="0.000001"
                      className="setting-input full"
                      value={locForm.lon}
                      onChange={(e) => {
                        const lon = parseFloat(e.target.value);
                        setLocForm((prev) => ({ ...prev, lon }));
                        if (!isNaN(locForm.lat) && !isNaN(lon)) {
                          setActiveCoords({ lat: locForm.lat, lon });
                        }
                      }}
                    />
                  </label>
                </div>

                <div className="two-col">
                  <label>
                    Demand (units)
                    <input
                      type="number"
                      min={1}
                      className="setting-input full"
                      value={locForm.demand}
                      onChange={(e) => setLocForm({ ...locForm, demand: Number(e.target.value) })}
                    />
                  </label>
                  <label>
                    Priority (1=Standard to 5=Critical)
                    <input
                      type="number"
                      min={1}
                      max={5}
                      className="setting-input full"
                      value={locForm.priority}
                      onChange={(e) => setLocForm({ ...locForm, priority: Number(e.target.value) })}
                    />
                  </label>
                </div>

                {/* Interactive Map Picker Embedded in Form */}
                <div style={{ marginTop: 8, marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <label style={{ fontSize: 12, fontWeight: 600, color: '#c7d2fe', display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span>🗺️ Pick Delivery Stop on Map</span>
                      <span style={{ fontSize: 11, color: '#94a3b8', fontWeight: 400 }}>
                        (Click to set pin & geocode • Drag to adjust)
                      </span>
                    </label>
                    {activeCoords && (
                      <span style={{ fontSize: 11, fontFamily: 'monospace', color: '#a5b4fc', background: 'rgba(99, 102, 241, 0.15)', padding: '2px 8px', borderRadius: 4 }}>
                        📍 {activeCoords.lat.toFixed(6)}, {activeCoords.lon.toFixed(6)}
                      </span>
                    )}
                  </div>
                  <LocationPickerMap
                    warehouse={{
                      lat: vadodaraScenario.depot.lat || 22.3072,
                      lon: vadodaraScenario.depot.lon || 73.1812,
                      name: vadodaraScenario.depot.name || 'Vadodara Central Depot (Sayajigunj)',
                    }}
                    savedLocations={locations}
                    activeCoords={activeCoords}
                    onSelectCoords={handleSelectCoords}
                    onQuickAddLocation={handleQuickAddLocation}
                    onEditLocation={handleEditLocation}
                    onDeleteLocation={handleDeleteLocation}
                    hoveredLocationId={hoveredLocId}
                    onHoverLocation={setHoveredLocId}
                    selectedLocationId={selectedLocId}
                    onSelectLocation={setSelectedLocId}
                    height={460}
                  />
                </div>

                <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
                  <button type="submit" className="btn btn-solve" style={{ flex: 1 }} disabled={busy}>
                    {editingLocId ? '💾 Update Location' : '+ Save Location'}
                  </button>
                  {editingLocId && (
                    <button
                      type="button"
                      className="btn"
                      style={{ background: 'rgba(255,255,255,0.1)', color: '#cbd5e1' }}
                      onClick={handleCancelEdit}
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </form>

              <div className="card-box table-scroll">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
                  <h3 style={{ margin: 0 }}>Registered Delivery Stops ({locations.length})</h3>
                  <div style={{ display: 'flex', gap: 8, fontSize: 11, alignItems: 'center' }}>
                    <span style={{ color: '#94a3b8' }}>Priority:</span>
                    {[1, 2, 3, 4, 5].map((p) => (
                      <span key={p} style={{ display: 'inline-flex', alignItems: 'center', gap: 3, color: '#e2e8f0' }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: PRIORITY_COLORS[p] }} />
                        P{p}
                      </span>
                    ))}
                  </div>
                </div>

                <table className="data-table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Customer</th>
                      <th>Address</th>
                      <th>GPS</th>
                      <th>Demand</th>
                      <th>Window</th>
                      <th style={{ textAlign: 'center' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {locations.map((l, idx) => {
                      const code = `C${String(idx + 1).padStart(2, '0')}`;
                      const isHovered = hoveredLocId === l.id;
                      const isSelected = selectedLocId === l.id;
                      const isEditing = editingLocId === l.id;
                      const prioColor = PRIORITY_COLORS[l.priority] || '#6366f1';

                      return (
                        <tr
                          key={l.id}
                          style={{
                            backgroundColor:
                              isEditing
                                ? 'rgba(168, 85, 247, 0.28)'
                                : isSelected || isHovered
                                ? 'rgba(99, 102, 241, 0.2)'
                                : undefined,
                            transition: 'background-color 0.15s ease',
                            cursor: 'pointer',
                          }}
                          onMouseEnter={() => setHoveredLocId(l.id)}
                          onMouseLeave={() => setHoveredLocId(null)}
                          onClick={() => {
                            setSelectedLocId(l.id);
                            setActiveCoords({ lat: l.lat, lon: l.lon });
                          }}
                        >
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <span
                                style={{
                                  background: prioColor,
                                  color: '#fff',
                                  fontSize: 10,
                                  fontWeight: 700,
                                  padding: '1px 5px',
                                  borderRadius: 4,
                                  fontFamily: 'monospace',
                                }}
                              >
                                {code}
                              </span>
                              <span className="mono" style={{ fontSize: 11, color: '#94a3b8' }}>
                                {l.id}
                              </span>
                            </div>
                          </td>
                          <td>
                            <strong>{l.customer_name}</strong>
                            <br />
                            <small style={{ color: '#94a3b8' }}>{l.customer_phone}</small>
                          </td>
                          <td style={{ maxWidth: 200, fontSize: 12 }}>
                            {l.address}
                          </td>
                          <td className="mono" style={{ fontSize: 11 }}>
                            {l.lat.toFixed(5)}, {l.lon.toFixed(5)}
                          </td>
                          <td>
                            <span style={{ fontWeight: 600 }}>{l.demand}</span>
                            <span
                              style={{
                                marginLeft: 6,
                                background: prioColor,
                                color: '#fff',
                                fontSize: 10,
                                padding: '1px 5px',
                                borderRadius: 4,
                                fontWeight: 700,
                              }}
                            >
                              P{l.priority}
                            </span>
                          </td>
                          <td style={{ fontSize: 11 }}>
                            {fmtClock(l.ready_time)}–{fmtClock(l.due_time)}
                          </td>
                          <td>
                            <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                              <button
                                type="button"
                                className="btn-xs"
                                title="Edit stop in form"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleEditLocation(l);
                                }}
                                style={{ background: '#4f46e5', color: '#fff' }}
                              >
                                ✏️
                              </button>
                              <button
                                type="button"
                                className="btn-xs"
                                title="Delete stop"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDeleteLocation(l.id);
                                }}
                                style={{ background: 'rgba(239, 68, 68, 0.2)', color: '#f87171' }}
                              >
                                🗑️
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
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
