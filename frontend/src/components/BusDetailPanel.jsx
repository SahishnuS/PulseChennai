import React, { useState, useEffect } from 'react';
import { MapPin, Navigation, Ticket, CreditCard, ArrowLeft, ChevronRight, Bus } from 'lucide-react';
import { API_BASE } from '../lib/supabase';
import ETABadge from './ETABadge';
import { getPassengerId } from '../lib/passenger';
import CustomSelect from './CustomSelect';
import { addTicket, generateTicketId } from '../store/ticketStore';

// Mock SVG icons for UPI apps
const GPayIcon = () => (
  <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M43.9 24.5c0-1.7-.1-3.3-.4-4.8H24v9.1h11.2c-.5 3-2.3 5.5-4.8 7.2v6h7.7c4.5-4.2 7.1-10.4 7.1-17.5z" fill="#4285F4"/>
    <path d="M24 44.8c5.6 0 10.3-1.9 13.8-5l-7.7-6c-1.9 1.3-4.3 2-6.1 2-4.7 0-8.7-3.2-10.1-7.5h-8v6.2C9.4 41.5 16.2 44.8 24 44.8z" fill="#34A853"/>
    <path d="M13.9 28.3c-.4-1.1-.6-2.3-.6-3.5s.2-2.4.6-3.5v-6.2h-8C4.5 18 3.8 20.9 3.8 24s.7 6 2 8.8l8.1-4.5z" fill="#FBBC05"/>
    <path d="M24 12.2c3 0 5.7 1 7.9 3.1l5.9-5.9C34.3 6 29.6 4 24 4 16.2 4 9.4 7.3 5.9 13.7l8 6.2c1.4-4.3 5.4-7.7 10.1-7.7z" fill="#EA4335"/>
  </svg>
);

const PhonePeIcon = () => (
  <div style={{ width: 24, height: 24, background: '#5f259f', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontWeight: 'bold', fontSize: '14px', fontFamily: 'sans-serif' }}>P</div>
);

const PaytmIcon = () => (
  <div style={{ width: 24, height: 24, background: '#002970', borderRadius: '4px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#00baf2', fontWeight: 'bold', fontSize: '10px', fontFamily: 'sans-serif' }}>Pay</div>
);

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

export default function BusDetailPanel({ bus, onClose, language, showBoardingModal, setShowBoardingModal }) {
  const [etaData, setEtaData] = useState(null);
  const [etaLoading, setEtaLoading] = useState(false);
  
  // Boarding Flow States
  const [hasActiveTicket, setHasActiveTicket] = useState(false);
  const [stops, setStops] = useState([]);
  const [selectedBoardingStop, setSelectedBoardingStop] = useState('');
  const [selectedDroppingStop, setSelectedDroppingStop] = useState('');
  const [boardingStep, setBoardingStep] = useState(1); // 1: Selection, 2: Payment
  const [selectedPaymentMethod, setSelectedPaymentMethod] = useState('GPay');
  const [boardingLoading, setBoardingLoading] = useState(false);
  const [activeTicketData, setActiveTicketData] = useState(null);
  const [showSuccessModal, setShowSuccessModal] = useState(false);

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
    setBoardingStep(1);
    setSelectedPaymentMethod('GPay');
    setShowSuccessModal(false);

    // Check if user has active ticket
    const pid = getPassengerId();
    fetch(`${API_BASE}/api/passengers/${pid}/tickets`)
      .then(r => r.ok ? r.json() : [])
      .then(data => {
        const active = data.find(t => t.status === 'active');
        if (active) {
          setHasActiveTicket(true);
          setActiveTicketData({
            ...active,
            ticket_id: active.id
          });
        } else {
          setHasActiveTicket(false);
          setActiveTicketData(null);
        }
      })
      .catch(console.error);
      
    // Fetch stops for modal
    fetch(`${API_BASE}/api/stops?route=${bus.route}`)
      .then(r => r.ok ? r.json() : { stops: [] })
      .then(data => {
        const fetchedStops = data.stops || [];
        setStops(fetchedStops);
        if (fetchedStops.length > 0) {
          setSelectedBoardingStop(fetchedStops[0].name);
          setSelectedDroppingStop(fetchedStops[fetchedStops.length - 1].name);
        }
      })
      .catch(console.error);
  }, [bus?.id, bus?.route]);

  useEffect(() => {
    if (showBoardingModal) {
      setBoardingStep(1);
      setSelectedPaymentMethod('GPay');
    }
  }, [showBoardingModal]);

  const getFareDetails = () => {
    const boardingIdx = stops.findIndex(s => s.name === selectedBoardingStop);
    const droppingIdx = stops.findIndex(s => s.name === selectedDroppingStop);
    
    const stopsCount = (boardingIdx !== -1 && droppingIdx !== -1)
      ? Math.max(1, Math.abs(droppingIdx - boardingIdx))
      : 8;
    
    const baseFare = 8;
    const distanceFare = stopsCount * 2;
    const totalFare = baseFare + distanceFare;
    
    return { stopsCount, baseFare, distanceFare, totalFare };
  };

  const handleConfirmStops = () => {
    if (selectedBoardingStop === selectedDroppingStop) {
      return;
    }
    setBoardingStep(2);
  };

  const handleBoard = async () => {
    setBoardingLoading(true);
    const { totalFare } = getFareDetails();

    try {
      const pid = getPassengerId();
      const res = await fetch(`${API_BASE}/api/passengers/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          passenger_id: pid,
          bus_id: bus.id,
          boarding_stop: selectedBoardingStop
        })
      });
      
      let ticketData;
      if (res.ok) {
        ticketData = await res.json();
      } else {
        console.warn("API registration failed, using local mock fallback");
        const mockTicketId = generateTicketId();
        ticketData = {
          ticket_id: mockTicketId,
          route: bus.route,
          bus_id: bus.id,
          boarding_stop: selectedBoardingStop,
          fare_estimate: totalFare
        };
      }

      // Add to local storage ticket list
      const newLocalTicket = {
        id: ticketData.ticket_id || generateTicketId(),
        route: bus.route,
        busId: bus.id,
        fromStop: selectedBoardingStop,
        toStop: selectedDroppingStop,
        fare: totalFare,
        purchasedAt: new Date().toISOString(),
        status: 'active'
      };
      addTicket(newLocalTicket);

      setHasActiveTicket(true);
      setActiveTicketData({
        ...ticketData,
        ticket_id: newLocalTicket.id,
        fromStop: selectedBoardingStop,
        toStop: selectedDroppingStop,
        fare: totalFare
      });
      setShowSuccessModal(true);
      setShowBoardingModal(false);
    } catch (e) {
      console.error(e);
      console.warn("API registration exception, using local mock fallback");
      const mockTicketId = generateTicketId();
      const ticketData = {
        ticket_id: mockTicketId,
        route: bus.route,
        bus_id: bus.id,
        boarding_stop: selectedBoardingStop,
        fare_estimate: totalFare
      };
      
      const newLocalTicket = {
        id: mockTicketId,
        route: bus.route,
        busId: bus.id,
        fromStop: selectedBoardingStop,
        toStop: selectedDroppingStop,
        fare: totalFare,
        purchasedAt: new Date().toISOString(),
        status: 'active'
      };
      addTicket(newLocalTicket);

      setHasActiveTicket(true);
      setActiveTicketData({
        ...ticketData,
        ticket_id: newLocalTicket.id,
        fromStop: selectedBoardingStop,
        toStop: selectedDroppingStop,
        fare: totalFare
      });
      setShowSuccessModal(true);
      setShowBoardingModal(false);
    } finally {
      setBoardingLoading(false);
    }
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
        minHeight: '120px',
        display: 'flex',
        flexDirection: 'column',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            {language === 'en' ? 'ML-Predicted ETA' : 'AI கணிப்பு ETA'}
          </span>
        </div>

        {etaLoading ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            Calculating...
          </div>
        ) : etaData ? (
          <>
            {/* ETABadge: ETA number + confidence arc + confidence label right-aligned */}
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
      </div>

      {/* Boarding Modal */}
      {showBoardingModal && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(8, 12, 20, 0.95)', zIndex: 1010, borderRadius: '16px',
          display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '20px',
          animation: 'fadeIn 0.2s ease-out'
        }}>
          {boardingStep === 1 ? (
            <div style={{ background: 'var(--color-bg-panel)', padding: '20px', borderRadius: '12px', border: '1px solid var(--color-border)' }}>
              <h3 style={{ margin: '0 0 16px 0', fontSize: '1.2rem', fontFamily: 'var(--font-data)' }}>Board {bus.id}</h3>
              
              <div style={{ marginBottom: '12px' }}>
                <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginBottom: '8px' }}>Select Boarding Stop</label>
                <CustomSelect 
                  value={selectedBoardingStop} 
                  onChange={e => setSelectedBoardingStop(e.target.value)}
                  options={stops.length > 0 ? stops.map(s => ({
                    value: s.name,
                    label: s.name
                  })) : [
                    { value: 'Unknown Stop', label: 'Unknown Stop' }
                  ]}
                  buttonStyle={{ background: '#0d1520' }}
                />
              </div>

              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginBottom: '8px' }}>Select Dropping Stop</label>
                <CustomSelect 
                  value={selectedDroppingStop} 
                  onChange={e => setSelectedDroppingStop(e.target.value)}
                  options={stops.length > 0 ? stops.map(s => ({
                    value: s.name,
                    label: s.name
                  })) : [
                    { value: 'Unknown Stop', label: 'Unknown Stop' }
                  ]}
                  buttonStyle={{ background: '#0d1520' }}
                />
              </div>

              {selectedBoardingStop === selectedDroppingStop && (
                <div style={{ color: 'var(--color-danger)', fontSize: '0.75rem', marginBottom: '12px', fontWeight: 600 }}>
                  Boarding and dropping stops cannot be the same.
                </div>
              )}

              <div style={{ background: 'rgba(0,212,255,0.1)', padding: '12px', borderRadius: '8px', marginBottom: '20px' }}>
                <div style={{ fontSize: '0.8rem', color: 'var(--color-accent)' }}>Estimated Fare</div>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, fontFamily: 'var(--font-data)', color: 'var(--color-text-primary)' }}>
                  ₹{getFareDetails().totalFare}
                </div>
              </div>

              <div style={{ display: 'flex', gap: '12px' }}>
                <button onClick={() => setShowBoardingModal(false)} style={{ flex: 1, padding: '10px', background: 'transparent', border: '1px solid var(--color-border)', color: 'white', borderRadius: '8px', cursor: 'pointer' }}>Cancel</button>
                <button 
                  onClick={handleBoard} 
                  disabled={selectedBoardingStop === selectedDroppingStop || boardingLoading}
                  style={{ 
                    flex: 1, padding: '10px', 
                    background: (selectedBoardingStop === selectedDroppingStop || boardingLoading) ? 'var(--color-bg-base)' : 'var(--color-accent)', 
                    border: 'none', 
                    color: (selectedBoardingStop === selectedDroppingStop || boardingLoading) ? 'var(--color-text-muted)' : '#080C14', 
                    borderRadius: '8px', fontWeight: 'bold', cursor: (selectedBoardingStop === selectedDroppingStop || boardingLoading) ? 'not-allowed' : 'pointer',
                    display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px'
                  }}
                >
                  {boardingLoading ? (
                    <>
                      <div className="spinner" style={{ width: '16px', height: '16px', border: '2px solid rgba(8,12,20,0.3)', borderTopColor: '#080C14', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                      Processing...
                    </>
                  ) : (
                    'Confirm'
                  )}
                </button>
              </div>
            </div>
          ) : (
            /* STEP 2: Payment */
            <div style={{ background: 'var(--color-bg-panel)', padding: '20px', borderRadius: '12px', border: '1px solid var(--color-border)', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <button 
                  onClick={() => setBoardingStep(1)}
                  style={{
                    background: 'none', border: 'none', color: 'var(--color-text-primary)',
                    cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    padding: '4px', borderRadius: '50%'
                  }}
                >
                  <ArrowLeft size={20} />
                </button>
                <h3 style={{ margin: 0, fontSize: '1.2rem', fontFamily: 'var(--font-data)' }}>Confirm & Pay</h3>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '8px', border: '1px solid var(--color-border)', fontSize: '0.85rem', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>Route:</span>
                  <span style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>{bus.route}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>From:</span>
                  <span style={{ color: 'var(--color-text-primary)', fontWeight: 600, maxWidth: '180px', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{selectedBoardingStop}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>To:</span>
                  <span style={{ color: 'var(--color-text-primary)', fontWeight: 600, maxWidth: '180px', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{selectedDroppingStop}</span>
                </div>
                <div style={{ height: '1px', background: 'var(--color-border)', margin: '4px 0' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--color-text-primary)', fontWeight: 700 }}>Total Fare:</span>
                  <span style={{ color: 'var(--color-accent)', fontWeight: 800, fontSize: '1.2rem' }}>₹{getFareDetails().totalFare}</span>
                </div>
              </div>

              <div>
                <p style={{ color: 'var(--color-text-secondary)', marginBottom: '8px', fontSize: '0.8rem' }}>Pay via UPI</p>
                <div style={{ display: 'flex', gap: '10px' }}>
                  {['GPay', 'PhonePe', 'Paytm'].map((app) => {
                    const isSelected = selectedPaymentMethod === app;
                    return (
                      <div 
                        key={app} 
                        onClick={() => setSelectedPaymentMethod(app)}
                        style={{
                          flex: 1, padding: '10px 6px', background: '#0d1520', borderRadius: '8px',
                          border: isSelected ? '2px solid var(--color-accent)' : '1px solid var(--color-border)',
                          boxShadow: isSelected ? '0 0 8px rgba(0, 212, 255, 0.15)' : 'none',
                          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px', cursor: 'pointer',
                          transition: 'all 0.2s'
                        }}
                      >
                        {app === 'GPay' && <GPayIcon />}
                        {app === 'PhonePe' && <PhonePeIcon />}
                        {app === 'Paytm' && <PaytmIcon />}
                        <span style={{ color: 'var(--color-text-primary)', fontSize: '0.75rem', fontWeight: 600 }}>{app}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              <button
                onClick={handleBoard}
                disabled={boardingLoading}
                style={{
                  width: '100%', padding: '12px', borderRadius: '8px', border: 'none',
                  background: 'var(--color-accent)', color: '#080C14',
                  fontSize: '1rem', fontWeight: 700, cursor: boardingLoading ? 'wait' : 'pointer',
                  display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px',
                  marginTop: '4px'
                }}
              >
                {boardingLoading ? (
                  <>
                    <div className="spinner" style={{ width: '16px', height: '16px', border: '2px solid rgba(8,12,20,0.3)', borderTopColor: '#080C14', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                    Processing...
                  </>
                ) : (
                  <>
                    <CreditCard size={16} />
                    PAY ₹{getFareDetails().totalFare}
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Success Modal */}
      {showSuccessModal && activeTicketData && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(8, 12, 20, 0.98)', zIndex: 1020, borderRadius: '16px',
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '20px',
          animation: 'fadeIn 0.2s ease-out'
        }}>
          <Ticket size={36} color="var(--color-accent)" style={{ marginBottom: '8px' }} />
          <h2 style={{ fontFamily: 'var(--font-data)', fontSize: '1.2rem', margin: '0 0 16px 0', color: 'var(--color-accent)', fontWeight: 800, letterSpacing: '1px' }}>BOARDING SUCCESS</h2>
          
          <div style={{
            background: 'white', color: '#0F172A', padding: '16px', borderRadius: '12px', width: '100%', 
            boxShadow: '0 10px 25px rgba(0, 212, 255, 0.1)', marginBottom: '16px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px dashed #CBD5E1', paddingBottom: '10px', marginBottom: '10px' }}>
              <div>
                <span style={{ fontSize: '0.65rem', color: '#64748B', fontWeight: 600 }}>TICKET ID</span>
                <div style={{ fontFamily: 'var(--font-data)', fontWeight: 700, fontSize: '0.9rem' }}>{activeTicketData.ticket_id}</div>
              </div>
              <div style={{ background: 'var(--color-accent)', color: '#080C14', padding: '2px 8px', borderRadius: '4px', fontWeight: 800, fontSize: '0.8rem' }}>
                {bus.route}
              </div>
            </div>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <div style={{ flex: 1 }}>
                <span style={{ fontSize: '0.6rem', color: '#64748B' }}>FROM</span>
                <div style={{ fontSize: '0.8rem', fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{activeTicketData.fromStop || selectedBoardingStop}</div>
              </div>
              <div style={{ padding: '0 8px', color: '#94A3B8' }}><ChevronRight size={14} /></div>
              <div style={{ flex: 1, textAlign: 'right' }}>
                <span style={{ fontSize: '0.6rem', color: '#64748B' }}>TO</span>
                <div style={{ fontSize: '0.8rem', fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{activeTicketData.toStop || selectedDroppingStop}</div>
              </div>
            </div>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '8px', borderTop: '1px solid #E2E8F0' }}>
              <div>
                <span style={{ fontSize: '0.6rem', color: '#64748B' }}>BUS</span>
                <div style={{ fontSize: '0.8rem', fontWeight: 700 }}>{bus.id}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <span style={{ fontSize: '0.6rem', color: '#64748B' }}>FARE</span>
                <div style={{ fontSize: '0.95rem', fontWeight: 800, color: 'var(--color-bg-base)' }}>₹{activeTicketData.fare ?? 18}</div>
              </div>
            </div>
            
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: '12px' }}>
              <svg width="60" height="60" viewBox="0 0 100 100" style={{ background: 'white' }}>
                <path d="M0 0h30v30H0zM10 10h10v10H10zM70 0h30v30H70zM80 10h10v10H80zM0 70h30v30H0zM10 80h10v10H10zM40 0h20v20H40zM50 30h20v20H50zM20 50h20v20H20zM60 60h20v20H60zM40 80h20v20H40zM80 80h20v20H80z" fill="black" />
              </svg>
            </div>
          </div>
          
          <button 
            onClick={() => { 
              setShowSuccessModal(false);
              setActiveTicketData(null); 
              if (onClose) onClose(); 
            }} 
            style={{ 
              width: '100%',
              background: 'var(--color-accent)', 
              border: 'none', 
              color: '#080C14', 
              padding: '12px', 
              borderRadius: '8px', 
              cursor: 'pointer',
              fontWeight: 700,
              fontSize: '0.9rem'
            }}
          >
            Done
          </button>
        </div>
      )}
    </div>
  );
}
