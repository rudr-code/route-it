import { useState, useEffect, useCallback } from 'react';
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
