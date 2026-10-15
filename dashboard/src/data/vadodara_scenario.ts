import type { ProblemCreateRequest } from '../api/types';

// Customer priority: backend uses int ge=1. 1=standard, 2=high-priority (medicine/essentials).
// Sending priority=false (bool) was the root cause of the 422 Unprocessable Entity.

// Vadodara city centre: 22.3072°N, 73.1812°E
// 30 delivery stops within ~8 km radius, seeded deterministically

const DEPOT_LAT = 22.3072;
const DEPOT_LON = 73.1812;

// 30 named locations around Vadodara
const RAW_STOPS: Array<{
  name: string;
  lat: number;
  lon: number;
  demand: number;
  ready_time: number;
  due_time: number;
  service_time: number;
  priority?: boolean;
}> = [
  { name: 'Alkapuri', lat: 22.3105, lon: 73.1667, demand: 8, ready_time: 480, due_time: 660, service_time: 10 },
  { name: 'Fatehgunj', lat: 22.3242, lon: 73.1816, demand: 5, ready_time: 540, due_time: 720, service_time: 8 },
  { name: 'Sayajiganj', lat: 22.3166, lon: 73.1780, demand: 12, ready_time: 480, due_time: 600, service_time: 12, priority: true },
  { name: 'Manjalpur', lat: 22.2721, lon: 73.1823, demand: 7, ready_time: 600, due_time: 840, service_time: 10 },
  { name: 'Waghodia', lat: 22.3280, lon: 73.2350, demand: 9, ready_time: 480, due_time: 780, service_time: 15 },
  { name: 'Makarpura', lat: 22.2598, lon: 73.1756, demand: 6, ready_time: 600, due_time: 900, service_time: 10 },
  { name: 'Gorwa', lat: 22.3412, lon: 73.1554, demand: 4, ready_time: 540, due_time: 720, service_time: 8 },
  { name: 'Productivity Road', lat: 22.3051, lon: 73.1901, demand: 10, ready_time: 480, due_time: 660, service_time: 10 },
  { name: 'Nizampura', lat: 22.3438, lon: 73.1945, demand: 8, ready_time: 600, due_time: 840, service_time: 12 },
  { name: 'Akota', lat: 22.3001, lon: 73.1729, demand: 11, ready_time: 480, due_time: 720, service_time: 10, priority: true },
  { name: 'Harni', lat: 22.3213, lon: 73.2082, demand: 5, ready_time: 540, due_time: 780, service_time: 8 },
  { name: 'Chhani', lat: 22.3613, lon: 73.1784, demand: 7, ready_time: 600, due_time: 900, service_time: 10 },
  { name: 'Karelibaug', lat: 22.3296, lon: 73.1883, demand: 9, ready_time: 480, due_time: 660, service_time: 12 },
  { name: 'Sama', lat: 22.3162, lon: 73.2002, demand: 6, ready_time: 540, due_time: 840, service_time: 8 },
  { name: 'Subhanpura', lat: 22.2963, lon: 73.1693, demand: 8, ready_time: 480, due_time: 720, service_time: 10 },
  { name: 'Ellora Park', lat: 22.2892, lon: 73.1761, demand: 5, ready_time: 600, due_time: 900, service_time: 8 },
  { name: 'Panigate', lat: 22.2990, lon: 73.2030, demand: 12, ready_time: 480, due_time: 600, service_time: 15 },
  { name: 'Raopura', lat: 22.2983, lon: 73.2107, demand: 7, ready_time: 540, due_time: 720, service_time: 10 },
  { name: 'Navapura', lat: 22.3069, lon: 73.2144, demand: 9, ready_time: 480, due_time: 780, service_time: 12 },
  { name: 'Gotri', lat: 22.2852, lon: 73.1623, demand: 6, ready_time: 600, due_time: 840, service_time: 8 },
  { name: 'Vadsar', lat: 22.3718, lon: 73.2102, demand: 10, ready_time: 480, due_time: 720, service_time: 15 },
  { name: 'Atladra', lat: 22.2701, lon: 73.1918, demand: 8, ready_time: 540, due_time: 900, service_time: 10 },
  { name: 'Tandalja', lat: 22.2786, lon: 73.1557, demand: 5, ready_time: 480, due_time: 660, service_time: 8 },
  { name: 'Vasna', lat: 22.2622, lon: 73.1638, demand: 7, ready_time: 600, due_time: 780, service_time: 10 },
  { name: 'Warasiya', lat: 22.3395, lon: 73.2285, demand: 9, ready_time: 480, due_time: 840, service_time: 12 },
  { name: 'Tarsali', lat: 22.2550, lon: 73.1967, demand: 11, ready_time: 540, due_time: 720, service_time: 15 },
  { name: 'Sevasi', lat: 22.2817, lon: 73.1463, demand: 6, ready_time: 480, due_time: 900, service_time: 8 },
  { name: 'Navayard', lat: 22.3128, lon: 73.1944, demand: 8, ready_time: 540, due_time: 660, service_time: 10 },
  { name: 'Jetalpur', lat: 22.2482, lon: 73.1779, demand: 10, ready_time: 480, due_time: 780, service_time: 12 },
  { name: 'Pratap Nagar', lat: 22.3047, lon: 73.2236, demand: 7, ready_time: 600, due_time: 840, service_time: 10 },
];

export const vadodaraScenario: ProblemCreateRequest = {
  id: 'vadodara_demo',
  depot: {
    id: 'depot',
    lat: DEPOT_LAT,
    lon: DEPOT_LON,
    ready_time: 420,   // 07:00
    due_time: 1080,    // 18:00
    service_time: 0,
    name: 'Vadodara Central Depot',
  },
  customers: RAW_STOPS.map((s, i) => ({
    id: `C${String(i + 1).padStart(2, '0')}`,
    lat: s.lat,
    lon: s.lon,
    demand: s.demand,
    ready_time: s.ready_time,
    due_time: s.due_time,
    service_time: s.service_time,
    // Backend Customer.priority is int ge=1. 1=standard, 2=high-priority.
    // Sending boolean false caused 422: "Input should be >= 1".
    priority: s.priority ? 2 : 1,
  })),
  vehicles: [
    { id: 'V_1', capacity: 80, shift_start: 420, shift_end: 1080 },
    { id: 'V_2', capacity: 80, shift_start: 420, shift_end: 1080 },
    { id: 'V_3', capacity: 80, shift_start: 420, shift_end: 1080 },
  ],
};

export const VADODARA_CENTER: [number, number] = [DEPOT_LON, DEPOT_LAT]; // [lng, lat] for MapLibre
