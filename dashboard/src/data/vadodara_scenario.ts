import rawVadodaraJson from './vadodara_30.json';
import type { ProblemCreateRequest } from '../api/types';

// Canonical Vadodara 30-stop delivery scenario
// Sourced from dashboard/src/data/vadodara_30.json.
// All distances are in metres, times in seconds (SI unit contract).
export const vadodaraScenario: ProblemCreateRequest = {
  id: rawVadodaraJson.id,
  coordinate_system: (rawVadodaraJson.coordinate_system as 'geographic' | 'planar') || 'geographic',
  depot: {
    id: rawVadodaraJson.depot.id,
    name: rawVadodaraJson.depot.name,
    lat: rawVadodaraJson.depot.lat,
    lon: rawVadodaraJson.depot.lon,
    ready_time: rawVadodaraJson.depot.ready_time,
    due_time: rawVadodaraJson.depot.due_time,
    service_time: rawVadodaraJson.depot.service_time,
  },
  // rawVadodaraJson.customers.map
  customers: (rawVadodaraJson.customers as any[]).map((c: any) => ({
    id: c.id,
    name: c.name,
    lat: c.lat,
    lon: c.lon,
    demand: c.demand,
    ready_time: c.ready_time,
    due_time: c.due_time,
    service_time: c.service_time,
    priority: c.priority ?? 1,
  })),
  // rawVadodaraJson.vehicles.map
  vehicles: (rawVadodaraJson.vehicles as any[]).map((v: any) => ({
    id: v.id,
    capacity: v.capacity,
    shift_start: v.shift_start,
    shift_end: v.shift_end,
  })),
};

export const VADODARA_CENTER: [number, number] = [
  vadodaraScenario.depot.lon,
  vadodaraScenario.depot.lat,
];
