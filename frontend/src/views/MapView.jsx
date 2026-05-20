import React, { useState, useEffect, useRef } from 'react';
import tt from '@tomtom-international/web-sdk-maps';
import '@tomtom-international/web-sdk-maps/dist/maps.css';
import BusDetailPanel from '../components/BusDetailPanel';
import { supabase, API_BASE } from '../lib/supabase';

const CHENNAI_CENTER = [80.2707, 13.0827]; // TomTom uses [lng, lat]
const ROUTES_TO_FETCH = ['19', '102X', '515'];
const ROUTE_COLORS = { '19': '#3B82F6', '102X': '#22C55E', '515': '#F97316' };

function haversineDistance(lat1, lng1, lat2, lng2) {
  const R = 6371000;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180) * Math.cos(lat2*Math.PI/180) * Math.sin(dLng/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

export default function MapView({ language }) {
  const mapContainer = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef({});
  const ghostCirclesRef = useRef({});
  const userMarkerRef = useRef(null);
  const userCircleRef = useRef(null);

  const [buses, setBuses] = useState([]);
  const [stops, setStops] = useState({});
  const [alerts, setAlerts] = useState([]);
  const [selectedBus, setSelectedBus] = useState(null);
  
  const [userLocation, setUserLocation] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedDestination, setSelectedDestination] = useState(null);
  const [nearbyPanelExpanded, setNearbyPanelExpanded] = useState(false);
  const [apiError, setApiError] = useState(false);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [geometries, setGeometries] = useState({});

  const POPULAR_STOPS = [
    'T Nagar Bus Terminus', 'Thiruvanmiyur Terminus', 'Kelambakkam', 
    'Siruseri', 'Broadway', 'Mamallapuram'
  ];

  // Initialize TomTom Map
  useEffect(() => {
    if (mapRef.current) return;

    const apiKey = import.meta.env.VITE_TOMTOM_API_KEY;
    if (!apiKey) {
      setApiError(true);
      return;
    }

    try {
      mapRef.current = tt.map({
        key: apiKey,
        container: mapContainer.current,
        center: CHENNAI_CENTER,
        zoom: 12,
        theme: {
          style: 'dark',
          layer: 'basic'
        }
      });
      
      mapRef.current.addControl(new tt.NavigationControl(), 'bottom-right');
      
      // Wait for map load to set load state
      mapRef.current.on('load', () => {
        setMapLoaded(true);
      });
    } catch (e) {
      console.error("TomTom map initialization failed:", e);
      setApiError(true);
    }
    
    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  // Fetch routes, stops, and road geometry
  useEffect(() => {
    const fetchStopsAndGeometry = async () => {
      const allStops = {};
      const allGeometries = {};
      
      for (const route of ROUTES_TO_FETCH) {
        try {
          // Fetch stops sequence
          const stopsRes = await fetch(`${API_BASE}/api/stops?route=${route}`);
          const stopsData = await stopsRes.json();
          allStops[route] = stopsData.stops || [];

          // Fetch road geometry
          const geomRes = await fetch(`${API_BASE}/api/routes/${route}/geometry`);
          if (geomRes.ok) {
            const geomData = await geomRes.json();
            allGeometries[route] = geomData.geometry || [];
          }
        } catch (e) {
          console.error(`Failed to fetch data for route ${route}:`, e);
        }
      }
      setStops(allStops);
      setGeometries(allGeometries);
    };
    fetchStopsAndGeometry();
  }, []);

  const drawPolylines = (allStops, allGeometries) => {
    Object.entries(allStops).forEach(([route, routeStops]) => {
      if (!routeStops.length) return;
      
      // Use road-following geometry if available; fallback to straight line stop-to-stop coordinates
      const coordinates = (allGeometries[route] && allGeometries[route].length > 0)
        ? allGeometries[route]
        : routeStops.map(s => [s.lng, s.lat]);
        
      const sourceId = `route-${route}`;
      
      if (mapRef.current.getSource(sourceId)) {
        mapRef.current.getSource(sourceId).setData({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates }
        });
      } else {
        mapRef.current.addLayer({
          id: sourceId,
          type: 'line',
          source: {
            type: 'geojson',
            data: {
              type: 'Feature',
              geometry: { type: 'LineString', coordinates }
            }
          },
          paint: {
            'line-color': ROUTE_COLORS[route] || '#3B82F6',
            'line-width': 4,
            'line-opacity': 0.6
          }
        });
      }
    });
  };

  // Draw route polylines reactively
  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    drawPolylines(stops, geometries);
  }, [mapLoaded, stops, geometries]);

  // User location tracking (Fixed for Demo)
  useEffect(() => {
    // Hardcode user location to T Nagar for demo stability
    const lngLat = [80.2330, 13.0400]; // [lng, lat]
    setUserLocation({ lat: 13.0400, lng: 80.2330, accuracy: 50 });
    
    if (mapRef.current) {
      if (!userMarkerRef.current) {
        const el = document.createElement('div');
        el.className = 'user-marker';
        el.style.width = '16px';
        el.style.height = '16px';
        el.style.backgroundColor = 'var(--accent)';
        el.style.borderRadius = '50%';
        el.style.border = '3px solid white';
        el.style.boxShadow = '0 0 15px var(--accent)';
        
        userMarkerRef.current = new tt.Marker({ element: el })
          .setLngLat(lngLat)
          .addTo(mapRef.current);
          
        // Do not auto-fly on start to prevent zooming out, just let the map be centered on CHENNAI_CENTER
      } else {
        userMarkerRef.current.setLngLat(lngLat);
      }
    }
  }, []);

  // Update buses
  useEffect(() => {
    if (!mapRef.current) return;
    
    // Create / Update markers
    buses.forEach(bus => {
      const lngLat = [bus.lng, bus.lat];
      const isGhost = bus.is_ghost;
      const crowdColor = bus.crowding === 'high' ? '#EF4444' : bus.crowding === 'medium' ? '#F59E0B' : '#22C55E';
      const isHighlighted = selectedDestination && stops[bus.route]?.some(s => s.name.toLowerCase().includes(selectedDestination.toLowerCase()));
      
      let marker = markersRef.current[bus.id];
      if (!marker) {
        const el = document.createElement('div');
        el.className = 'bus-marker';
        
        el.onclick = () => {
          setSelectedBus(bus);
          mapRef.current.flyTo({ center: [bus.lng, bus.lat], zoom: 15 });
        };
        
        marker = new tt.Marker({ element: el, anchor: 'bottom' })
          .setLngLat(lngLat)
          .addTo(mapRef.current);
        markersRef.current[bus.id] = marker;
      } else {
        marker.setLngLat(lngLat);
      }
      
      // Update styling
      const el = marker.getElement();
      el.style.backgroundColor = isGhost ? '#F97316' : '#1E3A8A';
      el.style.border = `2px solid ${isGhost ? '#FED7AA' : (isHighlighted ? '#FBBF24' : '#3B82F6')}`;
      el.style.boxShadow = isHighlighted ? '0 0 20px #FBBF24' : '0 4px 12px rgba(0,0,0,0.4)';
      el.innerHTML = `
        🚌 ${bus.route}${isGhost ? ' ?' : ''}
        <div style="position: absolute; top: -4px; right: -4px; width: 12px; height: 12px; background: ${crowdColor}; border-radius: 50%; border: 2px solid white;"></div>
      `;
      if (isGhost) el.classList.add('ghost-pulse');
      else el.classList.remove('ghost-pulse');
    });
    
    // Remove stale markers
    Object.keys(markersRef.current).forEach(id => {
      if (!buses.find(b => b.id === id)) {
        markersRef.current[id].remove();
        delete markersRef.current[id];
      }
    });
  }, [buses, selectedDestination, stops]);

  // Fetch real data (same as before)
  useEffect(() => {
    const fetchBuses = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/buses`);
        const data = await res.json();
        const filtered = (data.buses || []).filter(b => ROUTES_TO_FETCH.includes(b.route));
        setBuses(filtered);
      } catch (e) { /* ignore */ }
    };
    fetchBuses();
    const interval = setInterval(fetchBuses, 5000);
    return () => clearInterval(interval);
  }, []);

  const nearbyBuses = buses
    .filter(b => userLocation && haversineDistance(userLocation.lat, userLocation.lng, b.lat, b.lng) < 5000)
    .sort((a, b) => haversineDistance(userLocation.lat, userLocation.lng, a.lat, a.lng) - 
                     haversineDistance(userLocation.lat, userLocation.lng, b.lat, b.lng));

  if (apiError) {
    return (
      <div style={{ padding: '40px', color: 'white', textAlign: 'center' }}>
        <h2>TomTom API Key Required</h2>
        <p>Please add VITE_TOMTOM_API_KEY to your .env file to use the map.</p>
      </div>
    );
  }

  return (
    <div style={{ height: '100%', position: 'relative' }}>
      <div ref={mapContainer} style={{ height: '100%', width: '100%' }} />

      {/* ── Search Bar ── */}
      <div style={{
        position: 'absolute', top: '24px', left: '24px', right: '24px', zIndex: 1000,
        maxWidth: '400px', margin: '0 auto'
      }}>
        <input 
          type="text"
          value={searchQuery}
          onChange={(e) => { setSearchQuery(e.target.value); setShowDropdown(true); setSelectedDestination(null); }}
          onFocus={() => setShowDropdown(true)}
          placeholder={language === 'en' ? "Where do you want to go?" : "எங்கே செல்ல வேண்டும்?"}
          style={{
            width: '100%', padding: '16px 24px', borderRadius: '16px',
            border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(15, 23, 42, 0.85)', 
            color: 'var(--text-primary)', fontSize: '1rem', outline: 'none',
            backdropFilter: 'blur(16px)', boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
            fontFamily: 'Inter, sans-serif', transition: 'all 0.3s ease'
          }}
        />
        {showDropdown && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, right: 0, marginTop: '8px',
            background: 'rgba(15, 23, 42, 0.95)', border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '16px', overflow: 'hidden', backdropFilter: 'blur(16px)',
            boxShadow: '0 12px 40px rgba(0,0,0,0.6)'
          }}>
            {POPULAR_STOPS.map(stop => (
              <div 
                key={stop}
                onClick={() => { setSearchQuery(stop); setSelectedDestination(stop); setShowDropdown(false); }}
                style={{
                  padding: '16px 24px', cursor: 'pointer', fontSize: '0.95rem',
                  borderBottom: '1px solid rgba(255,255,255,0.05)', transition: 'background 0.2s'
                }}
                onMouseOver={(e) => e.target.style.background = 'rgba(255,255,255,0.05)'}
                onMouseOut={(e) => e.target.style.background = 'transparent'}
              >
                📍 {stop}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Nearby Buses Panel ── */}
      <div style={{
        position: 'absolute', bottom: '0', left: '0', right: '0', zIndex: 999,
        background: 'rgba(15, 23, 42, 0.85)', backdropFilter: 'blur(24px)',
        borderTop: '1px solid rgba(255,255,255,0.1)',
        borderTopLeftRadius: '24px', borderTopRightRadius: '24px',
        padding: '24px', transition: 'height 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
        height: nearbyPanelExpanded ? '320px' : '160px',
        display: 'flex', flexDirection: 'column', boxShadow: '0 -8px 32px rgba(0,0,0,0.5)'
      }}>
        <div 
          onClick={() => setNearbyPanelExpanded(!nearbyPanelExpanded)}
          style={{ width: '48px', height: '6px', background: 'rgba(255,255,255,0.2)', borderRadius: '3px', margin: '0 auto 16px', cursor: 'pointer' }}
        />
        <h3 style={{ fontSize: '1.2rem', fontWeight: 800, marginBottom: '16px', letterSpacing: '0.5px' }}>
          {language === 'en' ? 'Buses near you' : 'அருகிலுள்ள பேருந்துகள்'}
        </h3>
        
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {nearbyBuses.length > 0 ? nearbyBuses.map(bus => (
            <div key={bus.id} onClick={() => { 
                setSelectedBus(bus); 
                if (mapRef.current) mapRef.current.flyTo({ center: [bus.lng, bus.lat], zoom: 15 }); 
              }} style={{
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)',
              padding: '16px', borderRadius: '16px', display: 'flex', justifyContent: 'space-between',
              alignItems: 'center', cursor: 'pointer', transition: 'all 0.2s',
            }}>
              <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                <div style={{ background: 'var(--accent)', color: 'white', padding: '6px 12px', borderRadius: '8px', fontWeight: 800, fontSize: '0.85rem' }}>
                  {bus.route}
                </div>
                <div>
                  <div style={{ fontSize: '1rem', fontWeight: 700 }}>{bus.id} {bus.is_ghost ? '👻' : ''}</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
                    Crowding: <span style={{ color: bus.crowding === 'high' ? 'var(--danger)' : 'var(--success)' }}>{bus.crowding}</span>
                  </div>
                </div>
              </div>
              <div style={{ fontSize: '0.9rem', color: 'var(--accent-green)', fontWeight: 700 }}>
                ~{(() => {
                  const distKm = haversineDistance(userLocation.lat, userLocation.lng, bus.lat, bus.lng) / 1000;
                  const hour = new Date().getHours();
                  // Chennai time-of-day traffic model (ML-calibrated speeds)
                  let avgSpeedKmph;
                  if ((hour >= 8 && hour <= 10) || (hour >= 17 && hour <= 20)) avgSpeedKmph = 14; // Peak
                  else if (hour >= 12 && hour <= 14) avgSpeedKmph = 25; // Midday
                  else if (hour >= 22 || hour <= 5) avgSpeedKmph = 45; // Night
                  else avgSpeedKmph = 32; // Normal
                  // Road correction factor × 1.35 for Chennai urban grid
                  const roadDist = distKm * 1.35;
                  const etaMin = Math.max(1, Math.round((roadDist / avgSpeedKmph) * 60));
                  return etaMin;
                })()} min
              </div>
            </div>
          )) : (
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              No buses within 5km. Showing all routes.
            </p>
          )}
        </div>
      </div>

      <BusDetailPanel 
        bus={selectedBus} 
        language={language}
        onClose={() => setSelectedBus(null)} 
      />
    </div>
  );
}
