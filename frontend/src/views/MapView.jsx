import React, { useState, useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Polyline, CircleMarker, Tooltip, Polygon, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import BusDetailPanel from '../components/BusDetailPanel';
import ETABadge, { computeETA } from '../components/ETABadge';
import { API_BASE } from '../lib/supabase';
import { loadAllRoutePolylines, snapToPolyline } from '../services/routePolylines';
import { createSimulatorState, tickBuses } from '../services/busSimulator';
import { addPingsAndGetHexes } from '../services/h3DemandLayer';
import { useWatchedStop } from '../context/WatchedStopContext';
import { useStopArrivalAlert } from '../hooks/useStopArrivalAlert';
import { useDeviationAlert } from '../hooks/useDeviationAlert';
import { AlertTriangle, MapPin } from 'lucide-react';

const CHENNAI_CENTER = [13.0827, 80.2707];
const ROUTES_TO_FETCH = ['19', '102X', '515', '21C', '70', '47A'];
const ROUTE_COLORS = { 
  '19': '#00D4FF', 
  '102X': '#00E5A0', 
  '515': '#FFB800',
  '21C': '#FF6B35',
  '70': '#C084FC',
  '47A': '#F472B6'
};

function haversineDistance(lat1, lng1, lat2, lng2) {
  const R = 6371000;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180) * Math.cos(lat2*Math.PI/180) * Math.sin(dLng/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

// ─── Custom Icons ────────────────────────────────────────────────────────
const createBusIcon = (bus, isHighlighted, isDeviated) => {
  const isGhost = bus.is_ghost;
  const crowdColor = bus.crowding === 'high' ? 'var(--color-danger)' : bus.crowding === 'medium' ? 'var(--color-warning)' : 'var(--color-success)';
  
  const borderColor = isGhost ? 'var(--color-ghost-pulse)' : 'var(--color-accent)';
  const pulseClass = isGhost ? 'ghost-pulse' : '';
  const highlightShadow = isHighlighted ? 'box-shadow: 0 0 20px #FBBF24;' : '';
  const deviationBadge = isDeviated
    ? `<span style="position:absolute;top:-6px;right:-6px;background:var(--color-ghost-pulse,#FF6B35);color:#fff;border-radius:3px;font-size:9px;font-weight:900;padding:1px 4px;line-height:1.2;font-family:monospace;">!</span>`
    : '';

  const html = `
    <div class="custom-bus-marker ${pulseClass}" style="
      position: relative;
      background-color: var(--color-bg-elevated);
      border: 1.5px solid ${borderColor};
      border-left: 6px solid ${crowdColor};
      border-radius: 8px;
      padding: 4px 8px;
      color: var(--color-text-primary);
      font-family: var(--font-data);
      font-size: 11px;
      font-weight: 600;
      display: flex;
      align-items: center;
      justify-content: center;
      white-space: nowrap;
      ${highlightShadow}
    ">
      ${bus.route}${isGhost ? ' ?' : ''}
      ${deviationBadge}
    </div>
  `;

  return L.divIcon({
    html,
    className: '',
    iconSize: [60, 30],
    iconAnchor: [30, 15],
  });
};

const LerpingBusMarker = ({ bus, isHighlighted, isDeviated, routePolyline, onClick }) => {
  const [pos, setPos] = useState(snapToPolyline([bus.lat, bus.lng], routePolyline));
  const posRef = useRef(pos);
  const targetRef = useRef(pos);
  const requestRef = useRef();

  useEffect(() => {
    targetRef.current = snapToPolyline([bus.lat, bus.lng], routePolyline);
  }, [bus.lat, bus.lng, routePolyline]);

  useEffect(() => {
    const animate = () => {
      const current = posRef.current;
      const target = targetRef.current;
      const dLat = target[0] - current[0];
      const dLng = target[1] - current[1];
      
      if (Math.abs(dLat) > 0.00001 || Math.abs(dLng) > 0.00001) {
        const next = [current[0] + dLat * 0.08, current[1] + dLng * 0.08];
        posRef.current = next;
        setPos(next);
      }
      requestRef.current = requestAnimationFrame(animate);
    };
    requestRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(requestRef.current);
  }, []);

  return (
    <Marker
      position={pos}
      icon={createBusIcon(bus, isHighlighted, isDeviated)}
      eventHandlers={{
        click: (e) => {
          if (e && e.originalEvent) {
            L.DomEvent.stopPropagation(e);
          }
          onClick(e);
        }
      }}
    />
  );
};

export default function MapView({ language, focusBusId, onClearFocus }) {
  const mapRef = useRef(null);
  
  const [buses, setBuses] = useState([]);
  const [stops, setStops] = useState({});
  const [geometries, setGeometries] = useState({});
  const [tomtomPolylines, setTomtomPolylines] = useState(new Map());
  const [selectedBus, setSelectedBus] = useState(null);
  const [showBoardingModal, setShowBoardingModal] = useState(false);
  
  const [userLocation, setUserLocation] = useState({ lat: 13.0827, lng: 80.2707, accuracy: 50 });
  const [searchQuery, setSearchQuery] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedDestination, setSelectedDestination] = useState(null);
  const [nearbyPanelExpanded, setNearbyPanelExpanded] = useState(false);

  const [mapCenter, setMapCenter] = useState(CHENNAI_CENTER);
  const [mapZoom, setMapZoom] = useState(12);

  const { watchedStop, setWatchedStop } = useWatchedStop();
  const { alert, setAlert } = useStopArrivalAlert(buses);
  const [selectedStopForWatch, setSelectedStopForWatch] = useState(null);

  // ── Deviation Alerts ──
  const { deviationAlert, dismissAlert, deviatedBusIds } = useDeviationAlert();

  // ── H3 Demand Layer (frontend-side, clustered around buses) ──
  const [demandHexes, setDemandHexes] = useState([]);
  const [showDemandLayer, setShowDemandLayer] = useState(true);

  const HEX_STYLES = {
    low:    { fillColor: 'rgba(0, 212, 255, 0.08)',  color: 'transparent', weight: 0, fillOpacity: 1 },
    medium: { fillColor: 'rgba(255, 184, 0, 0.18)',  color: '#FFB800',     weight: 0.5, fillOpacity: 1, opacity: 0.5 },
    high:   { fillColor: 'rgba(255, 69,  96, 0.28)',  color: '#FF4560',     weight: 1, fillOpacity: 1, opacity: 0.6 },
  };

  const POPULAR_STOPS = [
    'T Nagar', 'Velachery', 'Kelambakkam', 
    'Sholinganallur', 'Broadway', 'Mamallapuram', 'Adyar', 'Koyambedu'
  ];

  // ── Bus Simulator State ──
  const simBusesRef = useRef(createSimulatorState());
  const tickCountRef = useRef(0);
  const [etaData, setEtaData] = useState({});

  // Fetch stops and road-snapped polylines
  useEffect(() => {
    const fetchStopsAndGeometry = async () => {
      const allStops = {};

      await Promise.all(
        ROUTES_TO_FETCH.map(async (route) => {
          try {
            const res = await fetch(`${API_BASE}/api/stops?route=${route}`);
            const data = await res.json();
            allStops[route] = data.stops || [];
          } catch (e) {
            allStops[route] = [];
          }
        })
      );

      // Fetch road-snapped polylines (OSRM primary, TomTom fallback)
      try {
        const polyMap = await loadAllRoutePolylines();
        setTomtomPolylines(polyMap);
      } catch (e) {
        console.warn('Failed to fetch polylines:', e);
      }

      setStops(allStops);
    };
    fetchStopsAndGeometry();
  }, []);

  // ── Frontend bus simulation: 2s tick ──
  useEffect(() => {
    const interval = setInterval(() => {
      if (tomtomPolylines.size === 0) return;
      tickCountRef.current += 1;
      const updated = tickBuses(simBusesRef.current, tomtomPolylines, tickCountRef.current);
      simBusesRef.current = updated;
      setBuses([...updated]);

      // Update H3 demand hexes (clustered around bus positions)
      const hexes = addPingsAndGetHexes(updated);
      setDemandHexes(hexes);
    }, 2000);
    return () => clearInterval(interval);
  }, [tomtomPolylines]);

  // ── ETA recalculation every 30s ──
  useEffect(() => {
    const calcETAs = () => {
      if (tomtomPolylines.size === 0) return;
      const newEtas = {};
      buses.forEach(bus => {
        newEtas[bus.id] = computeETA(bus, tomtomPolylines);
      });
      setEtaData(newEtas);
    };
    calcETAs();
    const interval = setInterval(calcETAs, 30000);
    return () => clearInterval(interval);
  }, [buses, tomtomPolylines]);

  // Handle focusBusId
  useEffect(() => {
    if (focusBusId && buses.length > 0) {
      const busToFocus = buses.find(b => b.id === focusBusId);
      if (busToFocus) {
        setSelectedBus(busToFocus);
        setShowBoardingModal(false);
        setMapCenter([busToFocus.lat, busToFocus.lng]);
        setMapZoom(16);
      }
    }
  }, [focusBusId, buses]);

  const handleMapClick = () => {
    if (showBoardingModal) {
      setShowBoardingModal(false);
    } else {
      setSelectedBus(null);
      setSelectedStopForWatch(null);
      if (onClearFocus) onClearFocus();
    }
  };

  const nearbyBuses = buses
    .filter(b => haversineDistance(userLocation.lat, userLocation.lng, b.lat, b.lng) < 5000)
    .sort((a, b) => haversineDistance(userLocation.lat, userLocation.lng, a.lat, a.lng) - 
                     haversineDistance(userLocation.lat, userLocation.lng, b.lat, b.lng));

  return (
    <div style={{ height: '100%', position: 'relative' }}>
      <MapContainer 
        center={mapCenter} 
        zoom={mapZoom} 
        zoomControl={false}
        ref={mapRef}
        style={{ height: '100%', width: '100%', background: 'var(--color-bg-base)' }}
      >
        <MapUpdater center={mapCenter} zoom={mapZoom} />
        <MapEventsHandler onClick={handleMapClick} />
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution="&copy; <a href='https://openstreetmap.org'>OpenStreetMap</a> &copy; <a href='https://carto.com/'>CARTO</a>"
        />

        {/* Polylines — road-snapped from TomTom */}
        {ROUTES_TO_FETCH.map(route => {
          let coords = tomtomPolylines.get(route);
          if (!coords || !coords.length) {
            if (stops[route]?.length > 0) {
              coords = stops[route].map(s => [s.lat, s.lng]);
            }
          }
          if (!coords || !coords.length) return null;
          return (
            <Polyline
              key={route}
              positions={coords}
              pathOptions={{ color: ROUTE_COLORS[route] || '#3B82F6', weight: 4, opacity: 0.7 }}
            />
          );
        })}

        {/* Stops */}
        {Object.entries(stops).map(([route, routeStops]) => 
          routeStops.map((stop, i) => (
            <CircleMarker
              key={`${route}-${stop.id}-${i}`}
              center={[stop.lat, stop.lng]}
              radius={4}
              pathOptions={{
                fillColor: 'var(--color-accent)',
                fillOpacity: 0.7,
                color: 'transparent'
              }}
              eventHandlers={{
                click: (e) => {
                  if (e && e.originalEvent) {
                    L.DomEvent.stopPropagation(e);
                  }
                  setSelectedStopForWatch({
                    routeId: route,
                    stopId: stop.id,
                    stopName: stop.name,
                    stopCoords: [stop.lat, stop.lng]
                  });
                }
              }}
            >
              <Tooltip direction="top" offset={[0, -10]} opacity={1}>
                <div style={{ fontFamily: 'var(--font-ui)', fontWeight: 600 }}>{stop.name}</div>
              </Tooltip>
            </CircleMarker>
          ))
        )}

        {/* Buses */}
        {buses.map(bus => {
          const isHighlighted = selectedDestination && stops[bus.route]?.some(s => s.name.toLowerCase().includes(selectedDestination.toLowerCase()));
          return (
            <LerpingBusMarker
              key={bus.id}
              bus={bus}
              isHighlighted={isHighlighted}
              isDeviated={deviatedBusIds.has(bus.id)}
              routePolyline={tomtomPolylines.get(bus.route)}
              onClick={() => {
                setSelectedBus(bus);
                setShowBoardingModal(false);
                setMapCenter([bus.lat, bus.lng]);
                setMapZoom(16);
              }}
            />
          );
        })}

        {/* H3 Demand Hexagons */}
        {showDemandLayer && demandHexes.map(hex => (
          <Polygon
            key={hex.hex_id}
            positions={hex.boundary.map(pt => [pt[0], pt[1]])}
            pathOptions={HEX_STYLES[hex.level] || HEX_STYLES.low}
            eventHandlers={{
              mouseover: (e) => e.target.openTooltip(),
              mouseout:  (e) => e.target.closeTooltip(),
            }}
          >
            <Tooltip sticky opacity={0.97}>
              <div style={{
                fontFamily: 'var(--font-data)',
                fontSize: '0.78rem',
                color: '#ffffff',
                background: 'var(--color-bg-elevated)',
                padding: '6px 10px',
                borderRadius: '6px',
                border: `1px solid ${
                  hex.level === 'high' ? '#FF4560' : hex.level === 'medium' ? '#FFB800' : 'rgba(0,212,255,0.4)'
                }`,
                whiteSpace: 'nowrap',
              }}>
                <span style={{ fontWeight: 700 }}>Zone demand:</span> {hex.count} passengers · past 10 min
              </div>
            </Tooltip>
          </Polygon>
        ))}

        {/* User Location */}
        <CircleMarker
          center={[userLocation.lat, userLocation.lng]}
          radius={8}
          pathOptions={{
            fillColor: 'var(--color-accent)',
            fillOpacity: 1,
            color: '#fff',
            weight: 3
          }}
        />
      </MapContainer>

      {/* ── H3 Demand Toggle Button ── */}
      <button
        id="demand-heatmap-toggle"
        onClick={() => setShowDemandLayer(v => !v)}
        title={showDemandLayer ? 'Hide Demand Heatmap' : 'Show Demand Heatmap'}
        style={{
          position: 'absolute', top: '24px', right: '24px', zIndex: 1001,
          display: 'flex', alignItems: 'center', gap: '8px',
          justifyContent: 'center',
          width: '240px',
          padding: '10px 16px',
          background: showDemandLayer ? 'var(--color-accent)' : 'var(--color-bg-elevated)',
          border: `1px solid ${showDemandLayer ? 'var(--color-accent)' : 'var(--color-border)'}`,
          borderRadius: '12px',
          color: showDemandLayer ? '#080C14' : 'var(--color-text-secondary)',
          fontFamily: 'var(--font-ui)',
          fontWeight: 700,
          fontSize: '0.82rem',
          cursor: 'pointer',
          boxShadow: showDemandLayer ? 'var(--shadow-accent)' : 'var(--shadow-panel)',
          transition: 'all 0.25s ease',
          letterSpacing: '0.03em',
        }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2" />
        </svg>
        Demand Heatmap {showDemandLayer ? 'ON' : 'OFF'}
      </button>

      {/* ── H3 Demand Legend Panel ── */}
      <div style={{
        position: 'absolute', top: '76px', right: '24px', zIndex: 1001,
        background: 'var(--color-bg-elevated)',
        border: '1px solid var(--color-border)',
        borderRadius: '14px',
        padding: '14px 16px',
        width: '240px',
        boxShadow: 'var(--shadow-panel)',
        transition: 'opacity 0.3s ease',
        opacity: showDemandLayer ? 1 : 0.35,
        pointerEvents: showDemandLayer ? 'auto' : 'none',
      }}>
        <div style={{
          fontFamily: 'var(--font-data)',
          fontSize: '0.68rem',
          fontWeight: 800,
          color: 'var(--color-accent)',
          letterSpacing: '0.12em',
          marginBottom: '10px',
        }}>H3 DEMAND LAYER (res-8, ~460m)</div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '7px', marginBottom: '10px' }}>
          {[
            { level: 'High',   fill: 'rgba(255, 69, 96, 0.35)',   stroke: '#FF4560' },
            { level: 'Medium', fill: 'rgba(255, 184, 0, 0.30)',   stroke: '#FFB800' },
            { level: 'Low',    fill: 'rgba(0, 212, 255, 0.18)',   stroke: 'rgba(0,212,255,0.5)' },
          ].map(({ level, fill, stroke }) => (
            <div key={level} style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <svg width="18" height="16" viewBox="0 0 18 16">
                <polygon
                  points="9,1 17,5 17,11 9,15 1,11 1,5"
                  fill={fill}
                  stroke={stroke}
                  strokeWidth="1.5"
                />
              </svg>
              <span style={{
                fontFamily: 'var(--font-ui)',
                fontSize: '0.8rem',
                color: 'var(--color-text-primary)',
                fontWeight: 600,
              }}>{level}</span>
            </div>
          ))}
        </div>

        <div style={{
          fontFamily: 'var(--font-ui)',
          fontSize: '0.72rem',
          color: 'var(--color-text-secondary)',
          borderTop: '1px solid var(--color-border)',
          paddingTop: '8px',
          lineHeight: 1.4,
        }}>Passenger ping density · 10-min window</div>
      </div>

      {/* ── Search Bar ── */}
      <div style={{
        position: 'absolute', top: '68px', left: '24px', right: '24px', zIndex: 50,
        maxWidth: '560px', margin: '0 auto',
        display: 'none'
      }}>
        <input 
          type="text"
          value={searchQuery}
          onChange={(e) => { setSearchQuery(e.target.value); setShowDropdown(true); setSelectedDestination(null); }}
          onFocus={() => setShowDropdown(true)}
          placeholder={language === 'en' ? "Where do you want to go?" : "எங்கே செல்ல வேண்டும்?"}
          style={{
            width: '100%', padding: '16px 24px', borderRadius: '16px',
            border: '1px solid var(--color-border)', background: 'var(--color-bg-elevated)', 
            color: 'var(--color-text-primary)', fontSize: '1rem', outline: 'none',
            boxShadow: 'var(--shadow-panel)',
            fontFamily: 'var(--font-ui)', transition: 'all 0.3s ease'
          }}
        />
        {showDropdown && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, right: 0, marginTop: '8px',
            background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)',
            borderRadius: '16px', overflow: 'hidden',
            boxShadow: 'var(--shadow-panel)'
          }}>
            {POPULAR_STOPS.map(stop => (
              <div 
                key={stop}
                onClick={() => { setSearchQuery(stop); setSelectedDestination(stop); setShowDropdown(false); }}
                style={{
                  padding: '16px 24px', cursor: 'pointer', fontSize: '0.95rem',
                  borderBottom: '1px solid var(--color-border)', transition: 'background 0.2s',
                  color: 'var(--color-text-primary)', fontFamily: 'var(--font-ui)'
                }}
                onMouseOver={(e) => e.target.style.background = 'var(--color-bg-panel)'}
                onMouseOut={(e) => e.target.style.background = 'transparent'}
              >
                <MapPin size={14} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '6px' }} /> {stop}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Nearby Buses Panel ── */}
      <div style={{
        position: 'absolute', bottom: '0', left: '0', right: '0', zIndex: 999,
        background: 'var(--color-bg-elevated)',
        borderTop: '1px solid var(--color-border)',
        borderTopLeftRadius: '24px', borderTopRightRadius: '24px',
        padding: '24px', transition: 'height 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
        height: nearbyPanelExpanded ? '320px' : '160px',
        display: 'flex', flexDirection: 'column', boxShadow: 'var(--shadow-panel)'
      }}>
        <div 
          onClick={() => setNearbyPanelExpanded(!nearbyPanelExpanded)}
          style={{ width: '48px', height: '6px', background: 'var(--color-border)', borderRadius: '3px', margin: '0 auto 16px', cursor: 'pointer' }}
        />
        <h3 style={{ fontSize: '1.2rem', fontWeight: 800, marginBottom: '16px', color: 'var(--color-text-primary)' }}>
          {language === 'en' ? 'Buses near you' : 'அருகிலுள்ள பேருந்துகள்'}
        </h3>
        
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {nearbyBuses.length > 0 ? nearbyBuses.map(bus => (
            <div key={bus.id} onClick={() => { 
                setSelectedBus(bus); 
                setShowBoardingModal(false);
                setMapCenter([bus.lat, bus.lng]);
                setMapZoom(16);
              }} style={{
              background: 'var(--color-bg-panel)', border: '1px solid var(--color-border)',
              padding: '16px', borderRadius: '16px', display: 'flex', justifyContent: 'space-between',
              alignItems: 'center', cursor: 'pointer', transition: 'all 0.2s',
            }}>
              <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                <div style={{ background: 'var(--color-accent)', color: '#080C14', padding: '6px 12px', borderRadius: '8px', fontWeight: 800, fontSize: '0.85rem' }}>
                  {bus.route}
                </div>
                <div>
                  <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--color-text-primary)' }}>
                    {bus.id}
                    {bus.is_ghost && <span style={{ marginLeft: '6px', fontSize: '0.65rem', color: 'var(--color-ghost-pulse, #FF6B35)', fontWeight: 700, background: 'rgba(255,107,53,0.1)', padding: '2px 6px', borderRadius: '4px' }}>GPS RECOVERING</span>}
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginTop: '4px' }}>
                    Crowding: <span style={{ color: bus.crowding === 'high' ? 'var(--color-danger)' : bus.crowding === 'medium' ? 'var(--color-warning)' : 'var(--color-success)' }}>{bus.crowding}</span>
                  </div>
                </div>
              </div>
              <ETABadge
                eta_minutes={etaData[bus.id]?.eta}
                confidence_pct={etaData[bus.id]?.confidence}
                confidence_label={etaData[bus.id]?.label}
                model={etaData[bus.id]?.model}
              />
            </div>
          )) : (
            <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>
              No buses within 5km. Showing all routes.
            </p>
          )}
        </div>
      </div>

      <BusDetailPanel 
        bus={selectedBus} 
        language={language}
        onClose={() => { setSelectedBus(null); if (onClearFocus) onClearFocus(); }} 
        showBoardingModal={showBoardingModal}
        setShowBoardingModal={setShowBoardingModal}
      />

      {/* ── Watch Stop Prompt (Bottom Sheet) ── */}
      {selectedStopForWatch && (
        <div style={{
          position: 'absolute', bottom: '0', left: '0', right: '0', zIndex: 1000,
          background: 'var(--color-bg-elevated)',
          borderTop: '1px solid var(--color-border)',
          borderTopLeftRadius: '24px', borderTopRightRadius: '24px',
          padding: '24px',
          boxShadow: 'var(--shadow-panel)',
          display: 'flex', flexDirection: 'column', gap: '16px'
        }}>
          <div>
            <h4 style={{ color: 'var(--color-text-primary)', fontSize: '1.2rem', fontWeight: 700, marginBottom: '4px' }}>
              Watch this stop?
            </h4>
            <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>
              Get notified when Route {selectedStopForWatch.routeId} arrives at {selectedStopForWatch.stopName}.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '12px' }}>
            <button 
              onClick={() => setSelectedStopForWatch(null)}
              style={{
                flex: 1, padding: '12px', borderRadius: '12px',
                background: 'var(--color-bg-panel)', border: '1px solid var(--color-border)',
                color: 'var(--color-text-primary)', fontWeight: 600, cursor: 'pointer'
              }}
            >
              Cancel
            </button>
            <button 
              onClick={() => {
                setWatchedStop(selectedStopForWatch);
                setSelectedStopForWatch(null);
                setAlert(null); // Clear previous alerts
              }}
              style={{
                flex: 1, padding: '12px', borderRadius: '12px',
                background: 'var(--color-accent)', border: 'none',
                color: '#080C14', fontWeight: 700, cursor: 'pointer',
                boxShadow: 'var(--shadow-accent)'
              }}
            >
              Watch Stop
            </button>
          </div>
        </div>
      )}

      {/* ── Arrival Alert Notification Bar ── */}
      {alert && (
        <div style={{
          position: 'absolute', bottom: '80px', left: '24px', right: '24px', zIndex: 2000,
          background: 'var(--color-bg-elevated)',
          borderTop: `2px solid ${alert.status === 'arrived' ? 'var(--color-success)' : 'var(--color-accent)'}`,
          borderRadius: '12px',
          padding: '16px',
          boxShadow: '0 10px 30px rgba(0,0,0,0.8)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center'
        }}>
          <div style={{
            fontFamily: 'var(--font-data)',
            color: alert.status === 'arrived' ? 'var(--color-success)' : 'var(--color-text-primary)',
            fontWeight: 700,
            fontSize: '0.95rem'
          }}>
            {alert.message}
          </div>
          <button 
            onClick={() => setAlert(null)}
            style={{
              background: 'transparent', border: 'none', color: 'var(--color-text-secondary)',
              cursor: 'pointer', fontSize: '1.2rem', padding: '0 8px'
            }}
          >
            ×
          </button>
        </div>
      )}
      {/* ── Route Deviation Alert Banner ── */}
      {deviationAlert && (
        <div style={{
          position: 'absolute', bottom: alert ? '148px' : '80px',
          left: '24px', right: '24px', zIndex: 2100,
          background: 'rgba(255, 107, 53, 0.15)',
          borderLeft: '3px solid var(--color-ghost-pulse, #FF6B35)',
          borderRadius: '12px',
          padding: '14px 16px',
          boxShadow: '0 10px 30px rgba(0,0,0,0.6)',
          display: 'flex', gap: '12px', alignItems: 'flex-start',
          backdropFilter: 'blur(8px)',
          animation: 'slideDown 0.3s ease-out',
        }}>
          {/* Icon */}
          <AlertTriangle
            size={20}
            style={{ color: 'var(--color-ghost-pulse, #FF6B35)', flexShrink: 0, marginTop: '2px' }}
          />

          {/* Content */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontFamily: 'var(--font-data)',
              fontWeight: 700,
              fontSize: '0.8rem',
              color: 'var(--color-ghost-pulse, #FF6B35)',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              marginBottom: '4px',
            }}>
              Route Deviation Detected
            </div>
            <div style={{
              fontSize: '0.82rem',
              color: 'var(--color-text-primary)',
              lineHeight: 1.5,
              marginBottom: deviationAlert.next_available_stop ? '10px' : 0,
            }}>
              {deviationAlert.message}
            </div>

            {/* CTA: next available stop */}
            {deviationAlert.next_available_stop && (
              <button
                style={{
                  background: 'transparent',
                  border: '1px solid var(--color-accent)',
                  color: 'var(--color-accent)',
                  borderRadius: '8px',
                  padding: '6px 14px',
                  fontSize: '0.78rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                  fontFamily: 'var(--font-data)',
                  letterSpacing: '0.04em',
                  transition: 'background 0.2s',
                }}
                onMouseEnter={(e) => { e.target.style.background = 'rgba(0,212,255,0.08)'; }}
                onMouseLeave={(e) => { e.target.style.background = 'transparent'; }}
              >
                Move to {deviationAlert.next_available_stop} →
              </button>
            )}
          </div>

          {/* Dismiss */}
          <button
            onClick={dismissAlert}
            style={{
              background: 'transparent', border: 'none',
              color: 'var(--color-text-secondary)',
              cursor: 'pointer', fontSize: '1.2rem', padding: '0 4px',
              flexShrink: 0, lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>
      )}

    </div>
  );
}

function MapUpdater({ center, zoom }) {
  const map = useMap();
  React.useEffect(() => {
    map.setView(center, zoom, { animate: true });
  }, [center, zoom, map]);
  return null;
}

function MapEventsHandler({ onClick }) {
  useMapEvents({
    click: () => {
      onClick();
    }
  });
  return null;
}
