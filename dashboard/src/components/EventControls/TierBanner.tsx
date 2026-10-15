import type { EventInjectResponse } from '../../api/types';

const TIER_META: Record<string, { label: string; color: string; icon: string }> = {
  tier_1_path_repair: { label: 'Tier 1 — Path Repair', color: '#10b981', icon: '🔧' },
  tier_2_local_repair: { label: 'Tier 2 — Local Repair', color: '#f59e0b', icon: '🔀' },
  tier_3_qpso_warm_start: { label: 'Tier 3 — QPSO Warm Start', color: '#ef4444', icon: '⚛' },
  no_replan: { label: 'No Re-plan', color: '#6366f1', icon: '✓' },
  infeasible_no_better: { label: 'No Improvement Found', color: '#94a3b8', icon: '—' },
};

interface TierBannerProps {
  result: EventInjectResponse;
  onDismiss: () => void;
}

export function TierBanner({ result, onDismiss }: TierBannerProps) {
  const meta = TIER_META[result.tier_selected] ?? {
    label: result.tier_selected,
    color: '#6366f1',
    icon: '⚡',
  };

  const costDelta = result.cost_after - result.cost_before;
  const deltaPct = result.cost_before > 0 ? (costDelta / result.cost_before) * 100 : 0;

  return (
    <div id="tier-banner" className="tier-banner" style={{ borderColor: meta.color }}>
      <div className="tier-banner-header" style={{ background: `${meta.color}22` }}>
        <span className="tier-icon">{meta.icon}</span>
        <span className="tier-label" style={{ color: meta.color }}>{meta.label}</span>
        <span className={`feasible-chip ${result.is_feasible ? 'ok' : 'warn'}`}>
          {result.is_feasible ? 'Feasible' : 'Infeasible'}
        </span>
        <button className="dismiss-btn" onClick={onDismiss} title="Dismiss">✕</button>
      </div>

      <div className="tier-stats">
        <div className="tier-stat">
          <span className="stat-label">Time</span>
          <span className="stat-val">{result.wall_clock_time_ms.toFixed(0)} ms</span>
        </div>
        <div className="tier-stat">
          <span className="stat-label">Cost before</span>
          <span className="stat-val">{result.cost_before.toFixed(1)}</span>
        </div>
        <div className="tier-stat">
          <span className="stat-label">Cost after</span>
          <span className="stat-val">{result.cost_after.toFixed(1)}</span>
        </div>
        <div className="tier-stat">
          <span className="stat-label">Δ Cost</span>
          <span className={`stat-val ${costDelta > 0 ? 'up' : 'down'}`}>
            {costDelta > 0 ? '+' : ''}{costDelta.toFixed(1)} ({deltaPct.toFixed(1)}%)
          </span>
        </div>
        <div className="tier-stat">
          <span className="stat-label">Stops changed</span>
          <span className="stat-val">{result.stops_changed_count}</span>
        </div>
      </div>

      {result.message && <div className="tier-message">{result.message}</div>}
    </div>
  );
}
