import { ROUTE_COLORS } from '../Map/RouteMap';
import type { Route } from '../../api/types';

function formatEta(arrivalSecs: number): string {
  const totalMins = Math.floor(arrivalSecs / 60);
  const h = (Math.floor(totalMins / 60) % 24).toString().padStart(2, '0');
  const m = (totalMins % 60).toString().padStart(2, '0');
  return `${h}:${m}`;
}

type CustomerMeta = {
  name?: string;
  ready_time: number;
  due_time: number;
  priority: number; // int ge=1; 2+ = high priority
};

function twStatus(arrivalSecs: number, c: CustomerMeta | undefined): 'ok' | 'late' | 'unknown' {
  if (!c) return 'unknown';
  if (arrivalSecs > c.due_time) return 'late';
  return 'ok';
}

interface RouteCardProps {
  route: Route;
  index: number;
  customerMap: Map<string, CustomerMeta>;
}

function RouteCard({ route, index, customerMap }: RouteCardProps) {
  const color = ROUTE_COLORS[index % ROUTE_COLORS.length];
  const stopCount = route.stop_ids.length;

  // Strict SI contract: distance in metres, convert directly to km
  const distKm = (route.distance / 1000).toFixed(1);

  // Strict SI contract: duration in seconds, convert directly to h/m
  const durMins = Math.round(route.duration / 60);
  const durHours = route.duration / 3600;
  const durText = durHours >= 1 ? `${durHours.toFixed(1)}h` : `${durMins}m`;

  return (
    <div className="route-card" style={{ borderLeft: `3px solid ${color}` }}>
      <div className="route-card-header">
        <span className="vehicle-label" style={{ color }}>
          {route.vehicle_id}
        </span>
        <span className={`route-feasible ${route.is_feasible !== false ? 'ok' : 'warn'}`}>
          {route.is_feasible !== false ? '✓' : '⚠'}
        </span>
        <span className="route-meta">
          {stopCount} stops · {route.load.toFixed(0)} units
        </span>
      </div>

      <div className="route-stats">
        <span>⏱ {durText}</span>
        <span>📍 {distKm} km</span>
      </div>

      <div className="stop-list">
        {route.stop_ids.slice(0, 8).map((cid, si) => {
          const c = customerMap.get(cid);
          const arrival = route.arrival_times[si] ?? 0;
          const status = twStatus(arrival, c);
          const isPriority = (c?.priority ?? 1) >= 2;
          return (
            <div key={`${cid}-${si}`} className={`stop-item ${status}`}>
              <span className="stop-id">
                {isPriority ? '⚡' : '•'} {c?.name ?? cid}
              </span>
              <span className="stop-eta">ETA {formatEta(arrival)}</span>
              {status === 'late' && <span className="tw-badge late">LATE</span>}
            </div>
          );
        })}
        {stopCount > 8 && (
          <div className="stop-more">+{stopCount - 8} more…</div>
        )}
      </div>
    </div>
  );
}

interface RightPanelProps {
  routes: Route[];
  customers: Array<{ id: string; name?: string; ready_time: number; due_time: number; priority: number }>;
  oracleType: 'euclidean' | 'valhalla';
  valhallaConnected?: boolean;
  showToggle: boolean;
  toggleMode: 'current' | 'previous';
  onToggle: () => void;
}

export function RightPanel({
  routes,
  customers,
  oracleType,
  valhallaConnected = false,
  showToggle,
  toggleMode,
  onToggle,
}: RightPanelProps) {
  const customerMap = new Map(
    customers.map((c) => [c.id, { name: c.name, ready_time: c.ready_time, due_time: c.due_time, priority: c.priority }]),
  );

  const isLiveValhalla = oracleType === 'valhalla' && valhallaConnected === true;
  const trafficLabel = isLiveValhalla
    ? '🟢 Valhalla: connected (public server)'
    : oracleType === 'valhalla' && !valhallaConnected
    ? '🟡 Valhalla unavailable, traffic simulated'
    : '🟡 Traffic: simulated';

  return (
    <div className="right-panel glass-panel">
      <div className="panel-header">
        <span className="panel-title">Fleet Routes</span>
        <div className="panel-header-right">
          <div className={`traffic-badge ${isLiveValhalla ? 'live' : 'simulated'}`}>
            {trafficLabel}
          </div>
        </div>
      </div>

      {/* Before/After toggle */}
      {showToggle && (
        <div className="toggle-row">
          <button
            id="btn-toggle-before-after"
            className={`toggle-btn ${toggleMode === 'previous' ? 'active' : ''}`}
            onClick={onToggle}
          >
            {toggleMode === 'current' ? '📸 Show Before' : '🔄 Show After'}
          </button>
          <span className="toggle-hint">
            {toggleMode === 'previous' ? 'Viewing pre-event routes' : 'Viewing repaired routes'}
          </span>
        </div>
      )}

      {/* Route cards */}
      <div className="route-list">
        {routes.length === 0 ? (
          <div className="no-routes">
            <div className="no-routes-icon">🚚</div>
            <div>No routes yet. Load a scenario and press Solve.</div>
          </div>
        ) : (
          routes.map((r, i) => (
            <RouteCard key={r.vehicle_id} route={r} index={i} customerMap={customerMap} />
          ))
        )}
      </div>
    </div>
  );
}
