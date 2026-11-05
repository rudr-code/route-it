import { useEffect, useRef, useCallback } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { GeoJsonFeatureCollection, Customer } from '../../api/types';
import { VADODARA_CENTER } from '../../data/vadodara_scenario';

// Route colours for up to 8 vehicles
export const ROUTE_COLORS = [
  '#6366f1', // indigo
  '#f59e0b', // amber
  '#10b981', // emerald
  '#ef4444', // red
  '#8b5cf6', // violet
  '#06b6d4', // cyan
  '#f97316', // orange
  '#ec4899', // pink
];

interface RouteMapProps {
  geojson: GeoJsonFeatureCollection | null;
  customers: Array<{
    id: string;
    name?: string;
    lat: number;
    lon: number;
    demand: number;
    ready_time: number;
    due_time: number;
    service_time: number;
    priority: number; // int ge=1: 1=standard, 2+=high-priority
  }>;
  placementMode: 'idle' | 'congestion' | 'blockage';
  onMapClick: (lat: number, lon: number) => void;
  showBeforeAfter?: 'current' | 'previous';
  previousGeojson?: GeoJsonFeatureCollection | null;
}

export function RouteMap({
  geojson,
  customers,
  placementMode,
  onMapClick,
  showBeforeAfter = 'current',
  previousGeojson,
}: RouteMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const clickHandlerRef = useRef<((e: maplibregl.MapMouseEvent) => void) | null>(null);

  // Init map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
        sources: {
          'osm-tiles': {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '© OpenStreetMap contributors',
          },
        },
        layers: [
          {
            id: 'osm-tiles',
            type: 'raster',
            source: 'osm-tiles',
            paint: {
              'raster-opacity': 0.25, // dark overlay feel
              'raster-brightness-min': 0,
              'raster-brightness-max': 0.4,
              'raster-saturation': -0.8,
              'raster-contrast': 0.3,
            },
          },
        ],
      },
      center: VADODARA_CENTER,
      zoom: 12,
    });

    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    mapRef.current = map;

    // Depot marker
    const depotEl = document.createElement('div');
    depotEl.className = 'depot-marker';
    depotEl.innerHTML = `<svg width="32" height="32" viewBox="0 0 32 32" fill="none">
      <circle cx="16" cy="16" r="14" fill="#6366f1" stroke="#fff" stroke-width="2"/>
      <text x="16" y="21" text-anchor="middle" font-size="14" fill="white" font-family="Inter">🏭</text>
    </svg>`;
    new maplibregl.Marker({ element: depotEl })
      .setLngLat(VADODARA_CENTER)
      .setPopup(new maplibregl.Popup({ offset: 25 }).setText('Vadodara Central Depot'))
      .addTo(map);

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Update map click handler based on placementMode
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // Remove previous handler
    if (clickHandlerRef.current) {
      map.off('click', clickHandlerRef.current);
      clickHandlerRef.current = null;
    }

    if (placementMode !== 'idle') {
      map.getCanvas().style.cursor = 'crosshair';
      const handler = (e: maplibregl.MapMouseEvent) => {
        onMapClick(e.lngLat.lat, e.lngLat.lng);
      };
      map.on('click', handler);
      clickHandlerRef.current = handler;
    } else {
      map.getCanvas().style.cursor = '';
    }

    return () => {
      if (clickHandlerRef.current && map) {
        map.off('click', clickHandlerRef.current);
        clickHandlerRef.current = null;
      }
    };
  }, [placementMode, onMapClick]);

  // Render customer markers
  const renderCustomers = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;

    // Clear old markers (skip depot marker at index 0)
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    customers.forEach((c) => {
      const isPriority = c.priority >= 2;
      const el = document.createElement('div');
      el.className = isPriority ? 'customer-marker priority' : 'customer-marker';
      el.innerHTML = isPriority
        ? `<div class="marker-dot priority-dot"><span>⚡</span></div>`
        : `<div class="marker-dot"><span>${c.id.replace('C', '')}</span></div>`;

      const popup = new maplibregl.Popup({ offset: 20, className: 'route-popup' }).setHTML(`
        <div class="popup-content">
          <strong>${c.name ? `${c.id} — ${c.name}` : c.id}</strong>
          <div>Demand: ${c.demand} | ${isPriority ? '⚡ Priority' : 'Standard'}</div>
          <div>Window: ${secsToTime(c.ready_time)}–${secsToTime(c.due_time)}</div>
        </div>
      `);

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([c.lon, c.lat])
        .setPopup(popup)
        .addTo(map);

      markersRef.current.push(marker);
    });
  }, [customers]);

  useEffect(() => {
    renderCustomers();
  }, [renderCustomers]);

  // Render GeoJSON routes
  const renderRoutes = useCallback((data: GeoJsonFeatureCollection | null, prefix: string, opacity: number) => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    // Remove existing route layers/sources (glow layer must be removed before its source)
    for (let i = 0; i < 8; i++) {
      const rid = `${prefix}-route-${i}`;
      if (map.getLayer(`${rid}-glow`)) map.removeLayer(`${rid}-glow`);
      if (map.getLayer(rid)) map.removeLayer(rid);
      if (map.getSource(rid)) map.removeSource(rid);
    }
    const ptId = `${prefix}-stops`;
    if (map.getLayer(ptId)) map.removeLayer(ptId);
    if (map.getSource(ptId)) map.removeSource(ptId);

    if (!data) return;

    // Group LineString features by vehicle_id
    const routeFeatures = data.features.filter(
      (f) => f.geometry.type === 'LineString' || f.geometry.type === 'MultiLineString',
    );
    const grouped: Record<string, typeof routeFeatures> = {};
    routeFeatures.forEach((f) => {
      const vid = (f.properties?.vehicle_id as string) ?? 'V_1';
      grouped[vid] = grouped[vid] ?? [];
      grouped[vid].push(f);
    });

    const vehicles = Object.keys(grouped);
    vehicles.forEach((vid, idx) => {
      const color = ROUTE_COLORS[idx % ROUTE_COLORS.length];
      const sourceId = `${prefix}-route-${idx}`;
      map.addSource(sourceId, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: grouped[vid] } as never,
      });
      // Outer glow
      map.addLayer({
        id: `${sourceId}-glow`,
        type: 'line',
        source: sourceId,
        paint: {
          'line-color': color,
          'line-width': 8,
          'line-opacity': opacity * 0.2,
          'line-blur': 4,
        },
      });
      // Main line
      map.addLayer({
        id: sourceId,
        type: 'line',
        source: sourceId,
        paint: {
          'line-color': color,
          'line-width': 3,
          'line-opacity': opacity,
          'line-dasharray': prefix === 'prev' ? [3, 3] : [1],
        },
      });
    });
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (!map.isStyleLoaded()) {
      map.once('load', () => {
        renderRoutes(
          showBeforeAfter === 'previous' ? (previousGeojson ?? null) : geojson,
          'main',
          1.0,
        );
        if (showBeforeAfter === 'current' && previousGeojson) {
          renderRoutes(previousGeojson, 'prev', 0.4);
        }
      });
    } else {
      renderRoutes(
        showBeforeAfter === 'previous' ? (previousGeojson ?? null) : geojson,
        'main',
        1.0,
      );
      if (showBeforeAfter === 'current' && previousGeojson) {
        renderRoutes(previousGeojson, 'prev', 0.4);
      } else {
        // Clear prev routes
        renderRoutes(null, 'prev', 0);
      }
    }
  }, [geojson, previousGeojson, showBeforeAfter, renderRoutes]);

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%' }}>
      {placementMode !== 'idle' && (
        <div className="map-placement-hint">
          Click on the map to place{' '}
          {placementMode === 'congestion' ? '🚦 congestion' : '🚧 blockage'}
        </div>
      )}
    </div>
  );
}

function secsToTime(secs: number): string {
  const totalMins = Math.floor(secs / 60);
  const h = (Math.floor(totalMins / 60) % 24).toString().padStart(2, '0');
  const m = (totalMins % 60).toString().padStart(2, '0');
  return `${h}:${m}`;
}
