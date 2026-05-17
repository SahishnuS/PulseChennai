import React, { useState, useEffect, useRef } from 'react';
import { API_BASE } from '../lib/supabase';

export default function JourneyView({ language }) {
  const [buses, setBuses] = useState([]);
  const [stops, setStops] = useState([]);
  const [selectedBus, setSelectedBus] = useState('');
  const [selectedStop, setSelectedStop] = useState('');
  const [watching, setWatching] = useState(false);
  const [eta, setEta] = useState(null);
  const [showArrival, setShowArrival] = useState(false);
  const arrivalDismissed = useRef(false);
  const sessionId = useRef(crypto.randomUUID());

  // Fetch buses
  useEffect(() => {
    const fetchBuses = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/buses`);
        const data = await res.json();
        setBuses(data.buses || []);
      } catch (e) { /* ignore */ }
    };
    fetchBuses();
    const interval = setInterval(fetchBuses, 10000);
    return () => clearInterval(interval);
  }, []);

  // Fetch stops when bus changes
  useEffect(() => {
    if (!selectedBus) { setStops([]); return; }
    const bus = buses.find(b => b.id === selectedBus);
    if (!bus) return;

    const fetchStops = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/stops?route=${bus.route}`);
        const data = await res.json();
        setStops(data.stops || []);
      } catch (e) { /* ignore */ }
    };
    fetchStops();
  }, [selectedBus, buses]);

  // Live ETA polling when watching
  useEffect(() => {
    if (!watching || !selectedBus || !selectedStop) return;

    const fetchEta = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/buses/${selectedBus}/eta?stop_id=${selectedStop}`);
        const data = await res.json();
        setEta(data);

        // Alert trigger at ≤3 min
        if (data.eta_min <= 3 && !arrivalDismissed.current) {
          triggerArrivalAlert(data);
        }
      } catch (e) { /* ignore */ }
    };

    fetchEta();
    const interval = setInterval(fetchEta, 10000);
    return () => clearInterval(interval);
  }, [watching, selectedBus, selectedStop]);

  const triggerArrivalAlert = (etaData) => {
    setShowArrival(true);

    // Voice alert
    const stopObj = stops.find(s => s.id === selectedStop);
    const stopName = language === 'ta' && stopObj?.name_ta ? stopObj.name_ta : stopObj?.name || selectedStop;

    const msg = language === 'ta'
      ? `கவனிக்கவும்! உங்கள் நிறுத்தம் ${stopName} வருகிறது. இறங்க தயாராகுங்கள்.`
      : `Attention! Your stop ${stopName} is approaching. Please get ready to exit the bus.`;

    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(msg);
      utterance.lang = language === 'ta' ? 'ta-IN' : 'en-IN';
      utterance.rate = 0.9;
      window.speechSynthesis.speak(utterance);
    }

    // Vibrate
    if (navigator.vibrate) {
      navigator.vibrate([200, 100, 200, 100, 400]);
    }

    // Browser notification
    if (Notification.permission === 'granted') {
      new Notification(language === 'en' ? 'Get ready! Your stop is coming up' : 'தயாராகுங்கள்! உங்கள் நிறுத்தம் வருகிறது');
    } else if (Notification.permission !== 'denied') {
      Notification.requestPermission();
    }
  };

  const startWatching = async () => {
    if (!selectedBus || !selectedStop) return;
    arrivalDismissed.current = false;
    setWatching(true);

    // Register with backend
    try {
      await fetch(`${API_BASE}/api/journey/watch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId.current,
          bus_id: selectedBus,
          target_stop_id: selectedStop,
        }),
      });
    } catch (e) { /* ignore */ }
  };

  const stopWatching = () => {
    setWatching(false);
    setEta(null);
    setShowArrival(false);
  };

  const dismissArrival = () => {
    setShowArrival(false);
    arrivalDismissed.current = true;
  };

  const selectedBusObj = buses.find(b => b.id === selectedBus);
  const selectedStopObj = stops.find(s => s.id === selectedStop);

  // Calculate stop progress
  const busStopIndex = selectedBusObj?.stop_index || 0;
  const targetStopSequence = selectedStopObj?.sequence || 0;
  const stopsAway = Math.max(0, targetStopSequence - busStopIndex - 1);
  const totalStops = stops.length;
  const progressPercent = totalStops > 0 ? Math.min(100, ((busStopIndex + 1) / totalStops) * 100) : 0;

  return (
    <div style={{
      height: '100%',
      overflowY: 'auto',
      padding: '20px 16px',
      background: '#0F172A',
    }}>
      {/* ── Arrival Overlay ── */}
      {showArrival && (
        <div className="arrival-overlay" onClick={dismissArrival}>
          <div style={{ fontSize: '4rem', marginBottom: '16px' }}>🚨</div>
          <h1 style={{ fontSize: '2rem', fontWeight: 800, marginBottom: '8px' }}>
            {language === 'en' ? 'Get Ready!' : 'தயாராகுங்கள்!'}
          </h1>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 600, marginBottom: '24px' }}>
            {language === 'ta' && selectedStopObj?.name_ta ? selectedStopObj.name_ta : selectedStopObj?.name || 'Your stop'} {language === 'en' ? 'is next' : 'அடுத்ததாக வருகிறது'}
          </h2>
          <p style={{ opacity: 0.8, fontSize: '0.9rem' }}>
            {language === 'en' ? 'Tap to dismiss' : 'நிராகரிக்க தட்டவும்'}
          </p>
        </div>
      )}

      {!watching ? (
        /* ── Selection Mode ── */
        <div style={{ maxWidth: '400px', margin: '0 auto' }}>
          <h2 style={{ fontSize: '1.3rem', fontWeight: 700, marginBottom: '24px', textAlign: 'center' }}>
            {language === 'en' ? '🎯 Track My Journey' : '🎯 என் பயணத்தை கண்காணி'}
          </h2>

          {/* Bus selector */}
          <label style={{ display: 'block', marginBottom: '8px', color: '#94A3B8', fontSize: '0.85rem' }}>
            {language === 'en' ? "I'm on this bus:" : 'நான் இந்த பேருந்தில் இருக்கிறேன்:'}
          </label>
          <select
            value={selectedBus}
            onChange={e => { setSelectedBus(e.target.value); setSelectedStop(''); }}
            style={{
              width: '100%', padding: '14px 16px', borderRadius: '12px',
              border: '1px solid #334155', background: '#1E293B', color: '#F8FAFC',
              fontSize: '1rem', marginBottom: '20px', outline: 'none',
              fontFamily: 'Inter, sans-serif',
            }}
          >
            <option value="">{language === 'en' ? 'Select a bus...' : 'பேருந்து தேர்ந்தெடுக்கவும்...'}</option>
            {buses.map(bus => (
              <option key={bus.id} value={bus.id}>
                {bus.route} — {bus.id} {bus.is_ghost ? '(Ghost)' : ''}
              </option>
            ))}
          </select>

          {/* Stop selector */}
          <label style={{ display: 'block', marginBottom: '8px', color: '#94A3B8', fontSize: '0.85rem' }}>
            {language === 'en' ? 'I want to get off at:' : 'நான் இறங்க விரும்புகிறேன்:'}
          </label>
          <select
            value={selectedStop}
            onChange={e => setSelectedStop(e.target.value)}
            disabled={!selectedBus}
            style={{
              width: '100%', padding: '14px 16px', borderRadius: '12px',
              border: '1px solid #334155', background: '#1E293B', color: '#F8FAFC',
              fontSize: '1rem', marginBottom: '24px', outline: 'none',
              opacity: selectedBus ? 1 : 0.5,
              fontFamily: 'Inter, sans-serif',
            }}
          >
            <option value="">{language === 'en' ? 'Select your stop...' : 'நிறுத்தம் தேர்ந்தெடுக்கவும்...'}</option>
            {stops.map(stop => (
              <option key={stop.id} value={stop.id}>
                {language === 'ta' ? stop.name_ta : stop.name}
              </option>
            ))}
          </select>

          {/* Start button */}
          <button
            onClick={startWatching}
            disabled={!selectedBus || !selectedStop}
            style={{
              width: '100%', padding: '16px', borderRadius: '14px',
              border: 'none', cursor: selectedBus && selectedStop ? 'pointer' : 'not-allowed',
              background: selectedBus && selectedStop ? 'linear-gradient(135deg, #3B82F6, #2563EB)' : '#334155',
              color: 'white', fontSize: '1.1rem', fontWeight: 700,
              transition: 'all 0.2s',
              fontFamily: 'Inter, sans-serif',
              boxShadow: selectedBus && selectedStop ? '0 4px 16px rgba(59, 130, 246, 0.3)' : 'none',
            }}
          >
            {language === 'en' ? '🔔 START WATCHING' : '🔔 கண்காணிக்க தொடங்கு'}
          </button>
        </div>
      ) : (
        /* ── Watching Mode ── */
        <div style={{ maxWidth: '400px', margin: '0 auto' }}>
          {/* Header */}
          <div style={{
            padding: '16px', borderRadius: '14px', background: '#1E293B',
            marginBottom: '16px', textAlign: 'center',
          }}>
            <p style={{ color: '#94A3B8', fontSize: '0.8rem', marginBottom: '4px' }}>
              {language === 'en' ? 'Watching' : 'கண்காணிக்கிறது'}
            </p>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>
              {selectedBusObj?.route} → {language === 'ta' && selectedStopObj?.name_ta ? selectedStopObj.name_ta : selectedStopObj?.name}
            </h3>
          </div>

          {/* ETA Display */}
          {eta && (
            <div style={{
              padding: '24px', borderRadius: '16px',
              background: 'var(--bg-secondary)',
              border: `1px solid ${eta.is_ghost ? 'var(--ghost-orange)' : 'var(--border)'}`,
              boxShadow: eta.is_ghost ? '0 0 20px rgba(249, 115, 22, 0.2)' : '0 12px 32px rgba(0,0,0,0.3)',
              marginBottom: '16px', textAlign: 'center', position: 'relative', overflow: 'hidden'
            }}>
              {eta.is_ghost && (
                <div style={{ position: 'absolute', top: 0, left: 0, right: 0, background: 'var(--ghost-orange)', color: 'white', fontSize: '0.75rem', fontWeight: 700, padding: '4px' }}>
                  {language === 'en' ? 'GHOST MODE (ESTIMATED)' : 'மதிப்பீட்டு நிலை'}
                </div>
              )}
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', marginBottom: '8px', marginTop: eta.is_ghost ? '20px' : '0' }}>
                {language === 'en' ? 'Arriving in' : 'வருகை'}
              </p>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                <h2 style={{ fontSize: '3rem', fontWeight: 800, color: 'var(--text-primary)', margin: 0, lineHeight: 1 }}>
                  {eta.eta_min}
                </h2>
                <span style={{ fontSize: '1.5rem', color: 'var(--text-muted)' }}>-</span>
                <h2 style={{ fontSize: '3rem', fontWeight: 800, color: 'var(--text-primary)', margin: 0, lineHeight: 1 }}>
                  {eta.eta_max}
                </h2>
              </div>
              <p style={{ fontSize: '1rem', color: 'var(--text-secondary)', fontWeight: 500, marginTop: '4px' }}>
                {language === 'en' ? 'minutes' : 'நிமிடங்கள்'}
              </p>

              {/* Confidence Badge */}
              <div style={{
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                gap: '6px', marginTop: '16px', background: 'var(--bg-primary)',
                padding: '6px 12px', borderRadius: '20px', border: '1px solid var(--border)'
              }}>
                {eta.confidence === 'high' && <span style={{ color: 'var(--success)' }}>✅</span>}
                {eta.confidence === 'medium' && <span style={{ color: 'var(--warning)' }}>⚠️</span>}
                {eta.confidence === 'low' && <span style={{ color: 'var(--danger)' }}>👻</span>}
                <span style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', fontWeight: 600 }}>
                  {eta.confidence === 'low'
                    ? (language === 'en' ? 'Signal lost' : 'சமிக்ஞை இல்லை')
                    : (language === 'en' ? `Confidence: ${eta.confidence}` : `நம்பகம்: ${eta.confidence}`)
                  }
                </span>
              </div>
            </div>
          )}

          <div style={{ display: 'flex', gap: '16px', marginBottom: '16px' }}>
            {/* Progress bar */}
            <div style={{
              flex: 1, padding: '16px', borderRadius: '16px', background: 'var(--bg-secondary)', border: '1px solid var(--border)'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                <span style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                  {language === 'en' ? 'Route Progress' : 'வழி முன்னேற்றம்'}
                </span>
                <span style={{ color: 'var(--text-primary)', fontSize: '0.8rem', fontWeight: 700 }}>
                  {stopsAway} {language === 'en' ? 'stops' : 'நிறுத்தங்கள்'}
                </span>
              </div>
              <div style={{ height: '8px', background: 'var(--bg-tertiary)', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{
                  height: '100%', width: `${progressPercent}%`,
                  background: 'linear-gradient(90deg, var(--accent), var(--accent-green))',
                  borderRadius: '4px', transition: 'width 0.5s ease',
                }} />
              </div>
            </div>

            {/* Ticket Estimate */}
            <div style={{
              width: '120px', padding: '16px', borderRadius: '16px', background: 'var(--bg-secondary)', border: '1px solid var(--border)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center'
            }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '8px', textAlign: 'center' }}>
                {language === 'en' ? 'Est. Ticket' : 'டிக்கெட்'}
              </div>
              <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--accent-green)' }}>
                ₹{5 + Math.min(15, stopsAway * 2)}
              </div>
            </div>
          </div>

          {/* Crowding */}
          {selectedBusObj && (
            <div style={{
              padding: '16px', borderRadius: '14px', background: '#1E293B',
              marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '12px',
            }}>
              <div style={{
                width: '12px', height: '12px', borderRadius: '50%',
                background: selectedBusObj.crowding === 'high' ? '#EF4444'
                  : selectedBusObj.crowding === 'medium' ? '#F59E0B' : '#22C55E',
              }} />
              <span style={{ color: '#F8FAFC', fontSize: '0.9rem' }}>
                {language === 'en' ? 'Crowding' : 'நெரிசல்'}: {selectedBusObj.crowding || 'low'}
              </span>
            </div>
          )}

          {/* Stop button */}
          <button
            onClick={stopWatching}
            style={{
              width: '100%', padding: '14px', borderRadius: '14px',
              border: '1px solid #EF4444', background: 'transparent',
              color: '#EF4444', fontSize: '1rem', fontWeight: 600,
              cursor: 'pointer', fontFamily: 'Inter, sans-serif',
            }}
          >
            {language === 'en' ? '⏹ Stop Watching' : '⏹ கண்காணிப்பை நிறுத்து'}
          </button>
        </div>
      )}
    </div>
  );
}
