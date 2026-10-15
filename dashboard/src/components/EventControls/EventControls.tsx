import type { EventPlacementMode } from '../../hooks/useEvents';

interface EventControlsProps {
  placementMode: EventPlacementMode;
  isInjecting: boolean;
  hasSolution: boolean;
  onStartCongestion: () => void;
  onStartBlockage: () => void;
  onCancel: () => void;
}

export function EventControls({
  placementMode,
  isInjecting,
  hasSolution,
  onStartCongestion,
  onStartBlockage,
  onCancel,
}: EventControlsProps) {
  return (
    <div className="event-controls">
      <span className="event-label">Dynamic Events</span>

      {placementMode === 'idle' ? (
        <>
          <button
            id="btn-sim-congestion"
            className="btn btn-event congestion"
            disabled={!hasSolution || isInjecting}
            onClick={onStartCongestion}
            title="Click the map to place congestion"
          >
            {isInjecting ? <span className="spinner-sm" /> : '🚦'} Congestion
          </button>
          <button
            id="btn-sim-blockage"
            className="btn btn-event blockage"
            disabled={!hasSolution || isInjecting}
            onClick={onStartBlockage}
            title="Click the map to place a road blockage"
          >
            {isInjecting ? <span className="spinner-sm" /> : '🚧'} Blockage
          </button>
        </>
      ) : (
        <button className="btn btn-cancel" onClick={onCancel}>
          ✕ Cancel placement
        </button>
      )}
    </div>
  );
}
