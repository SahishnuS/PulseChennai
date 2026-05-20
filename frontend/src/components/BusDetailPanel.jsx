import React, { useState, useEffect } from 'react';
import { MapPin, Navigation, Ticket } from 'lucide-react';
import { API_BASE } from '../lib/supabase';
import ETABadge from './ETABadge';
import { getPassengerId } from '../lib/passenger';

function computeLocalETA(busLat, busLng, dstLat, dstLng, speedKmph) {
  // Haversine distance
  const R = 6371;
  const dLat = (dstLat - busLat) * Math.PI / 180;
  const dLng = (dstLng - busLng) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 + Math.cos(busLat*Math.PI/180) * Math.cos(dstLat*Math.PI/180) * Math.sin(dLng/2)**2;
  const distKm = R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a)) * 1.35; // Chennai road correction

  const hour = new Date().getHours();
  let avgSpeed;
  if (speedKmph && speedKmph > 2) {
    avgSpeed = speedKmph;
  } else if ((hour >= 8 && hour <= 10) || (hour >= 17 && hour <= 20)) {
    avgSpeed = 14;
  } else if (hour >= 12 && hour <= 14) {
    avgSpeed = 25;
  } else if (hour >= 22 || hour <= 5) {
    avgSpeed = 45;
  } else {
    avgSpeed = 32;
  }

  return {
    eta_min: Math.max(1, Math.round((distKm / avgSpeed) * 60 * 0.85)),
    eta_max: Math.max(2, Math.round((distKm / avgSpeed) * 60 * 1.2)),
    distance_km: Math.round(distKm * 100) / 100,
    method: 'Local Calculation',
    confidence: speedKmph > 0 ? 'medium' : 'low',
  };
}

export default function BusDetailPanel({ bus, onClose, language }) {
  const [etaData, setEtaData] = useState(null);
  const [etaLoading, setEtaLoading] = useState(false);
  
  // Boarding Flow States
  const [hasActiveTicket, setHasActiveTicket] = useState(false);
  const [showBoardingModal, setShowBoardingModal] = useState(false);
  const [stops, setStops] = useState([]);
  const [selectedStop, setSelectedStop] = useState('');
  const [boardingLoading, setBoardingLoading] = useState(false);
  const [activeTicketData, setActiveTicketData] = useState(null);

  useEffect(() => {
    if (!bus) { setEtaData(null); return; }

    const fetchETA = async () => {
      setEtaLoading(true);
      try {
        // Try backend ML-powered ETA
        const res = await fetch(
          `${API_BASE}/api/eta?src=${bus.lat},${bus.lng}&dst=13.0338,80.2326`
        );
        if (res.ok) {
          const data = await res.json();
          if (data.eta) {
            setEtaData({
              eta_min: Math.max(1, Math.round((data.eta.best_eta_minutes || 0) * 0.85)),
              eta_max: Math.max(2, Math.round((data.eta.best_eta_minutes || 0) * 1.15)),
              best_eta: data.eta.best_eta_minutes,
              distance_km: data.eta.distance_km,
              method: data.eta.method_used || 'ML Prediction',
              confidence_pct:   data.confidence_pct   ?? Math.round((data.eta.confidence ?? 0.72) * 97),
              confidence_label: data.confidence_label ?? (data.eta.confidence > 0.85 ? 'HIGH' : data.eta.confidence > 0.6 ? 'MODERATE' : 'LOW'),
              traffic_delay: data.eta.traffic_delay_minutes,
              arrival_time: data.eta.arrival_time,
              source: data.eta.source_data || 'ML + TomTom',
            });
            setEtaLoading(false);
            return;
          }
        }
      } catch (e) { /* fall through to local */ }

      // Fallback: local time-of-day calculation
      const local = computeLocalETA(bus.lat, bus.lng, 13.0338, 80.2326, bus.speed || 0);
      setEtaData({
        ...local,
        confidence_pct:   local.confidence === 'high' ? 78 : local.confidence === 'medium' ? 58 : 38,
        confidence_label: local.confidence === 'high' ? 'HIGH' : local.confidence === 'medium' ? 'MODERATE' : 'LOW',
      });
      setEtaLoading(false);
    };

    fetchETA();
    const interval = setInterval(fetchETA, 30000);
    return () => clearInterval(interval);
  }, [bus?.id, bus?.lat, bus?.lng]);

  useEffect(() => {
    if (!bus) return;
    // Check if user has active ticket
    const pid = getPassengerId();
    fetch(`${API_BASE}/api/passengers/${pid}/tickets`)
      .then(r => r.ok ? r.json() : [])
      .then(data => {
        const active = data.find(t => t.status === 'active');
        if (active) {
          setHasActiveTicket(true);
          setActiveTicketData(active);
        }
      })
      .catch(console.error);
      
    // Fetch stops for modal
    fetch(`${API_BASE}/api/stops?route=${bus.route}`)
      .then(r => r.ok ? r.json() : { stops: [] })
      .then(data => {
        setStops(data.stops || []);
        if (data.stops && data.stops.length > 0) setSelectedStop(data.stops[0].stop_name);
      })
      .catch(console.error);
  }, [bus?.id, bus?.route]);

  const handleBoard = async () => {
    setBoardingLoading(true);
    try {
      const pid = getPassengerId();
      const res = await fetch(`${API_BASE}/api/passengers/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          passenger_id: pid,
          bus_id: bus.id,
          boarding_stop: selectedStop
        })
      });
      if (res.ok) {
        const data = await res.json();
        setHasActiveTicket(true);
        setActiveTicketData(data);
        setShowBoardingModal(false);
      }
    } catch (e) {
      console.error(e);
    }
    setBoardingLoading(false);
  };

  if (!bus) return null;

  return (
    <div style={{
      position: 'absolute',
      bottom: '16px',
      left: '16px',
      zIndex: 1000,
      background: 'var(--color-bg-panel)',
      border: '1px solid var(--color-border)',
      borderRadius: '16px',
      padding: '20px',
      width: '360px',
      boxShadow: 'var(--shadow-panel)',
      animation: 'slideDown 0.3s ease-out',
      display: 'flex',
      flexDirection: 'column',
      gap: '14px'
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span style={{
              background: 'var(--accent)',
              color: 'white',
              padding: '4px 8px',
              borderRadius: '6px',
              fontWeight: 800,
              fontSize: '1.2rem'
            }}>
              {bus.route}
            </span>
            <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', fontWeight: 600 }}>
              {bus.id}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', color: bus.is_ghost ? 'var(--ghost-orange)' : 'var(--success)' }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: bus.is_ghost ? 'var(--ghost-orange)' : 'var(--success)' }} />
            {bus.is_ghost ? (language === 'en' ? 'Signal Lost (Ghost Mode)' : 'சமிக்ஞை இல்லை') : (language === 'en' ? 'Live GPS Tracking' : 'நேரடி கண்காணிப்பு')}
          </div>
        </div>
        <button onClick={onClose} style={{
          background: 'var(--bg-tertiary)', border: 'none', color: 'var(--text-primary)',
          width: '28px', height: '28px', borderRadius: '50%', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center'
        }}>
          ✕
        </button>
      </div>

      {/* Live Metrics */}
      <div style={{ display: 'flex', gap: '12px' }}>
        <div style={{ flex: 1, background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '8px', border: '1px solid var(--color-border)' }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--color-text-secondary)', marginBottom: '4px' }}>SPEED</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--color-text-primary)' }}>{bus.speed?.toFixed(0)} km/h</div>
        </div>
        <div style={{ flex: 1, background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '8px', border: '1px solid var(--color-border)' }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--color-text-secondary)', marginBottom: '4px' }}>CROWDING</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 600, color: bus.crowding === 'high' ? 'var(--color-danger)' : 'var(--color-success)' }}>
            {bus.crowding?.toUpperCase()}
          </div>
        </div>
      </div>

      {/* ML ETA Prediction */}
      <div style={{
        background: 'linear-gradient(135deg, rgba(59,130,246,0.08), rgba(6,182,212,0.08))',
        border: '1px solid rgba(59,130,246,0.2)',
        borderRadius: '12px',
        padding: '16px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            {language === 'en' ? 'ML-Predicted ETA' : 'AI கணிப்பு ETA'}
          </span>
        </div>

        {etaLoading ? (
          <div style={{ textAlign: 'center', padding: '8px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            Calculating...
          </div>
        ) : etaData ? (
          <>
            {/* ETABadge: ETA number + confidence arc */}
            <div style={{ marginBottom: '10px' }}>
              <ETABadge
                eta_minutes={etaData.best_eta ?? ((etaData.eta_min + etaData.eta_max) / 2)}
                confidence_pct={etaData.confidence_pct ?? 55}
                confidence_label={etaData.confidence_label ?? 'MODERATE'}
              />
            </div>
            <div style={{ display: 'flex', gap: '12px', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
              {etaData.distance_km && <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><MapPin size={12} /> {etaData.distance_km} km</span>}
              {etaData.traffic_delay > 0 && (
                <span style={{ color: 'var(--color-warning)', display: 'flex', alignItems: 'center', gap: '4px' }}><Navigation size={12} /> +{etaData.traffic_delay} min delay</span>
              )}
            </div>
            <div style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)', marginTop: '6px', opacity: 0.7 }}>
              {etaData.source || etaData.method}
            </div>
          </>
        ) : (
          <div style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>ETA unavailable</div>
        )}
      </div>

      {/* Ticket Pricing */}
      <div style={{ borderTop: '1px dashed var(--border)', paddingTop: '14px' }}>
        <h4 style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '10px' }}>
          {language === 'en' ? 'Estimated Ticket Pricing' : 'மதிப்பிடப்பட்ட டிக்கெட் விலை'}
        </h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
            <span>MTC Ordinary</span>
            <span style={{ fontWeight: 600 }}>₹5 - ₹20</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
            <span>MTC Deluxe</span>
            <span style={{ fontWeight: 600, color: 'var(--accent-green)' }}>₹11 - ₹48</span>
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div style={{ display: 'flex', gap: '12px', marginTop: '2px' }}>
        <button style={{
          flex: 1, background: 'var(--color-bg-elevated)', color: 'var(--color-text-primary)',
          border: '1px solid var(--color-border)', padding: '12px', borderRadius: '8px',
          fontWeight: 600, cursor: 'pointer', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px'
        }}>
          <Navigation size={18} />
          Track
        </button>
        {!hasActiveTicket ? (
          <button 
            onClick={() => setShowBoardingModal(true)}
            style={{
              flex: 2, background: 'var(--color-accent)', color: '#080C14',
              border: 'none', padding: '12px', borderRadius: '8px',
              fontWeight: 700, cursor: 'pointer', transition: 'opacity 0.2s', boxShadow: 'var(--shadow-accent)',
              display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px'
            }}>
            <Ticket size={18} />
            BOARD THIS BUS
          </button>
        ) : (
          <button style={{
              flex: 2, background: 'var(--color-success)', color: '#080C14',
              border: 'none', padding: '12px', borderRadius: '8px',
              fontWeight: 700, cursor: 'not-allowed', opacity: 0.9,
              display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px'
          }}>
            TICKET ACTIVE
          </button>
        )}
      </div>

      {/* Boarding Modal */}
      {showBoardingModal && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.8)', zIndex: 1010, borderRadius: '16px',
          display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '20px',
          animation: 'fadeIn 0.2s ease-out'
        }}>
          <div style={{ background: 'var(--color-bg-panel)', padding: '20px', borderRadius: '12px', border: '1px solid var(--color-border)' }}>
            <h3 style={{ margin: '0 0 16px 0', fontSize: '1.2rem', fontFamily: 'var(--font-data)' }}>Board {bus.id}</h3>
            
            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginBottom: '8px' }}>Select Boarding Stop</label>
              <select 
                value={selectedStop} 
                onChange={e => setSelectedStop(e.target.value)}
                style={{ width: '100%', padding: '10px', background: 'var(--color-bg-elevated)', color: 'white', border: '1px solid var(--color-border)', borderRadius: '8px' }}
              >
                {stops.length > 0 ? stops.map(s => (
                  <option key={s.stop_id} value={s.stop_name}>{s.stop_name}</option>
                )) : (
                  <option value="Unknown Stop">Unknown Stop</option>
                )}
              </select>
            </div>

            <div style={{ background: 'rgba(0,212,255,0.1)', padding: '12px', borderRadius: '8px', marginBottom: '20px' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--color-accent)' }}>Estimated Fare</div>
              <div style={{ fontSize: '1.2rem', fontWeight: 700, fontFamily: 'var(--font-data)' }}>₹14 – ₹32 depending on destination</div>
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button onClick={() => setShowBoardingModal(false)} style={{ flex: 1, padding: '10px', background: 'transparent', border: '1px solid var(--color-border)', color: 'white', borderRadius: '8px', cursor: 'pointer' }}>Cancel</button>
              <button onClick={handleBoard} disabled={boardingLoading} style={{ flex: 1, padding: '10px', background: 'var(--color-accent)', border: 'none', color: '#080C14', borderRadius: '8px', fontWeight: 'bold', cursor: 'pointer' }}>
                {boardingLoading ? 'Confirming...' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Success Modal */}
      {hasActiveTicket && activeTicketData && !showBoardingModal && activeTicketData.ticket_id && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.9)', zIndex: 1020, borderRadius: '16px',
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '20px',
          animation: 'fadeIn 0.2s ease-out'
        }}>
          <Ticket size={48} color="var(--color-accent)" style={{ marginBottom: '16px' }} />
          <h2 style={{ fontFamily: 'var(--font-data)', margin: '0 0 8px 0', color: 'var(--color-accent)' }}>BOARDING SUCCESS</h2>
          <div style={{ fontSize: '1.2rem', fontFamily: 'var(--font-data)', letterSpacing: '2px', marginBottom: '24px' }}>{activeTicketData.ticket_id}</div>
          
          <svg width="120" height="120" viewBox="0 0 100 100" style={{ background: 'white', padding: '10px', borderRadius: '8px', marginBottom: '24px' }}>
            {/* Simple generic QR SVG pattern */}
            <path d="M0 0h30v30H0zM10 10h10v10H10zM70 0h30v30H70zM80 10h10v10H80zM0 70h30v30H0zM10 80h10v10H10zM40 0h20v20H40zM50 30h20v20H50zM20 50h20v20H20zM60 60h20v20H60zM40 80h20v20H40zM80 80h20v20H80z" fill="black" />
          </svg>

          <button onClick={() => setActiveTicketData(null)} style={{ background: 'transparent', border: '1px solid var(--color-border)', color: 'white', padding: '10px 24px', borderRadius: '20px', cursor: 'pointer' }}>Close</button>
        </div>
      )}
    </div>
  );
}

