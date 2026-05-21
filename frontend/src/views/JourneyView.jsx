import React, { useState, useEffect } from 'react';
import { MapPin, Bell, Gauge, Radio, Navigation, Eye } from 'lucide-react';
import { INITIAL_BUSES } from '../services/busSimulator';
import CustomSelect from '../components/CustomSelect';

// ── Hardcoded route data (Prompt 4 spec) ──
const ROUTE_DATA = {
  "19": {
    name: "Thiruporur ↔ T Nagar",
    color: "#00D4FF",
    stops: ["Thiruporur", "Navalur", "Sholinganallur", "Perungudi", "Taramani", "Velachery", "Saidapet", "T Nagar"],
    frequency: "Every 10 min",
    firstService: "05:00",
    lastService: "23:00",
  },
  "102X": {
    name: "Kelambakkam ↔ Broadway",
    color: "#00E5A0",
    stops: ["Kelambakkam", "Siruseri", "Sholinganallur", "Perungudi", "Adyar", "Saidapet", "Guindy", "Park Town", "Broadway"],
    frequency: "Every 12 min",
    firstService: "05:30",
    lastService: "22:30",
  },
  "515": {
    name: "Tambaram ↔ Mamallapuram",
    color: "#FFB800",
    stops: ["Tambaram", "Perungalathur", "Vandalur", "Mudichur", "Maraimalai Nagar", "Kovalam", "Mamallapuram"],
    frequency: "Every 20 min",
    firstService: "06:00",
    lastService: "21:00",
  },
  "21C": {
    name: "Koyambedu ↔ Adyar",
    color: "#FF6B35",
    stops: ["Koyambedu", "Vadapalani", "Ashok Nagar", "Anna Nagar", "Kodambakkam", "Nandanam", "Adyar"],
    frequency: "Every 8 min",
    firstService: "05:00",
    lastService: "23:30",
  },
  "70": {
    name: "Central ↔ Ambattur",
    color: "#C084FC",
    stops: ["Central", "Egmore", "Kilpauk", "Aminjikarai", "Shenoy Nagar", "Anna Nagar West", "Perambur", "Ambattur"],
    frequency: "Every 15 min",
    firstService: "05:30",
    lastService: "22:00",
  },
  "47A": {
    name: "T Nagar ↔ Chromepet",
    color: "#F472B6",
    stops: ["T Nagar", "Saidapet", "Guindy", "St. Thomas Mount", "Palavanthangal", "Chromepet"],
    frequency: "Every 18 min",
    firstService: "06:00",
    lastService: "21:30",
  },
};

export default function JourneyView({ language, onTrackBus }) {
  const [selectedRoute, setSelectedRoute] = useState('19');
  const [selectedStopIdx, setSelectedStopIdx] = useState(null);
  const [watchedStopLocal, setWatchedStopLocal] = useState(() => {
    try { return JSON.parse(localStorage.getItem('watched_stop')); } catch { return null; }
  });
  const [alertDist, setAlertDist] = useState('400m');

  const routeMeta = ROUTE_DATA[selectedRoute];
  const routeStops = routeMeta?.stops || [];

  // Count buses from INITIAL_BUSES
  const countBuses = (routeId) => INITIAL_BUSES.filter(b => b.route === routeId).length;
  const routeBuses = INITIAL_BUSES.filter(b => b.route === selectedRoute);

  const handleWatchStop = () => {
    if (selectedStopIdx === null) return;
    const data = { route: selectedRoute, stop: routeStops[selectedStopIdx], distance: alertDist };
    localStorage.setItem('watched_stop', JSON.stringify(data));
    setWatchedStopLocal(data);
  };

  return (
    <div style={{
      height: '100%', display: 'flex',
      background: 'var(--color-bg-base)', overflow: 'hidden',
    }}>
      {/* ── Left Column: Route Selector ── */}
      <div style={{
        width: '280px', flexShrink: 0,
        borderRight: '1px solid var(--color-border)',
        overflowY: 'auto', padding: '16px 0',
        background: 'var(--color-bg-panel)',
      }}>
        {Object.entries(ROUTE_DATA).map(([routeId, meta]) => {
          const isSelected = selectedRoute === routeId;
          return (
            <button
              key={routeId}
              onClick={() => { setSelectedRoute(routeId); setSelectedStopIdx(null); }}
              style={{
                width: '100%', textAlign: 'left',
                padding: '14px 16px', cursor: 'pointer',
                border: 'none', background: 'transparent',
                borderLeft: isSelected ? `4px solid ${meta.color}` : '4px solid transparent',
                transition: 'all 0.15s',
              }}
              onMouseOver={e => { if (!isSelected) e.currentTarget.style.background = 'rgba(255,255,255,0.03)'; }}
              onMouseOut={e => { if (!isSelected) e.currentTarget.style.background = 'transparent'; }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
                <span style={{
                  fontFamily: 'var(--font-data)', fontWeight: 800,
                  fontSize: '1.1rem', color: meta.color,
                }}>
                  {routeId}
                </span>
                <span style={{
                  fontSize: '0.7rem', color: 'var(--color-text-muted)',
                  background: 'rgba(255,255,255,0.05)',
                  padding: '2px 6px', borderRadius: '4px',
                  fontFamily: 'var(--font-data)',
                }}>
                  {countBuses(routeId)} active
                </span>
              </div>
              <p style={{ fontSize: '0.82rem', color: 'var(--color-text-secondary)', margin: 0 }}>
                {meta.name}
              </p>
            </button>
          );
        })}
      </div>

      {/* ── Right Column: Route Detail ── */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px' }}>
        {/* Route Header */}
        <div style={{ marginBottom: '28px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '8px' }}>
            <span style={{
              fontFamily: 'var(--font-data)', fontWeight: 800,
              fontSize: '1.5rem', color: routeMeta.color,
              background: `${routeMeta.color}15`, padding: '6px 16px',
              borderRadius: '8px', border: `1px solid ${routeMeta.color}30`,
            }}>
              {selectedRoute}
            </span>
            <div>
              <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--color-text-primary)', margin: 0 }}>
                {routeMeta.name}
              </h2>
              <div style={{ display: 'flex', gap: '16px', marginTop: '4px' }}>
                <span style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>{routeMeta.frequency}</span>
                <span style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>{routeMeta.firstService} – {routeMeta.lastService}</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── Stop Timeline ── */}
        <div style={{ position: 'relative', paddingLeft: '32px', marginBottom: '32px' }}>
          {/* Vertical line */}
          <div style={{
            position: 'absolute', left: '14px', top: '8px',
            bottom: '8px', width: '2px',
            background: routeMeta.color, opacity: 0.6,
          }} />

          {routeStops.map((stop, index) => {
            const isFirst = index === 0;
            const isLast = index === routeStops.length - 1;
            const isSelected = selectedStopIdx === index;
            const isWatched = watchedStopLocal?.route === selectedRoute && watchedStopLocal?.stop === stop;
            const etaFromStart = index * 4; // 4 min per stop
            const nextBusMin = index * 3 + 2;

            return (
              <div
                key={`${selectedRoute}-${stop}-${index}`}
                onClick={() => setSelectedStopIdx(index)}
                style={{
                  position: 'relative',
                  padding: '10px 16px 10px 24px',
                  marginBottom: '2px',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  background: isSelected ? 'rgba(0,212,255,0.05)' : 'transparent',
                  border: isSelected ? '1px solid rgba(0,212,255,0.15)' : '1px solid transparent',
                  transition: 'all 0.15s',
                }}
                onMouseOver={e => { if (!isSelected) e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; }}
                onMouseOut={e => { if (!isSelected) e.currentTarget.style.background = isSelected ? 'rgba(0,212,255,0.05)' : 'transparent'; }}
              >
                {/* Circle node */}
                <div style={{
                  position: 'absolute', left: '-22px', top: '14px',
                  width: '10px', height: '10px', borderRadius: '50%',
                  border: `2px solid ${routeMeta.color}`,
                  background: (isFirst || isLast) ? routeMeta.color : 'transparent',
                  zIndex: 1,
                  boxShadow: isWatched ? `0 0 8px var(--color-warning)` : 'none',
                }} />

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <p style={{
                      fontSize: '0.9rem', fontWeight: isSelected ? 700 : 500,
                      color: 'var(--color-text-primary)', margin: 0,
                    }}>
                      {stop}
                      {isWatched && <Eye size={12} style={{ marginLeft: '6px', verticalAlign: 'middle', color: 'var(--color-warning)' }} />}
                    </p>
                    <p style={{
                      fontSize: '0.75rem', color: 'var(--color-text-muted)',
                      margin: '2px 0 0', fontFamily: 'var(--font-data)',
                    }}>
                      Stop {index + 1} of {routeStops.length} — ~{etaFromStart} min from start
                    </p>
                  </div>
                  <span style={{
                    fontSize: '0.8rem', fontWeight: 600,
                    fontFamily: 'var(--font-data)',
                    color: routeMeta.color,
                    flexShrink: 0,
                  }}>
                    +{nextBusMin}min
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* ── Watch a Stop ── */}
        <div style={{
          padding: '20px', background: 'var(--color-bg-panel)',
          borderRadius: '12px', border: '1px solid var(--color-border)',
          marginBottom: '28px',
        }}>
          <p style={{
            fontSize: '10px', fontWeight: 700, color: 'var(--color-text-muted)',
            fontFamily: 'var(--font-data)', letterSpacing: '1.5px', marginBottom: '14px',
          }}>
            GET NOTIFIED WHEN BUS ARRIVES
          </p>

          <CustomSelect
            value={selectedStopIdx !== null ? selectedStopIdx : ''}
            onChange={e => setSelectedStopIdx(e.target.value !== '' ? parseInt(e.target.value) : null)}
            options={[
              { value: '', label: 'Select a stop...' },
              ...routeStops.map((s, i) => ({ value: i, label: s }))
            ]}
            buttonStyle={{ background: 'var(--color-bg-base)', marginBottom: '12px' }}
          />

          {/* Alert distance radio buttons */}
          <div style={{ display: 'flex', gap: '12px', marginBottom: '14px' }}>
            {['400m away', 'At the stop'].map(opt => (
              <label key={opt} style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                cursor: 'pointer', fontSize: '0.85rem',
                color: alertDist === opt ? 'var(--color-accent)' : 'var(--color-text-secondary)',
              }}>
                <input
                  type="radio" name="alertDist"
                  checked={alertDist === opt}
                  onChange={() => setAlertDist(opt)}
                  style={{ accentColor: 'var(--color-accent)' }}
                />
                {opt}
              </label>
            ))}
          </div>

          <button
            onClick={handleWatchStop}
            disabled={selectedStopIdx === null}
            style={{
              width: '100%', padding: '12px', borderRadius: '8px',
              border: selectedStopIdx !== null ? '1px solid var(--color-accent)' : '1px solid var(--color-border)',
              background: 'transparent',
              color: selectedStopIdx !== null ? 'var(--color-accent)' : 'var(--color-text-muted)',
              fontSize: '0.9rem', fontWeight: 700,
              cursor: selectedStopIdx !== null ? 'pointer' : 'not-allowed',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
              transition: 'all 0.2s',
            }}
          >
            <Bell size={16} />
            WATCH STOP
          </button>

          {watchedStopLocal && watchedStopLocal.route === selectedRoute && (
            <div style={{
              marginTop: '12px', padding: '10px',
              background: 'rgba(0,229,160,0.08)', borderRadius: '6px',
              border: '1px solid rgba(0,229,160,0.2)',
              fontSize: '0.8rem', color: 'var(--color-success)',
            }}>
              Watching {watchedStopLocal.stop} on Route {watchedStopLocal.route}
            </div>
          )}
        </div>

        {/* ── Active Buses for This Route ── */}
        <div>
          <p style={{
            fontSize: '10px', fontWeight: 700, color: 'var(--color-text-muted)',
            fontFamily: 'var(--font-data)', letterSpacing: '1.5px', marginBottom: '14px',
          }}>
            ACTIVE BUSES — ROUTE {selectedRoute}
          </p>

          {routeBuses.length === 0 && (
            <p style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>
              No active buses on this route
            </p>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {routeBuses.map(bus => (
              <div
                key={bus.id}
                style={{
                  padding: '16px', background: 'var(--color-bg-panel)',
                  borderRadius: '12px',
                  border: bus.isGhost
                    ? '1px solid var(--color-ghost-pulse, #FF6B35)'
                    : '1px solid var(--color-border)',
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <span style={{ fontFamily: 'var(--font-data)', fontWeight: 700, fontSize: '0.9rem', color: 'var(--color-text-primary)' }}>
                    {bus.id}
                  </span>
                  <span style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
                    {bus.speed_kmh} km/h
                  </span>
                  <span style={{
                    fontSize: '0.7rem', padding: '2px 8px', borderRadius: '4px',
                    background: bus.crowding === 'high' ? 'rgba(255,69,96,0.1)' : bus.crowding === 'medium' ? 'rgba(255,184,0,0.1)' : 'rgba(0,229,160,0.1)',
                    color: bus.crowding === 'high' ? 'var(--color-danger)' : bus.crowding === 'medium' ? 'var(--color-warning)' : 'var(--color-success)',
                    fontWeight: 600, textTransform: 'uppercase',
                  }}>
                    {bus.crowding}
                  </span>
                  {bus.isGhost && (
                    <span style={{
                      fontSize: '0.65rem', fontWeight: 700,
                      color: 'var(--color-ghost-pulse, #FF6B35)',
                      background: 'rgba(255,107,53,0.1)',
                      padding: '2px 8px', borderRadius: '4px',
                      display: 'flex', alignItems: 'center', gap: '4px',
                    }}>
                      <Radio size={10} /> GPS RECOVERING
                    </span>
                  )}
                </div>

                <button
                  onClick={() => { if (onTrackBus) onTrackBus(bus.id); }}
                  style={{
                    padding: '6px 14px', borderRadius: '6px', cursor: 'pointer',
                    border: '1px solid var(--color-border)', background: 'transparent',
                    color: 'var(--color-text-primary)', fontSize: '0.78rem', fontWeight: 600,
                    display: 'flex', alignItems: 'center', gap: '6px', transition: 'all 0.15s',
                  }}
                  onMouseOver={e => { e.currentTarget.style.borderColor = routeMeta.color; e.currentTarget.style.color = routeMeta.color; }}
                  onMouseOut={e => { e.currentTarget.style.borderColor = 'var(--color-border)'; e.currentTarget.style.color = 'var(--color-text-primary)'; }}
                >
                  <Navigation size={12} /> TRACK ON MAP
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
