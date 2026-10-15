# Valhalla Routing Engine Setup (Vadodara / Gujarat)

This directory manages the local Dockerized **Valhalla** road routing engine for Route.it. Valhalla powers our cost oracle by calculating real road network travel times, turn-by-turn routes, and distance matrices.

---

## 1. Verified Docker Image & Architecture

- **Official Image**: `ghcr.io/valhalla/valhalla-scripted:latest`  
  *(Public image on GitHub Container Registry, maintained directly upstream by the Valhalla core team).*
- **Legacy Image**: `ghcr.io/gis-ops/docker-valhalla/valhalla:latest`  
  *(Archived by GIS-Ops; upstream `valhalla-scripted` inherits all entrypoint scripts and options).*
- **Port**: `8002` (standard Valhalla HTTP API port).
- **Directory Mount**: `./custom_files:/custom_files` (stores OSM PBF inputs, built tile archives, and cached SQLite DBs).

---

## 2. Download the OSM Extract (Vadodara or Gujarat)

Geofabrik only provides the full country extract (`india-latest.osm.pbf`, ~1.5 GB), which is unnecessarily heavy for local development. We recommend obtaining a small extract for **Vadodara** (~5–12 MB) or **Gujarat** (~100–140 MB).

### Option A: Vadodara City Extract via BBBike (Recommended: < 12 MB)
1. Navigate to the **[BBBike Custom Extract Service](https://extract.bbbike.org/)**.
2. Enter the bounding box coordinates for **Vadodara**:
   - **South (min lat)**: `22.18`
   - **West (min lon)**: `73.08`
   - **North (max lat)**: `22.42`
   - **East (max lon)**: `73.32`
3. Under **Format**, select: **`Protocolbuffer (PBF)`**.
4. Set the name to: `vadodara` and click **Extract**.
5. Once generated (~1–2 minutes), download the `.osm.pbf` file and save it as:
   ```
   routing/custom_files/vadodara.osm.pbf
   ```

### Option B: Entire Gujarat State Extract via BBBike (~120 MB)
If you require routing across all of Gujarat (Ahmedabad, Surat, Rajkot, Vadodara):
1. On **[BBBike Extract](https://extract.bbbike.org/)**, set bounding box coordinates:
   - **South (min lat)**: `20.10`
   - **West (min lon)**: `68.10`
   - **North (max lat)**: `24.70`
   - **East (max lon)**: `74.50`
2. Select format **`Protocolbuffer (PBF)`**, name it `gujarat`, and download to:
   ```
   routing/custom_files/gujarat.osm.pbf
   ```

### Option C: Crop from Geofabrik India (via `osmium`)
If you already possess `india-latest.osm.pbf` and `osmium-tool`:
```bash
# Extract Vadodara bounding box
osmium extract --bbox 73.08,22.18,73.32,22.42 india-latest.osm.pbf -o routing/custom_files/vadodara.osm.pbf
```

---

## 3. Starting the Valhalla Container

Once your `.osm.pbf` file is placed inside `routing/custom_files/`:

```bash
# Navigate to the routing directory
cd routing

# Launch the Valhalla container in detached mode
docker compose up -d
```

### Inspect Build & Initialization Logs
On the first run, the scripted container detects any `*.pbf` files in `/custom_files`, builds the routing graph tiles, packages them into `valhalla_tiles.tar`, and starts `valhalla_service`:
```bash
docker compose logs -f valhalla
```
Look for the startup confirmation:
```
INFO: Found config file. Starting valhalla service!
```

### Stop the Service
```bash
docker compose down
```

### Force a Full Tile Rebuild
If you update the `.osm.pbf` file or change routing options, rebuild tiles by setting `force_rebuild=True`:
```bash
docker compose run --rm -e force_rebuild=True valhalla
```

---

## 4. Verified Curl API Examples (Vadodara Landmarks)

- **Vadodara Junction Railway Station**: `22.3108, 73.1811`
- **Sayaji Baug (Kamati Baug)**: `22.3129, 73.1906`
- **Laxmi Vilas Palace**: `22.2936, 73.1915`

### A. Healthcheck (`/status`)
```bash
curl -X GET "http://localhost:8002/status"
```
**Expected Response**:
```json
{
  "version": "3.4.x",
  "tileset_last_modified": 1700000000
}
```

### B. Route Calculation (`/route`)
Calculates driving route between Vadodara Junction and Sayaji Baug:
```bash
curl -X POST "http://localhost:8002/route" \
  -H "Content-Type: application/json" \
  -d '{
    "locations": [
      {"lat": 22.3108, "lon": 73.1811, "type": "break"},
      {"lat": 22.3129, "lon": 73.1906, "type": "break"}
    ],
    "costing": "auto",
    "directions_options": {"units": "kilometers"}
  }'
```
**Expected Response Structure**:
```json
{
  "trip": {
    "summary": {
      "length": 1.25,
      "time": 185
    },
    "legs": [...]
  }
}
```

### C. Travel Time & Distance Matrix (`/sources_to_targets`)
Computes the distance/time matrix from Vadodara Junction (source) to Sayaji Baug and Laxmi Vilas Palace (targets):
```bash
curl -X POST "http://localhost:8002/sources_to_targets" \
  -H "Content-Type: application/json" \
  -d '{
    "sources": [
      {"lat": 22.3108, "lon": 73.1811}
    ],
    "targets": [
      {"lat": 22.3129, "lon": 73.1906},
      {"lat": 22.2936, "lon": 73.1915}
    ],
    "costing": "auto"
  }'
```
**Expected Response Structure**:
```json
{
  "sources_to_targets": [
    [
      {"distance": 1.25, "time": 185, "to_index": 0, "from_index": 0},
      {"distance": 3.10, "time": 420, "to_index": 1, "from_index": 0}
    ]
  ]
}
```

---

## 5. Automated Health Check Script

An automated Python health check utility is included in `routing/healthcheck.py`:
```bash
python routing/healthcheck.py
```
Options:
- `--url`: Valhalla base URL (default: `http://localhost:8002`)
- `--timeout`: Request timeout in seconds (default: `5.0`)

Exit codes:
- `0`: Service is online, `/status` is responsive, and a sample Vadodara route query succeeded.
- `1`: Service is offline or returned an error.

Run health check unit tests:
```bash
python -m pytest tests/routing/test_healthcheck.py -v
```

---

## 6. Upstream Verification & Limitations Report

### What Was Verified
1. **Docker Image**: Verified that `ghcr.io/valhalla/valhalla-scripted:latest` is the official, actively maintained image from `valhalla/valhalla`, and that it is publicly accessible without registry authentication.
2. **Configuration Variables**: Verified against `docker/scripts/docker-entrypoint.sh` and `docker/scripts/configure_valhalla.sh`:
   - `build_elevation=False` avoids downloading SRTM elevation tiles.
   - `build_admins=True` invokes `valhalla_build_admins` on input `.pbf` to configure country borders and left-hand driving rules for India.
   - `build_time_zones=True` creates `timezones.sqlite` enabling time-dependent routing.
   - `build_tar=True` packages graph tiles into `valhalla_tiles.tar` for fast container restarts.
   - `server_threads=2` restricts concurrency to prevent CPU/memory exhaustion.
   - `serve_tiles=True` launches `valhalla_service`.
3. **Volume Mount**: Verified that any `*.pbf` placed in `/custom_files` is automatically detected by the container's glob loop `$(ls $CUSTOM_FILES/*.pbf)`.
4. **API Formats**: Verified `/route` and `/sources_to_targets` request and response JSON schemas against official Valhalla API documentation.

### What Could Not Be Verified
1. **Live Container Execution**: Docker is not currently installed or running on this Windows host (`docker` command not recognized in PowerShell). Live tile generation, container startup logs, and real network roundtrips could not be executed on this machine.
2. **Empirical Tile Build Memory/Time**: The exact build time and RAM consumption of the Vadodara PBF extract inside the container could not be measured locally without a functioning Docker daemon.

---

## 7. Cost Oracle & Traffic Engine (`routing/cost_oracle.py`)

The cost oracle subsystem abstracts road network routing and travel-time estimation away from the metaheuristic optimization solver.

> [!IMPORTANT]
> **INTEGRITY NOTICE: TRAFFIC IS SIMULATED**  
> Unless an authentic external commercial provider adapter (such as TomTom Routing API, Google Maps Platform, or HERE Traffic) is explicitly configured and authenticated, **ALL traffic conditions, hourly congestion curves, and dynamic incidents are SIMULATED** (using the time-dependent speed profile formulation of Ichoua et al. 2003 or synthetic incident injection).

### 7.1 Architecture & Oracles
- **`CostOracle` (Abstract Base)**:
  - `travel_time(origin, dest, depart_time=0.0) -> float`: Duration in seconds.
  - `distance(origin, dest) -> float`: Distance in metres.
  - `matrix(points, depart_time=0.0) -> MatrixResult`: $N \times N$ duration (seconds) and distance (metres) matrices (supports tuple unpacking: `durations, distances = oracle.matrix(...)`).
  - `evaluate_route(stops, start_time, ...)`: Sequential time-dependent timeline evaluation.
- **`ValhallaOracle`**:
  - Connects to the local/remote Valhalla container `/sources_to_targets` endpoint.
  - **Chunked Matrix Querying**: Splits large matrix requests into configurable blocks (`chunk_size`, default 50) to prevent Valhalla max matrix limits exhaustion.
  - Converts kilometers to metres and times to seconds.
- **`EuclideanOracle`**:
  - Fast, deterministic planar or haversine distance oracle for Solomon / CVRPLIB benchmarks and offline unit testing.

### 7.2 Caching Subsystem (`CostCache`)
- **Key Strategy**: `(origin_id, dest_id, time_bucket)` where `time_bucket = int(depart_time // bucket_size_seconds)` (default 15 minutes = 900s).
- **Implementations**:
  - `InMemoryLRUCache`: In-memory `OrderedDict` bounded by `max_size` (default 50,000).
  - `SQLiteCache`: Persistent SQLite database (`cost_cache.sqlite` or `:memory:`).
- **Telemetry**: Records `hits`, `misses`, and `hit_ratio` for cache efficiency monitoring.

### 7.3 Traffic Adapters (`TrafficAdapter`)
- **`TimeOfDayProfileAdapter`**:
  - Hourly speed multipliers based on Ichoua, Gendreau & Potvin (2003).
  - Morning rush (08:00–10:00: 0.65x speed, +54% travel time).
  - Evening rush (16:00–19:30: 0.60x speed, +67% travel time).
  - Night (22:00–06:00: 1.15x speed, -13% travel time).
- **`SimulatedEventAdapter`**:
  - Runtime injection of dynamic incidents: road closures (`speed_multiplier=0.0` -> infinite travel time), lane blockages, or severe bottlenecks.
  - Targets specific OD pairs or geographic radius zones `(center_lat, center_lon, radius_m)`.
- **`ProviderAdapter` (Stub)**:
  - Integration template for real commercial providers (TomTom, Google, HERE).
  - In default mode without credentials, logs a notice and defaults to baseline free-flow.

### 7.4 Time-Dependent Route Evaluation
Arrival time at stop $k$ is strictly computed from the actual departure time of the previous stop $k-1$:
$$\text{arrival}_k = \text{departure}_{k-1} + \text{travel\_time}(\text{stop}_{k-1}, \text{stop}_k, \text{departure}_{k-1})$$
$$\text{departure}_k = \max(\text{arrival}_k, \text{ready\_time}_k) + \text{service\_time}_k$$

### 7.5 Running the Unit Tests
```bash
python -m pytest tests/routing/test_cost_oracle.py -v
```
To run the live integration test when Valhalla is running:
```bash
python -m pytest tests/routing/test_cost_oracle.py -v -m integration
```


