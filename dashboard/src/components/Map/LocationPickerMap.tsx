import React, { useEffect, useRef, useState, useCallback } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

export interface LocationItem {
  id: string;
  customer_name: string;
  customer_phone: string;
  customer_email?: string;
  address: string;
  lat: number;
  lon: number;
  demand: number;
  priority: number;
  ready_time: number;
  due_time: number;
  service_time: number;
}

export interface WarehouseLocation {
  lat: number;
  lon: number;
  name?: string;
}

interface LocationPickerMapProps {
  warehouse?: WarehouseLocation;
  savedLocations: LocationItem[];
  activeCoords: { lat: number; lon: number } | null;
  onSelectCoords: (coords: { lat: number; lon: number }, address?: string) => void;
  onQuickAddLocation?: (locationData: {
    customer_name: string;
    customer_phone: string;
    address: string;
    lat: number;
    lon: number;
    demand: number;
    priority: number;
    ready_time: number;
    due_time: number;
    service_time: number;
  }) => Promise<void>;
  onEditLocation?: (location: LocationItem) => void;
  onDeleteLocation?: (id: string) => Promise<void>;
  hoveredLocationId?: string | null;
  onHoverLocation?: (id: string | null) => void;
  selectedLocationId?: string | null;
  onSelectLocation?: (id: string | null) => void;
  height?: number | string;
}

// Priority colors: 1 (Standard) to 5 (Critical)
export const PRIORITY_COLORS: Record<number, string> = {
  1: '#6366f1', // Indigo - Standard
  2: '#06b6d4', // Cyan - Regular
  3: '#f59e0b', // Amber - Medium
  4: '#f97316', // Orange - High
  5: '#ef4444', // Red - Critical / Express
};

// Haversine distance in km
export function getHaversineDistanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371; // Earth radius in km
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return Math.round(R * c * 100) / 100;
}

function fmtClock(sec: number): string {
  const mins = Math.floor(sec / 60);
  const h = Math.floor(mins / 60) % 24;
  const m = mins % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

export function LocationPickerMap({
  warehouse = { lat: 22.3072, lon: 73.1812, name: 'Vadodara Central Depot (Sayajigunj)' },
  savedLocations,
  activeCoords,
  onSelectCoords,
  onQuickAddLocation,
  onEditLocation,
  onDeleteLocation,
  hoveredLocationId,
  onHoverLocation,
  selectedLocationId,
  onSelectLocation,
  height = 460,
}: LocationPickerMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const savedMarkersRef = useRef<Map<string, maplibregl.Marker>>(new Map());
  const activeMarkerRef = useRef<maplibregl.Marker | null>(null);

  // Search & Geocoding states
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [showSearchDropdown, setShowSearchDropdown] = useState(false);

  // Quick add mode
  const [quickAddMode, setQuickAddMode] = useState(false);
  const [quickAddBusy, setQuickAddBusy] = useState(false);

  // Status message / toast
  const [toast, setToast] = useState<{ type: 'info' | 'warn' | 'ok'; msg: string } | null>(null);

  const showToast = useCallback((msg: string, type: 'info' | 'warn' | 'ok' = 'info', ttl = 4000) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), ttl);
  }, []);

  // Reverse geocode via Nominatim
  const reverseGeocode = useCallback(async (lat: number, lon: number): Promise<string> => {
    try {
      const url = `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lon}&zoom=18&addressdetails=1`;
      const res = await fetch(url, {
        headers: {
          'User-Agent': 'RouteIt-FleetManager/1.0 (sih2026-intelligent-routing)',
          Accept: 'application/json',
        },
      });
      if (!res.ok) return '';
      const data = await res.json();
      if (!data || !data.address) return data?.display_name || '';

      const a = data.address;
      const parts = [
        a.road || a.pedestrian || a.suburb || a.neighbourhood,
        a.suburb || a.city_district || a.neighbourhood,
        a.city || a.town || a.county || 'Vadodara',
        a.state || 'Gujarat',
      ].filter(Boolean);

      const deduped = parts.filter((val, i, arr) => i === 0 || val !== arr[i - 1]);
      return deduped.join(', ') || data.display_name;
    } catch (err) {
      console.warn('[PickerMap] Reverse geocoding failed:', err);
      return '';
    }
  }, []);

  // Initialize Map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const initialCenter: [number, number] = [
      activeCoords?.lon ?? warehouse.lon,
      activeCoords?.lat ?? warehouse.lat,
    ];

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
              'raster-opacity': 0.35, // sleek dark feel
              'raster-brightness-min': 0,
              'raster-brightness-max': 0.5,
              'raster-saturation': -0.7,
              'raster-contrast': 0.3,
            },
          },
        ],
      },
      center: initialCenter,
      zoom: 12.5,
    });

    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right');

    map.on('load', () => {
      // Add distance line source & layer
      map.addSource('distance-line', {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: [],
        },
      });

      map.addLayer({
        id: 'distance-line-layer',
        type: 'line',
        source: 'distance-line',
        paint: {
          'line-color': '#818cf8',
          'line-width': 2.5,
          'line-dasharray': [3, 2],
          'line-opacity': 0.85,
        },
      });

      // Depot Marker
      const depotEl = document.createElement('div');
      depotEl.className = 'picker-depot-marker';
      depotEl.innerHTML = `
        <div style="
          display: flex;
          align-items: center;
          gap: 6px;
          background: rgba(15, 23, 42, 0.95);
          border: 2px solid #818cf8;
          border-radius: 20px;
          padding: 4px 10px;
          box-shadow: 0 4px 14px rgba(99, 102, 241, 0.5);
          cursor: pointer;
        ">
          <span style="font-size: 16px;">🏭</span>
          <span style="font-size: 11px; font-weight: 700; color: #f8fafc; letter-spacing: 0.5px;">WAREHOUSE</span>
        </div>
      `;

      new maplibregl.Marker({ element: depotEl })
        .setLngLat([warehouse.lon, warehouse.lat])
        .setPopup(
          new maplibregl.Popup({ offset: 15, closeButton: false }).setHTML(`
            <div style="padding: 6px 10px; font-size: 12px; color: #f8fafc;">
              <strong>${warehouse.name || 'Central Distribution Hub'}</strong><br/>
              <span style="color: #94a3b8; font-size: 11px;">Starting Fleet Depot (0 km)</span><br/>
              <code style="color: #818cf8; font-size: 10px;">${warehouse.lat.toFixed(6)}, ${warehouse.lon.toFixed(6)}</code>
            </div>
          `)
        )
        .addTo(map);
    });

    // Map Click Handler
    map.on('click', async (e) => {
      const lat = Math.round(e.lngLat.lat * 1000000) / 1000000;
      const lon = Math.round(e.lngLat.lng * 1000000) / 1000000;

      // Validation 1: Distance from warehouse (> 100 km)
      const distFromHub = getHaversineDistanceKm(warehouse.lat, warehouse.lon, lat, lon);
      if (distFromHub > 100) {
        showToast(`⚠️ Point is ${distFromHub} km from depot (> 100 km standard delivery limit).`, 'warn');
      }

      // Reverse geocode
      const resolvedAddress = await reverseGeocode(lat, lon);

      // Check Quick Add Mode
      if (quickAddMode && onQuickAddLocation) {
        setQuickAddBusy(true);
        try {
          const nextIndex = savedLocations.length + 1;
          const defaultLoc = {
            customer_name: `Customer #${nextIndex} (${resolvedAddress.split(',')[0] || 'Stop'})`,
            customer_phone: `+91-98250${String(nextIndex).padStart(5, '0')}`,
            address: resolvedAddress || `Delivery Point near (${lat.toFixed(4)}, ${lon.toFixed(4)})`,
            lat,
            lon,
            demand: 10,
            priority: 1,
            ready_time: 28800,
            due_time: 54000,
            service_time: 600,
          };
          await onQuickAddLocation(defaultLoc);
          showToast(`⚡ Quick Add: Stop C${String(nextIndex).padStart(2, '0')} added at ${resolvedAddress.split(',')[0]}!`, 'ok');
        } catch (err: any) {
          showToast(`Quick add failed: ${err.message}`, 'warn');
        } finally {
          setQuickAddBusy(false);
        }
      } else {
        // Normal mode: auto-fill inputs and update active marker
        onSelectCoords({ lat, lon }, resolvedAddress);
        showToast(`📍 Selected point: ${distFromHub} km from Depot`, 'info', 2500);
      }
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Update Active Marker & Distance Line
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (!activeCoords) {
      if (activeMarkerRef.current) {
        activeMarkerRef.current.remove();
        activeMarkerRef.current = null;
      }
      // Clear line
      const source = map.getSource('distance-line') as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData({ type: 'FeatureCollection', features: [] });
      }
      return;
    }

    const { lat, lon } = activeCoords;

    if (!activeMarkerRef.current) {
      const activeEl = document.createElement('div');
      activeEl.className = 'picker-active-marker';
      activeEl.innerHTML = `
        <div style="position: relative; cursor: grab;">
          <div style="
            width: 28px;
            height: 28px;
            border-radius: 50%;
            background: #a855f7;
            border: 3px solid #ffffff;
            box-shadow: 0 0 16px rgba(168, 85, 247, 0.9), 0 0 0 4px rgba(168, 85, 247, 0.35);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            color: #fff;
            animation: pulse-ring 2s infinite;
          ">
            🎯
          </div>
        </div>
      `;

      const marker = new maplibregl.Marker({
        element: activeEl,
        draggable: true,
      })
        .setLngLat([lon, lat])
        .addTo(map);

      // Drag listener
      marker.on('dragend', async () => {
        const lngLat = marker.getLngLat();
        const nLat = Math.round(lngLat.lat * 1000000) / 1000000;
        const nLon = Math.round(lngLat.lng * 1000000) / 1000000;
        const revAddr = await reverseGeocode(nLat, nLon);
        onSelectCoords({ lat: nLat, lon: nLon }, revAddr);
      });

      activeMarkerRef.current = marker;
    } else {
      activeMarkerRef.current.setLngLat([lon, lat]);
    }

    // Update Distance Line from Warehouse
    const distKm = getHaversineDistanceKm(warehouse.lat, warehouse.lon, lat, lon);
    const source = map.getSource('distance-line') as maplibregl.GeoJSONSource | undefined;
    if (source) {
      source.setData({
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            properties: { distance_km: distKm },
            geometry: {
              type: 'LineString',
              coordinates: [
                [warehouse.lon, warehouse.lat],
                [lon, lat],
              ],
            },
          },
        ],
      });
    }
  }, [activeCoords, warehouse, onSelectCoords, reverseGeocode]);

  // Update Saved Markers on Map
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // Track active marker IDs
    const currentLocIds = new Set(savedLocations.map((l) => l.id));

    // Remove markers that were deleted
    for (const [id, marker] of savedMarkersRef.current.entries()) {
      if (!currentLocIds.has(id)) {
        marker.remove();
        savedMarkersRef.current.delete(id);
      }
    }

    // Add or update markers
    savedLocations.forEach((loc, idx) => {
      const code = `C${String(idx + 1).padStart(2, '0')}`;
      const color = PRIORITY_COLORS[loc.priority] || '#6366f1';
      const isHovered = loc.id === hoveredLocationId;
      const isSelected = loc.id === selectedLocationId;
      const distFromHub = getHaversineDistanceKm(warehouse.lat, warehouse.lon, loc.lat, loc.lon);

      let marker = savedMarkersRef.current.get(loc.id);

      if (!marker) {
        const el = document.createElement('div');
        el.className = `picker-stop-marker picker-stop-${loc.id}`;

        marker = new maplibregl.Marker({ element: el })
          .setLngLat([loc.lon, loc.lat])
          .addTo(map);

        savedMarkersRef.current.set(loc.id, marker);
      }

      // Update marker element styling
      const el = marker.getElement();
      el.innerHTML = `
        <div style="
          min-width: 32px;
          height: 24px;
          padding: 0 6px;
          border-radius: 12px;
          background: ${color};
          border: 2px solid ${isHovered || isSelected ? '#ffffff' : 'rgba(255,255,255,0.7)'};
          box-shadow: ${isHovered || isSelected ? `0 0 16px ${color}, 0 4px 10px rgba(0,0,0,0.6)` : '0 2px 6px rgba(0,0,0,0.4)'};
          display: flex;
          align-items: center;
          justify-content: center;
          font-family: 'JetBrains Mono', monospace;
          font-size: 11px;
          font-weight: 700;
          color: #ffffff;
          transform: ${isHovered || isSelected ? 'scale(1.2)' : 'scale(1)'};
          transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
          cursor: pointer;
        ">
          ${code}
        </div>
      `;

      // Popup Content with Edit & Delete actions
      const popupHtml = `
        <div style="padding: 10px 14px; font-size: 12px; color: #f8fafc; min-width: 220px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <strong style="color: ${color}; font-size: 13px;">${code} · ${loc.customer_name}</strong>
            <span style="font-size: 10px; background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px;">P${loc.priority}</span>
          </div>
          <div style="color: #cbd5e1; font-size: 11px; margin-bottom: 4px;">📍 ${loc.address}</div>
          <div style="display: flex; gap: 12px; color: #94a3b8; font-size: 11px; margin-bottom: 8px;">
            <span>📦 ${loc.demand} units</span>
            <span>⏰ ${fmtClock(loc.ready_time)}–${fmtClock(loc.due_time)}</span>
            <span>📏 ${distFromHub} km</span>
          </div>
          <div style="display: flex; gap: 8px; margin-top: 8px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 8px;">
            <button id="btn-edit-${loc.id}" style="
              flex: 1;
              padding: 4px 8px;
              background: #6366f1;
              color: white;
              border: none;
              border-radius: 4px;
              font-size: 11px;
              font-weight: 600;
              cursor: pointer;
            ">✏️ Edit</button>
            <button id="btn-del-${loc.id}" style="
              padding: 4px 8px;
              background: rgba(239, 68, 68, 0.2);
              color: #f87171;
              border: 1px solid rgba(239, 68, 68, 0.4);
              border-radius: 4px;
              font-size: 11px;
              cursor: pointer;
            ">🗑️</button>
          </div>
        </div>
      `;

      const popup = new maplibregl.Popup({ offset: 15, closeButton: false }).setHTML(popupHtml);
      marker.setPopup(popup);

      // Attach DOM button events on popup open
      popup.on('open', () => {
        const editBtn = document.getElementById(`btn-edit-${loc.id}`);
        const delBtn = document.getElementById(`btn-del-${loc.id}`);
        if (editBtn && onEditLocation) {
          editBtn.onclick = () => {
            onEditLocation(loc);
            popup.remove();
          };
        }
        if (delBtn && onDeleteLocation) {
          delBtn.onclick = async () => {
            if (window.confirm(`Delete stop ${code} (${loc.customer_name})?`)) {
              await onDeleteLocation(loc.id);
              popup.remove();
            }
          };
        }
      });
    });
  }, [savedLocations, hoveredLocationId, selectedLocationId, warehouse, onEditLocation, onDeleteLocation]);

  // Two-way sync: Pan to hovered/selected location from table
  useEffect(() => {
    const map = mapRef.current;
    if (!map || (!hoveredLocationId && !selectedLocationId)) return;

    const targetId = hoveredLocationId || selectedLocationId;
    const targetLoc = savedLocations.find((l) => l.id === targetId);
    if (targetLoc) {
      map.panTo([targetLoc.lon, targetLoc.lat], { duration: 600 });
      // Draw distance line to hovered stop
      const source = map.getSource('distance-line') as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData({
          type: 'FeatureCollection',
          features: [
            {
              type: 'Feature',
              properties: {
                distance_km: getHaversineDistanceKm(warehouse.lat, warehouse.lon, targetLoc.lat, targetLoc.lon),
              },
              geometry: {
                type: 'LineString',
                coordinates: [
                  [warehouse.lon, warehouse.lat],
                  [targetLoc.lon, targetLoc.lat],
                ],
              },
            },
          ],
        });
      }
    }
  }, [hoveredLocationId, selectedLocationId, savedLocations, warehouse]);

  // Handle Search Input (Debounced)
  useEffect(() => {
    if (!searchQuery.trim() || searchQuery.length < 2) {
      setSearchResults([]);
      setShowSearchDropdown(false);
      return;
    }

    const timer = setTimeout(async () => {
      setIsSearching(true);
      try {
        const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(
          searchQuery
        )}&viewbox=73.0,22.45,73.35,22.15&bounded=0&countrycodes=in&limit=5`;
        const res = await fetch(url, {
          headers: {
            'User-Agent': 'RouteIt-FleetManager/1.0 (sih2026-intelligent-routing)',
            Accept: 'application/json',
          },
        });
        if (res.ok) {
          const data = await res.json();
          setSearchResults(data || []);
          setShowSearchDropdown(true);
        }
      } catch (err) {
        console.warn('Search geocoding error:', err);
      } finally {
        setIsSearching(false);
      }
    }, 400);

    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Select Search Item
  const handleSelectSearchItem = (item: any) => {
    const lat = parseFloat(item.lat);
    const lon = parseFloat(item.lon);
    const address = item.display_name.split(',').slice(0, 3).join(', ');

    if (mapRef.current) {
      mapRef.current.flyTo({ center: [lon, lat], zoom: 15, duration: 800 });
    }

    onSelectCoords({ lat, lon }, address);
    setSearchQuery('');
    setShowSearchDropdown(false);
    showToast(`📍 Found: ${address}`, 'ok', 3000);
  };

  // Fit all stops
  const handleFitAllStops = () => {
    const map = mapRef.current;
    if (!map) return;

    const bounds = new maplibregl.LngLatBounds();
    bounds.extend([warehouse.lon, warehouse.lat]);

    if (activeCoords) {
      bounds.extend([activeCoords.lon, activeCoords.lat]);
    }

    savedLocations.forEach((loc) => {
      bounds.extend([loc.lon, loc.lat]);
    });

    map.fitBounds(bounds, { padding: 50, maxZoom: 15, duration: 800 });
    showToast('Zoomed to include warehouse and all delivery stops', 'info', 2000);
  };

  // Center on warehouse
  const handleCenterWarehouse = () => {
    if (mapRef.current) {
      mapRef.current.flyTo({ center: [warehouse.lon, warehouse.lat], zoom: 13, duration: 600 });
    }
  };

  // Use Current Location
  const handleUseCurrentLocation = () => {
    if (!navigator.geolocation) {
      showToast('Geolocation is not supported by your browser.', 'warn');
      return;
    }
    showToast('Acquiring current GPS coordinates...', 'info');
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const lat = Math.round(pos.coords.latitude * 1000000) / 1000000;
        const lon = Math.round(pos.coords.longitude * 1000000) / 1000000;
        if (mapRef.current) {
          mapRef.current.flyTo({ center: [lon, lat], zoom: 15, duration: 800 });
        }
        const revAddr = await reverseGeocode(lat, lon);
        onSelectCoords({ lat, lon }, revAddr);
        showToast('📍 Updated to your current location!', 'ok');
      },
      (err) => {
        showToast(`Could not obtain location: ${err.message}`, 'warn');
      },
      { timeout: 8000, enableHighAccuracy: true }
    );
  };

  // Distance from warehouse
  const activeDistanceKm = activeCoords
    ? getHaversineDistanceKm(warehouse.lat, warehouse.lon, activeCoords.lat, activeCoords.lon)
    : null;

  return (
    <div style={{ position: 'relative', width: '100%', height, borderRadius: 10, overflow: 'hidden', border: '1px solid rgba(99, 102, 241, 0.25)', boxShadow: '0 8px 32px rgba(0,0,0,0.45)' }}>
      {/* Map Container */}
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />

      {/* Top Floating Bar: Address Search & Quick Controls */}
      <div style={{
        position: 'absolute',
        top: 12,
        left: 12,
        right: 54, // Avoid overlapping maplibre nav controls
        display: 'flex',
        gap: 8,
        zIndex: 10,
      }}>
        {/* Search Input Box */}
        <div style={{ position: 'relative', flex: 1, maxWidth: 360 }}>
          <input
            type="text"
            placeholder="🔍 Search Vadodara area or road..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => searchQuery.length >= 2 && setShowSearchDropdown(true)}
            style={{
              width: '100%',
              padding: '8px 12px',
              backgroundColor: 'rgba(15, 23, 42, 0.92)',
              backdropFilter: 'blur(10px)',
              border: '1px solid rgba(99, 102, 241, 0.4)',
              borderRadius: 6,
              color: '#f8fafc',
              fontSize: 12,
              outline: 'none',
              boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
            }}
          />
          {isSearching && (
            <span style={{ position: 'absolute', right: 10, top: 9, fontSize: 11, color: '#818cf8' }}>Searching…</span>
          )}

          {/* Search Dropdown Results */}
          {showSearchDropdown && searchResults.length > 0 && (
            <div style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              right: 0,
              marginTop: 4,
              backgroundColor: 'rgba(15, 23, 42, 0.98)',
              backdropFilter: 'blur(12px)',
              border: '1px solid #334155',
              borderRadius: 6,
              boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
              overflow: 'hidden',
              zIndex: 30,
            }}>
              {searchResults.map((item, idx) => (
                <div
                  key={idx}
                  onClick={() => handleSelectSearchItem(item)}
                  style={{
                    padding: '8px 12px',
                    fontSize: 11,
                    color: '#e2e8f0',
                    borderBottom: idx < searchResults.length - 1 ? '1px solid rgba(255,255,255,0.06)' : 'none',
                    cursor: 'pointer',
                    transition: 'background 0.15s ease',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'rgba(99, 102, 241, 0.25)')}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                >
                  <div style={{ fontWeight: 600, color: '#f8fafc' }}>{item.display_name.split(',')[0]}</div>
                  <div style={{ color: '#94a3b8', fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.display_name}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Quick Add Mode Toggle */}
        <button
          type="button"
          onClick={() => {
            setQuickAddMode(!quickAddMode);
            showToast(
              !quickAddMode
                ? '⚡ Quick Add Mode ENABLED! Each click on the map immediately saves a delivery stop.'
                : 'Quick Add Mode disabled. Form submission active.',
              !quickAddMode ? 'ok' : 'info'
            );
          }}
          disabled={quickAddBusy}
          style={{
            padding: '6px 12px',
            backgroundColor: quickAddMode ? '#10b981' : 'rgba(15, 23, 42, 0.9)',
            border: quickAddMode ? '1px solid #34d399' : '1px solid rgba(255,255,255,0.2)',
            borderRadius: 6,
            color: quickAddMode ? '#ffffff' : '#cbd5e1',
            fontSize: 11,
            fontWeight: 700,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            boxShadow: quickAddMode ? '0 0 12px rgba(16, 185, 129, 0.5)' : 'none',
          }}
        >
          <span>⚡</span>
          <span>{quickAddMode ? 'Quick Add: ON' : 'Quick Add'}</span>
        </button>

        {/* Fit Bounds Button */}
        <button
          type="button"
          onClick={handleFitAllStops}
          title="Fit All Stops & Warehouse"
          style={{
            padding: '6px 10px',
            backgroundColor: 'rgba(15, 23, 42, 0.9)',
            border: '1px solid rgba(255,255,255,0.2)',
            borderRadius: 6,
            color: '#cbd5e1',
            fontSize: 11,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          ⛶ Fit All ({savedLocations.length})
        </button>

        {/* Center Warehouse Button */}
        <button
          type="button"
          onClick={handleCenterWarehouse}
          title="Center on Warehouse Depot"
          style={{
            padding: '6px 10px',
            backgroundColor: 'rgba(15, 23, 42, 0.9)',
            border: '1px solid rgba(255,255,255,0.2)',
            borderRadius: 6,
            color: '#cbd5e1',
            fontSize: 11,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          🏭 Depot
        </button>

        {/* Current GPS Location */}
        <button
          type="button"
          onClick={handleUseCurrentLocation}
          title="Use My Current GPS Location"
          style={{
            padding: '6px 10px',
            backgroundColor: 'rgba(15, 23, 42, 0.9)',
            border: '1px solid rgba(255,255,255,0.2)',
            borderRadius: 6,
            color: '#cbd5e1',
            fontSize: 11,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          📍 GPS
        </button>
      </div>

      {/* Floating Info Badge: Distance from Warehouse & Stop Count */}
      <div style={{
        position: 'absolute',
        bottom: 12,
        left: 12,
        zIndex: 10,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
      }}>
        {activeCoords && activeDistanceKm !== null && (
          <div style={{
            padding: '5px 12px',
            backgroundColor: 'rgba(15, 23, 42, 0.92)',
            backdropFilter: 'blur(8px)',
            border: `1px solid ${activeDistanceKm > 100 ? '#ef4444' : '#6366f1'}`,
            borderRadius: 20,
            fontSize: 11,
            fontWeight: 600,
            color: activeDistanceKm > 100 ? '#fca5a5' : '#e2e8f0',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
          }}>
            <span>📏</span>
            <span>{activeDistanceKm} km from Warehouse</span>
            {activeDistanceKm > 100 && <span style={{ color: '#ef4444' }}>(Outside 100km zone)</span>}
          </div>
        )}

        <div style={{
          padding: '5px 10px',
          backgroundColor: 'rgba(15, 23, 42, 0.85)',
          backdropFilter: 'blur(8px)',
          border: '1px solid rgba(255,255,255,0.15)',
          borderRadius: 20,
          fontSize: 11,
          color: '#94a3b8',
        }}>
          Saved Stops: <strong style={{ color: '#38bdf8' }}>{savedLocations.length}</strong>
        </div>
      </div>

      {/* Priority Legend */}
      <div style={{
        position: 'absolute',
        bottom: 12,
        right: 12,
        zIndex: 10,
        backgroundColor: 'rgba(15, 23, 42, 0.9)',
        backdropFilter: 'blur(8px)',
        border: '1px solid rgba(255,255,255,0.15)',
        borderRadius: 8,
        padding: '6px 10px',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        fontSize: 10,
        color: '#94a3b8',
      }}>
        <span style={{ fontWeight: 600, color: '#e2e8f0' }}>Priority:</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}><span style={{ width: 8, height: 8, borderRadius: '50%', background: '#6366f1' }}></span>1 (Std)</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}><span style={{ width: 8, height: 8, borderRadius: '50%', background: '#f59e0b' }}></span>3 (Med)</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}><span style={{ width: 8, height: 8, borderRadius: '50%', background: '#ef4444' }}></span>5 (Critical)</span>
      </div>

      {/* Floating Status Toast */}
      {toast && (
        <div style={{
          position: 'absolute',
          top: 60,
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 40,
          backgroundColor: toast.type === 'ok' ? 'rgba(16, 185, 129, 0.95)' : (toast.type === 'warn' ? 'rgba(239, 68, 68, 0.95)' : 'rgba(30, 41, 59, 0.95)'),
          backdropFilter: 'blur(8px)',
          color: '#ffffff',
          padding: '6px 16px',
          borderRadius: 20,
          fontSize: 12,
          fontWeight: 600,
          boxShadow: '0 6px 18px rgba(0,0,0,0.5)',
          animation: 'fadeIn 0.2s ease-out',
        }}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}
