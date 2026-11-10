import { useCallback, useState } from 'react';
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
