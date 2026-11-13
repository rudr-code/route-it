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
    delivery_instructions: '',
    time_window_type: 'hard' as 'hard' | 'soft',
  });
  const [locationConfirmed, setLocationConfirmed] = useState(false);

  // Enterprise Financial Cost Configuration (R9, R21, AC-10)
  const [costConfig, setCostConfig] = useState({
    cost_per_km: 8.0,
    cost_per_hour: 100.0,
    vehicle_activation_cost: 300.0,
    critical_sla_rate: 10.0,
    standard_sla_rate: 5.0,
    flexible_sla_rate: 2.0,
  });

  // Advanced Planning & Profiles (R16, R18, R19, R24)
  const [planningMode, setPlanningMode] = useState<'complete' | 'partial'>('complete');
  const [optimizationProfile, setOptimizationProfile] = useState<'cost_focused' | 'balanced' | 'driver_productivity'>('cost_focused');
  const [fleetMode, setFleetMode] = useState<'auto' | 'target'>('auto');
  const [targetFleetSize, setTargetFleetSize] = useState<number>(4);
  const [depotReturn, setDepotReturn] = useState<boolean>(true);
  const [lastBatchResult, setLastBatchResult] = useState<any>(null);

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

  const handleExportCsv = (batch: any, jobs: any[]) => {
    if (!batch) return;
    const rows = [
      ['Route ID', 'Vehicle ID', 'Driver ID', 'Stop Seq', 'Delivery ID', 'Customer Name', 'Phone', 'Address', 'Latitude', 'Longitude', 'Demand', 'ETA (seconds)', 'ETA Clock', 'Window', 'Status']
    ];
    jobs.forEach((job) => {
      (job.stops || []).forEach((st: any) => {
        rows.push([
          job.id,
          job.vehicle_id,
          job.driver_id || 'Unassigned',
          String(st.stop_sequence),
          st.id,
          `"${(st.customer_name || '').replace(/"/g, '""')}"`,
          st.customer_phone || '',
          `"${(st.address || '').replace(/"/g, '""')}"`,
          String(st.lat),
          String(st.lon),
          String(st.demand),
          String(st.eta_seconds),
          fmtClock(st.eta_seconds || 0),
          `${fmtClock(st.ready_time || 0)} - ${fmtClock(st.due_time || 0)}`,
          st.status || 'OPTIMIZED'
        ]);
      });
    });
    const csvContent = 'data:text/csv;charset=utf-8,' + rows.map((e) => e.join(',')).join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `${batch.id || 'route_plan'}_manifest.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleExportJson = (batch: any) => {
    if (!batch) return;
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(batch, null, 2));
    const link = document.createElement('a');
    link.setAttribute('href', dataStr);
    link.setAttribute('download', `${batch.id || 'route_plan'}.json`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

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
        planning_mode: planningMode,
        optimization_profile: optimizationProfile,
        fleet_mode: fleetMode,
        target_fleet_size: fleetMode === 'target' ? targetFleetSize : undefined,
        depot_return: depotReturn,
        cost_per_km: costConfig.cost_per_km,
        cost_per_hour: costConfig.cost_per_hour,
        vehicle_activation_cost: costConfig.vehicle_activation_cost,
      });
      setLastBatchResult(res);
      setActiveBatchGeojson(res.geojson);
      setActiveBatchId(res.batch_id);
      setBanner({
        type: 'ok',
        msg: `Batch ${res.batch_id} optimized via QPSO + Prins Split! ${res.dispatch_jobs.length} routes (${(res.total_distance_m / 1000).toFixed(2)} km). ${res.status_message || ''}`,
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
      delivery_instructions: l.delivery_instructions || '',
      time_window_type: (l.time_window_type as 'hard' | 'soft') || 'hard',
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
      delivery_instructions: '',
      time_window_type: 'hard',
    });
    setLocationConfirmed(false);
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
                <button className="btn btn-solve" disabled={busy || (planningMode === 'complete' && selectedDemand > selectedCap)} onClick={handleCreateBatchAndOptimize}>
                  {busy ? 'Running QPSO + Prins Split…' : '⚛ Optimize & Create Dispatch Jobs'}
                </button>
              </div>
            </div>

            {/* Enterprise Cost Configuration & Optimization Profiles Bar (R9, R16, R18, R19, R21, R24) */}
            <div className="card-box" style={{ marginTop: 10, background: 'rgba(30, 41, 59, 0.7)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: '#38bdf8' }}>⚙️ Enterprise Cost Parameters & Optimization Profiles (R9, R16, R18, R19, R21, R24)</span>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    className="btn-xs"
                    onClick={() => {
                      const activeBatch = batches.find((b) => b.id === activeBatchId) || lastBatchResult;
                      handleExportCsv(activeBatch, dispatchJobs.filter((j) => j.batch_id === activeBatchId));
                    }}
                    style={{ background: '#0284c7', color: '#fff' }}
                  >
                    📥 Export Plan (CSV)
                  </button>
                  <button
                    className="btn-xs"
                    onClick={() => {
                      const activeBatch = batches.find((b) => b.id === activeBatchId) || lastBatchResult;
                      handleExportJson(activeBatch);
                    }}
                    style={{ background: '#475569', color: '#fff' }}
                  >
                    📥 Export Plan (JSON)
                  </button>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10, fontSize: 12 }}>
                <label>
                  Cost / km (₹)
                  <input
                    type="number"
                    step="0.5"
                    className="setting-input full"
                    value={costConfig.cost_per_km}
                    onChange={(e) => setCostConfig({ ...costConfig, cost_per_km: Number(e.target.value) })}
                  />
                </label>
                <label>
                  Cost / driver hr (₹)
                  <input
                    type="number"
                    step="5"
                    className="setting-input full"
                    value={costConfig.cost_per_hour}
                    onChange={(e) => setCostConfig({ ...costConfig, cost_per_hour: Number(e.target.value) })}
                  />
                </label>
                <label>
                  Vehicle Activation (₹)
                  <input
                    type="number"
                    step="10"
                    className="setting-input full"
                    value={costConfig.vehicle_activation_cost}
                    onChange={(e) => setCostConfig({ ...costConfig, vehicle_activation_cost: Number(e.target.value) })}
                  />
                </label>
                <label>
                  Planning Mode
                  <select
                    className="setting-input full"
                    value={planningMode}
                    onChange={(e) => setPlanningMode(e.target.value as any)}
                  >
                    <option value="complete">Complete Plan (Mandatory Coverage)</option>
                    <option value="partial">Partial Plan (Shed by Priority)</option>
                  </select>
                </label>
                <label>
                  Optimization Profile
                  <select
                    className="setting-input full"
                    value={optimizationProfile}
                    onChange={(e) => setOptimizationProfile(e.target.value as any)}
                  >
                    <option value="cost_focused">Cost-focused (Min Financial J)</option>
                    <option value="balanced">Balanced (0.5 Cost + 0.5 Time)</option>
                    <option value="driver_productivity">Driver Productivity (Min Idle)</option>
                  </select>
                </label>
                <label>
                  Fleet Mode
                  <select
                    className="setting-input full"
                    value={fleetMode}
                    onChange={(e) => setFleetMode(e.target.value as any)}
                  >
                    <option value="auto">Auto Fleet (Optimal size)</option>
                    <option value="target">Target Fleet (Fixed budget)</option>
                  </select>
                </label>
                {fleetMode === 'target' && (
                  <label>
                    Target Fleet Count
                    <input
                      type="number"
                      min={1}
                      className="setting-input full"
                      value={targetFleetSize}
                      onChange={(e) => setTargetFleetSize(Number(e.target.value))}
                    />
                  </label>
                )}
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 18 }}>
                  <input
                    type="checkbox"
                    checked={depotReturn}
                    onChange={(e) => setDepotReturn(e.target.checked)}
                  />
                  <span>Return to Depot (R16)</span>
                </label>
              </div>

              {lastBatchResult?.cost_breakdown && (
                <div style={{ marginTop: 12, padding: 10, background: 'rgba(15, 23, 42, 0.8)', borderRadius: 8, border: '1px solid rgba(56, 189, 248, 0.2)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontWeight: 700, color: '#38bdf8' }}>💰 Financial Objective Cost Ledger:</span>
                    <strong style={{ fontSize: 15, color: '#10b981' }}>Total Cost J: ₹{lastBatchResult.cost_breakdown.total.toFixed(2)}</strong>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 8, fontSize: 11 }}>
                    <div>OPEX Distance: <strong>₹{lastBatchResult.cost_breakdown.opex_distance.toFixed(2)}</strong></div>
                    <div>OPEX Time: <strong>₹{lastBatchResult.cost_breakdown.opex_time.toFixed(2)}</strong></div>
                    <div>Fleet Mobilization: <strong>₹{lastBatchResult.cost_breakdown.fleet_activation.toFixed(2)}</strong></div>
                    <div>SLA Penalty: <strong style={{ color: lastBatchResult.cost_breakdown.sla_penalty > 0 ? '#f59e0b' : '#94a3b8' }}>₹{lastBatchResult.cost_breakdown.sla_penalty.toFixed(2)}</strong></div>
                    <div>Fleet Utilization: <strong>{lastBatchResult.fleet_utilization_pct || 0}%</strong></div>
                  </div>
                  {lastBatchResult.unserved_orders && lastBatchResult.unserved_orders.length > 0 && (
                    <div style={{ marginTop: 8, padding: 6, background: 'rgba(239, 68, 68, 0.1)', borderRadius: 6, color: '#fca5a5', fontSize: 11 }}>
                      <strong>⚠️ Partial Plan: {lastBatchResult.unserved_orders.length} unserved order(s) shed by priority:</strong>
                      <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                        {lastBatchResult.unserved_orders.map((u: any, idx: number) => (
                          <li key={idx}>Order {u.customer_id} ({u.priority_level}) - Reason: {u.reason} - Rec: {u.recommendations?.[0]}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
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

                <div style={{ background: 'rgba(99,102,241,0.08)', padding: 10, borderRadius: 8, border: '1px solid rgba(99,102,241,0.2)', marginBottom: 6 }}>
                  <label style={{ fontSize: 12, fontWeight: 600, color: '#c7d2fe', display: 'block', marginBottom: 4 }}>
                    👤 Returning Customer (Autofill Confirmed Location)
                  </label>
                  <select
                    className="setting-input full"
                    onChange={(e) => {
                      const selected = locations.find((l) => l.id === e.target.value);
                      if (selected) {
                        setLocForm({
                          customer_name: selected.customer_name,
                          customer_phone: selected.customer_phone,
                          address: selected.address,
                          lat: selected.lat,
                          lon: selected.lon,
                          demand: selected.demand,
                          priority: selected.priority,
                          ready_time: selected.ready_time,
                          due_time: selected.due_time,
                          service_time: selected.service_time,
                          delivery_instructions: selected.delivery_instructions || '',
                          time_window_type: selected.time_window_type || 'hard',
                        });
                        setActiveCoords({ lat: selected.lat, lon: selected.lon });
                        setLocationConfirmed(true);
                        setBanner({ type: 'ok', msg: `Autofilled saved coordinates for ${selected.customer_name}` });
                      }
                    }}
                    defaultValue=""
                  >
                    <option value="" disabled>-- Select returning customer to reuse confirmed coordinates --</option>
                    {locations.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.customer_name} ({l.address.slice(0, 30)}...)
                      </option>
                    ))}
                  </select>
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

                <label style={{ fontSize: 12, fontWeight: 600, color: '#c7d2fe' }}>
                  Delivery Instructions (Separate Dispatch Notes)
                  <textarea
                    rows={2}
                    placeholder="e.g. Ring bell, leave package with security gate 2, call upon arrival"
                    className="setting-input full"
                    style={{ marginTop: 4, resize: 'vertical' }}
                    value={locForm.delivery_instructions}
                    onChange={(e) => setLocForm({ ...locForm, delivery_instructions: e.target.value })}
                  />
                </label>

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

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 4, marginBottom: 8, padding: '6px 10px', background: locationConfirmed ? 'rgba(16,185,129,0.1)' : 'rgba(255,255,255,0.04)', borderRadius: 6, border: `1px solid ${locationConfirmed ? 'rgba(16,185,129,0.3)' : 'rgba(255,255,255,0.08)'}` }}>
                  <span style={{ fontSize: 12, color: locationConfirmed ? '#34d399' : '#94a3b8' }}>
                    {locationConfirmed ? '✓ Coordinates Confirmed & Locked' : '📍 Confirm coordinates before dispatching'}
                  </span>
                  <button
                    type="button"
                    className="btn-xs"
                    onClick={() => {
                      setLocationConfirmed(!locationConfirmed);
                      if (!locationConfirmed) {
                        setBanner({ type: 'ok', msg: `Coordinates locked: ${locForm.lat.toFixed(6)}, ${locForm.lon.toFixed(6)}` });
                      }
                    }}
                    style={{ background: locationConfirmed ? '#059669' : '#4f46e5', color: '#fff', border: 'none', padding: '4px 12px', borderRadius: 4, cursor: 'pointer' }}
                  >
                    {locationConfirmed ? 'Unlock' : 'Confirm Location'}
                  </button>
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

                <div className="two-col">
                  <label>
                    Window Type
                    <select
                      className="setting-input full"
                      value={locForm.time_window_type}
                      onChange={(e) => setLocForm({ ...locForm, time_window_type: e.target.value as 'hard' | 'soft' })}
                    >
                      <option value="hard">Hard Window (Strict completion)</option>
                      <option value="soft">Soft Window (SLA Lateness Penalty)</option>
                    </select>
                  </label>
                  <label>
                    Turnaround Service Time (sec)
                    <input
                      type="number"
                      step={30}
                      className="setting-input full"
                      value={locForm.service_time}
                      onChange={(e) => setLocForm({ ...locForm, service_time: Number(e.target.value) })}
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
