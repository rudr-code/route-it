import { useState, useEffect, useCallback } from 'react';
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
