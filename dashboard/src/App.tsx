import { useCallback, useState } from 'react';
import { useSolver } from './hooks/useSolver';
import { useEvents } from './hooks/useEvents';
import { LeftPanel } from './components/LeftPanel/LeftPanel';
import { RouteMap } from './components/Map/RouteMap';
import { RightPanel } from './components/RightPanel/RightPanel';
import { EventControls } from './components/EventControls/EventControls';
import { TierBanner } from './components/EventControls/TierBanner';
import { vadodaraScenario } from './data/vadodara_scenario';
import type { SolutionResponse } from './api/types';

export default function App() {
  const [solverState, solverActions] = useSolver();
  const [eventState, eventActions] = useEvents();
  const [toggleMode, setToggleMode] = useState<'current' | 'previous'>('current');
  const [previousSolution, setPreviousSolution] = useState<SolutionResponse | null>(null);

  const handleNewSolution = useCallback((sol: SolutionResponse) => {
    // Directly update solver state with the newly re-optimized solution
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

  const showToggle = !!previousSolution && !!solverState.solution;

  return (
    <div className="app-layout">
      {/* Left Panel */}
      <LeftPanel
        solverState={solverState}
        convergence={solverState.convergence}
        onLoadScenario={solverActions.loadScenario}
        onSolve={solverActions.solve}
      />

      {/* Map + overlay controls */}
      <div className="map-area">
        {/* Map toolbar */}
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

        {/* Tier Banner */}
        {eventState.lastResult && (
          <TierBanner result={eventState.lastResult} onDismiss={eventActions.dismiss} />
        )}

        {/* Injecting overlay */}
        {eventState.isInjecting && (
          <div className="injecting-overlay">
            <span className="spinner-lg" /> Re-optimizing routes…
          </div>
        )}

        {/* Event error */}
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

      {/* Right Panel */}
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
  );
}
