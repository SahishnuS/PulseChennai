import React, { useState, useEffect } from 'react';
import { API_BASE } from '../lib/supabase';

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
              confidence: data.eta.confidence > 0.85 ? 'high' : data.eta.confidence > 0.6 ? 'medium' : 'low',
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
      setEtaData(local);
      setEtaLoading(false);
    };

    fetchETA();
    const interval = setInterval(fetchETA, 30000);
    return () => clearInterval(interval);
  }, [bus?.id, bus?.lat, bus?.lng]);

  if (!bus) return null;

  const confColor = etaData?.confidence === 'high' ? '#22C55E'
    : etaData?.confidence === 'medium' ? '#F59E0B' : '#EF4444';
  const confIcon = etaData?.confidence === 'high' ? '✅'
    : etaData?.confidence === 'medium' ? '⚠️' : '👻';

  return (
    <div style={{
      position: 'absolute',
      bottom: '16px',
      left: '16px',
      zIndex: 1000,
      background: 'var(--bg-secondary)',
      border: '1px solid var(--border)',
      borderRadius: '16px',
      padding: '20px',
      width: '360px',
      boxShadow: '0 12px 40px rgba(0,0,0,0.6)',
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
        <div style={{ flex: 1, background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '8px', border: '1px solid var(--border)' }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>SPEED</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>{bus.speed?.toFixed(0)} km/h</div>
        </div>
        <div style={{ flex: 1, background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '8px', border: '1px solid var(--border)' }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>CROWDING</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 600, color: bus.crowding === 'high' ? 'var(--danger)' : 'var(--success)' }}>
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
          <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            {language === 'en' ? '⚡ ML-Predicted ETA' : '⚡ AI கணிப்பு ETA'}
          </span>
          {etaData && (
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: '4px',
              background: 'rgba(0,0,0,0.2)', padding: '2px 8px', borderRadius: '12px',
              fontSize: '0.7rem', fontWeight: 600, color: confColor,
            }}>
              {confIcon} {etaData.confidence}
            </span>
          )}
        </div>

        {etaLoading ? (
          <div style={{ textAlign: 'center', padding: '8px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            Calculating...
          </div>
        ) : etaData ? (
          <>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginBottom: '6px' }}>
              <span style={{
                fontSize: '2.2rem', fontWeight: 800,
                background: 'linear-gradient(135deg, #3B82F6, #06B6D4)',
                WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
              }}>
                {etaData.best_eta ? Math.round(etaData.best_eta) : `${etaData.eta_min}–${etaData.eta_max}`}
              </span>
              <span style={{ fontSize: '1rem', color: 'var(--text-secondary)', fontWeight: 500 }}>min</span>
              {etaData.arrival_time && (
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>
                  Arrives ~{etaData.arrival_time}
                </span>
              )}
            </div>
            <div style={{ display: 'flex', gap: '12px', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {etaData.distance_km && <span>📍 {etaData.distance_km} km</span>}
              {etaData.traffic_delay > 0 && (
                <span style={{ color: '#F59E0B' }}>🚦 +{etaData.traffic_delay} min delay</span>
              )}
            </div>
            <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: '6px', opacity: 0.7 }}>
              {etaData.source || etaData.method}
            </div>
          </>
        ) : (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>ETA unavailable</div>
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
          flex: 1, background: 'var(--accent)', color: 'white',
          border: 'none', padding: '12px', borderRadius: '8px',
          fontWeight: 600, cursor: 'pointer', transition: 'opacity 0.2s'
        }}>
          Track This Bus
        </button>
        <button style={{
          flex: 1, background: 'var(--bg-tertiary)', color: 'white',
          border: '1px solid var(--border)', padding: '12px', borderRadius: '8px',
          fontWeight: 600, cursor: 'pointer'
        }}>
          Set as My Bus
        </button>
      </div>
    </div>
  );
}

