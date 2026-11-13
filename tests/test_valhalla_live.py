import json
import time
from routing.cost_oracle import ValhallaOracle, Location

def main():
    with open('benchmarks/instances/vadodara_30.json') as f:
        data = json.load(f)

    depot = Location('D0', data['depot']['lat'], data['depot']['lon'])
    custs = [Location(c['id'], c['lat'], c['lon']) for c in data['customers']]
    all_points = [depot] + custs

    print('Testing ValhallaOracle with https://valhalla1.openstreetmap.de...')
    oracle = ValhallaOracle(base_url='https://valhalla1.openstreetmap.de')
    
    t0 = time.time()
    res = oracle.matrix(all_points[:5])
    t1 = time.time()
    print(f'Matrix 5x5 done in {t1-t0:.2f}s. Durations shape: {len(res.durations)}x{len(res.durations[0])}, sample: {res.durations[0][1]:.1f}s')

    t0 = time.time()
    route_res = oracle.route(all_points[:11])
    t1 = time.time()
    print(f'Route 11 stops (chunked across >10 limit) done in {t1-t0:.2f}s. Coords: {len(route_res["coordinates"])}, dist: {route_res["distance_km"]}km, time: {route_res["time_sec"]}s')
    assert len(route_res["coordinates"]) > 11, "Road polyline coordinates should contain detailed intermediate points"

    print('Testing Fallback with dead URL on uncached points...')
    # Points 20..23 were never queried yet
    uncached_points = [Location(f'TEST_{i}', 23.0 + i * 0.01, 72.5 + i * 0.01) for i in range(3)]
    dead_oracle = ValhallaOracle(base_url='http://127.0.0.1:54321', timeout=0.8, fallback_to_haversine=True)
    dead_res = dead_oracle.matrix(uncached_points)
    print(f'Dead oracle fallback matrix done: {dead_res.durations[0][1]:.1f}s, fallback_active={dead_oracle.fallback_active}')
    assert dead_oracle.fallback_active is True, "Fallback should be active after failed network query"
    
    dead_route = dead_oracle.route(uncached_points)
    print(f'Dead oracle fallback route done: coords={len(dead_route["coordinates"])}, dist={dead_route["distance_km"]}km')
    assert dead_route["fallback"] is True, "Route fallback flag should be true"

    print('>>> ALL VALHALLA TESTS PASSED SUCCESSFULLY! <<<')

if __name__ == '__main__':
    main()
