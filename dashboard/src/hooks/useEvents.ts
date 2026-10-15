import { useState, useCallback } from 'react';
import { api } from '../api/client';
import type { EventInjectResponse, SolutionResponse } from '../api/types';

type MinCustomer = { id: string; lat: number; lon: number };

export type EventPlacementMode = 'idle' | 'congestion' | 'blockage';

export interface EventState {
  placementMode: EventPlacementMode;
  lastResult: EventInjectResponse | null;
  isInjecting: boolean;
  error: string | null;
}

export interface EventActions {
  startPlacement: (mode: 'congestion' | 'blockage') => void;
  cancelPlacement: () => void;
  injectAtPoint: (
    problemId: string,
    lat: number,
    lon: number,
    customers: MinCustomer[],
    onNewSolution: (sol: SolutionResponse) => void,
  ) => Promise<void>;
  dismiss: () => void;
}

// Find the two nearest customer IDs to a clicked map point
function findNearestIds(lat: number, lon: number, customers: MinCustomer[]): [string, string] {
  const sorted = [...customers].sort((a, b) => {
    const da = Math.hypot(a.lat - lat, a.lon - lon);
    const db = Math.hypot(b.lat - lat, b.lon - lon);
    return da - db;
  });
  const first = sorted[0]?.id ?? 'C01';
  const second = sorted[1]?.id ?? 'C02';
  return [first, second];
}

export function useEvents(): [EventState, EventActions] {
  const [state, setState] = useState<EventState>({
    placementMode: 'idle',
    lastResult: null,
    isInjecting: false,
    error: null,
  });

  const startPlacement = useCallback((mode: 'congestion' | 'blockage') => {
    setState((s) => ({ ...s, placementMode: mode, lastResult: null, error: null }));
  }, []);

  const cancelPlacement = useCallback(() => {
    setState((s) => ({ ...s, placementMode: 'idle' }));
  }, []);

  const injectAtPoint = useCallback(
    async (
      problemId: string,
      lat: number,
      lon: number,
      customers: MinCustomer[],
      onNewSolution: (sol: SolutionResponse) => void,
    ) => {
      const [originId, destId] = findNearestIds(lat, lon, customers);
      const mode = state.placementMode;

      setState((s) => ({ ...s, isInjecting: true, placementMode: 'idle', error: null }));

      try {
        const result = await api.injectEvent(problemId, {
          event_type: mode === 'congestion' ? 'edge_congestion' : 'road_blockage',
          trigger_time: 0,
          duration: mode === 'congestion' ? 1800 : 3600,
          origin_id: originId,
          dest_id: destId,
          multiplier: mode === 'congestion' ? 3.0 : 999,
          description: mode === 'congestion'
            ? `Map-placed congestion near [${lat.toFixed(4)}, ${lon.toFixed(4)}]`
            : `Map-placed blockage near [${lat.toFixed(4)}, ${lon.toFixed(4)}]`,
        });
        setState((s) => ({ ...s, lastResult: result, isInjecting: false }));
        onNewSolution(result.solution);
      } catch (e: unknown) {
        setState((s) => ({
          ...s,
          isInjecting: false,
          error: e instanceof Error ? e.message : String(e),
        }));
      }
    },
    [state.placementMode],
  );

  const dismiss = useCallback(() => {
    setState((s) => ({ ...s, lastResult: null, error: null }));
  }, []);

  return [state, { startPlacement, cancelPlacement, injectAtPoint, dismiss }];
}
