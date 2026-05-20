import React, { useState, useEffect } from 'react';
import { MapPin, Bus, CreditCard, Ticket, Search, X, CheckCircle, ChevronRight, Clock } from 'lucide-react';
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

export default function PlanTripModal({ isOpen, onClose, onTrackBus, language }) {
  const [step, setStep] = useState(1);
  const [stops, setStops] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDestination, setSelectedDestination] = useState(null);
  
  // Payment states
  const [isPaying, setIsPaying] = useState(false);
  
  // Ticket states
  const [ticket, setTicket] = useState(null);
  const [selectedRoute, setSelectedRoute] = useState(null);

  // Hardcoded stops from all 6 routes (Prompt 3 spec)
  const ALL_STOPS = [
    'Thiruporur', 'Velachery', 'T Nagar', 'Kelambakkam', 'Sholinganallur',
    'Adyar', 'Broadway', 'Tambaram', 'Mamallapuram', 'Koyambedu',
    'Vadapalani', 'Egmore', 'Perambur', 'Ambattur', 'Guindy',
    'Chromepet', 'Park Town', 'Anna Salai', 'Navalur', 'Perungudi',
    'Taramani', 'Saidapet', 'Siruseri', 'Nandanam', 'Ashok Nagar',
  ].sort();

  useEffect(() => {
    if (!isOpen) return;
    setStops(ALL_STOPS);
    setStep(1);
    setSearchQuery('');
    setSelectedDestination(null);
    setSelectedRoute(null);
    setTicket(null);
  }, [isOpen]);

  if (!isOpen) return null;

  const filteredStops = stops.filter(s => s.toLowerCase().includes(searchQuery.toLowerCase()));

  const handleFindRoutes = () => {
    if (!selectedDestination) return;
    setStep(2);
  };

  const handleSelectRoute = (route) => {
    setSelectedRoute(route);
    setStep(3);
  };

  const handlePay = () => {
    setIsPaying(true);
    setTimeout(() => {
      setIsPaying(false);
      const newTicket = {
        id: generateTicketId(),
        route: selectedRoute.routeId,
        busId: `BUS_${selectedRoute.routeId.replace(/\s/g, '')}_001`,
        fromStop: 'Chennai Central',
        toStop: selectedDestination,
        fare: selectedRoute.fare,
        purchasedAt: new Date().toISOString(),
        status: 'active',
        eta_minutes: selectedRoute.duration,
      };

      addTicket(newTicket);
      setTicket(newTicket);
      setStep(4);
    }, 1500);
  };

  const handleTrackBus = () => {
    onTrackBus(ticket.busId);
    onClose();
  };

  // Mock routes generation based on destination
  const mockRoutes = [
    {
      id: 'r1',
      routeId: '19',
      name: 'Thiruporur Fast',
      stopsCount: 8,
      duration: 34,
      fare: 8 * 2 + 8, // 24
      eta: 4,
      crowding: 'low',
      recommended: true
    },
    {
      id: 'r2',
      routeId: '102X',
      name: 'OMR Express',
      stopsCount: 12,
      duration: 45,
      fare: 12 * 2 + 8, // 32
      eta: 12,
      crowding: 'medium',
      recommended: false
    }
  ];

  const getCrowdingColor = (level) => {
    if (level === 'low') return 'var(--color-success)';
    if (level === 'medium') return 'var(--color-warning)';
    return 'var(--color-danger)';
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(8,12,20,0.95)',
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      display: 'flex', flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{ padding: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: '8px' }}>
          {[1, 2, 3, 4].map(s => (
            <div key={s} style={{
              width: '40px', height: '4px', borderRadius: '2px',
              background: s <= step ? 'var(--color-accent)' : 'var(--color-border)',
              transition: 'background 0.3s'
            }} />
          ))}
        </div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--color-text-secondary)', cursor: 'pointer' }}>
          <X size={28} />
        </button>
      </div>

      {/* Main Content Container with sliding transition */}
      <div style={{
        flex: 1, overflowY: 'auto', padding: '0 24px',
        display: 'flex', flexDirection: 'column', alignItems: 'center'
      }}>
        <div style={{
          width: '100%', maxWidth: '480px',
          animation: 'slideLeft 0.3s ease-out forwards',
          // Keyframes are in index.css or injected. We'll just rely on a simple transform if we don't have the keyframe.
          // Since we can't easily inject keyframes here, we'll just use a subtle fade-in.
        }}>
          
          {/* STEP 1: Selection */}
          {step === 1 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              <h2 style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--color-text-primary)' }}>
                {language === 'en' ? 'Where are you going?' : 'எங்கே செல்ல வேண்டும்?'}
              </h2>
              
              <div style={{ background: 'var(--color-bg-panel)', padding: '20px', borderRadius: '16px', border: '1px solid var(--color-border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '16px' }}>
                  <MapPin size={24} color="var(--color-accent)" />
                  <div style={{ flex: 1 }}>
                    <p style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginBottom: '4px' }}>FROM</p>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <p style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--color-text-primary)' }}>Chennai Central</p>
                      <span style={{ fontSize: '0.7rem', padding: '2px 6px', background: 'rgba(0, 212, 255, 0.1)', color: 'var(--color-accent)', borderRadius: '4px', fontWeight: 700 }}>DETECTED</span>
                    </div>
                  </div>
                </div>
                
                <div style={{ height: '1px', background: 'var(--color-border)', margin: '0 0 16px 40px' }} />
                
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px' }}>
                  <Search size={24} color="var(--color-text-muted)" style={{ marginTop: '8px' }} />
                  <div style={{ flex: 1 }}>
                    <p style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginBottom: '4px' }}>TO</p>
                    {selectedDestination ? (
                      <div 
                        onClick={() => setSelectedDestination(null)}
                        style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--color-text-primary)', padding: '8px 0', cursor: 'pointer' }}
                      >
                        {selectedDestination}
                      </div>
                    ) : (
                      <>
                        <input
                          type="text"
                          value={searchQuery}
                          onChange={e => setSearchQuery(e.target.value)}
                          placeholder="Search destination..."
                          style={{
                            width: '100%', background: 'transparent', border: 'none',
                            color: 'var(--color-text-primary)', fontSize: '1.1rem', outline: 'none', padding: '8px 0'
                          }}
                        />
                        {searchQuery && (
                          <div style={{ maxHeight: '200px', overflowY: 'auto', marginTop: '8px', borderTop: '1px solid var(--color-border)' }}>
                            {filteredStops.map(stop => (
                              <div
                                key={stop}
                                onClick={() => setSelectedDestination(stop)}
                                style={{ padding: '12px 0', borderBottom: '1px solid var(--color-border)', cursor: 'pointer', color: 'var(--color-text-primary)' }}
                              >
                                {stop}
                              </div>
                            ))}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              </div>

              <button
                onClick={handleFindRoutes}
                disabled={!selectedDestination}
                style={{
                  width: '100%', padding: '16px', borderRadius: '12px', border: 'none',
                  background: selectedDestination ? 'var(--color-accent)' : 'var(--color-bg-panel)',
                  color: selectedDestination ? '#080C14' : 'var(--color-text-muted)',
                  fontSize: '1.1rem', fontWeight: 700, cursor: selectedDestination ? 'pointer' : 'not-allowed',
                  transition: 'all 0.2s', marginTop: 'auto'
                }}
              >
                Find Routes
              </button>
            </div>
          )}

          {/* STEP 2: Routes */}
          {step === 2 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <h2 style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--color-text-primary)' }}>
                Select Route
              </h2>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {mockRoutes.map(route => (
                  <div key={route.id} style={{
                    background: 'var(--color-bg-panel)', borderRadius: '16px',
                    border: route.recommended ? '1px solid var(--color-accent)' : '1px solid var(--color-border)',
                    overflow: 'hidden', position: 'relative'
                  }}>
                    {route.recommended && (
                      <div style={{ background: 'var(--color-accent)', color: '#080C14', fontSize: '0.7rem', fontWeight: 800, padding: '4px 12px', display: 'inline-block', borderBottomRightRadius: '8px' }}>
                        RECOMMENDED
                      </div>
                    )}
                    <div style={{ padding: '20px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <div style={{ background: 'var(--color-accent)', color: '#080C14', padding: '4px 12px', borderRadius: '8px', fontWeight: 800, fontSize: '1.1rem' }}>
                            {route.routeId}
                          </div>
                          <span style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>{route.name}</span>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <span style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--color-text-primary)' }}>₹{route.fare}</span>
                        </div>
                      </div>

                      <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.9rem', marginBottom: '16px' }}>
                        Chennai Central <ChevronRight size={14} style={{ verticalAlign: 'middle' }}/> {selectedDestination}
                        <span style={{ color: 'var(--color-text-muted)', marginLeft: '8px' }}>via {route.stopsCount} stops</span>
                      </p>

                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.03)', padding: '12px', borderRadius: '8px', marginBottom: '16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <Clock size={16} color="var(--color-text-secondary)" />
                          <span style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>{route.duration} min trip</span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <Bus size={16} color="var(--color-text-secondary)" />
                          <span style={{ color: 'var(--color-accent)', fontWeight: 700 }}>In {route.eta} min</span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: getCrowdingColor(route.crowding) }} />
                          <span style={{ color: 'var(--color-text-secondary)', fontSize: '0.85rem', textTransform: 'capitalize' }}>{route.crowding}</span>
                        </div>
                      </div>

                      <button
                        onClick={() => handleSelectRoute(route)}
                        style={{
                          width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid var(--color-border)',
                          background: 'transparent', color: 'var(--color-text-primary)',
                          fontSize: '1rem', fontWeight: 600, cursor: 'pointer',
                          transition: 'all 0.2s'
                        }}
                        onMouseOver={e => { e.target.style.background = 'var(--color-border)'; }}
                        onMouseOut={e => { e.target.style.background = 'transparent'; }}
                      >
                        Select This Route
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* STEP 3: Payment */}
          {step === 3 && selectedRoute && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              <h2 style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--color-text-primary)' }}>
                Confirm & Pay
              </h2>

              <div style={{ background: 'var(--color-bg-panel)', padding: '24px', borderRadius: '16px', border: '1px solid var(--color-border)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>Route</span>
                  <span style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>{selectedRoute.routeId} {selectedRoute.name}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>From</span>
                  <span style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>Chennai Central</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '24px' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>To</span>
                  <span style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>{selectedDestination}</span>
                </div>

                <div style={{ height: '1px', background: 'var(--color-border)', marginBottom: '24px' }} />

                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>Base Fare</span>
                  <span style={{ color: 'var(--color-text-primary)' }}>₹8</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '24px' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>Distance ({selectedRoute.stopsCount} stops)</span>
                  <span style={{ color: 'var(--color-text-primary)' }}>₹{selectedRoute.stopsCount * 2}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--color-text-primary)', fontSize: '1.2rem', fontWeight: 700 }}>Total Fare</span>
                  <span style={{ color: 'var(--color-accent)', fontSize: '1.8rem', fontWeight: 800 }}>₹{selectedRoute.fare}</span>
                </div>
              </div>

              <div>
                <p style={{ color: 'var(--color-text-secondary)', marginBottom: '12px', fontSize: '0.9rem' }}>Pay via UPI</p>
                <div style={{ display: 'flex', gap: '16px' }}>
                  {['GPay', 'PhonePe', 'Paytm'].map((app, idx) => (
                    <div key={app} style={{
                      flex: 1, padding: '16px', background: 'var(--color-bg-panel)', borderRadius: '12px',
                      border: idx === 0 ? '2px solid var(--color-accent)' : '1px solid var(--color-border)',
                      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', cursor: 'pointer'
                    }}>
                      {idx === 0 && <GPayIcon />}
                      {idx === 1 && <PhonePeIcon />}
                      {idx === 2 && <PaytmIcon />}
                      <span style={{ color: 'var(--color-text-primary)', fontSize: '0.8rem', fontWeight: 600 }}>{app}</span>
                    </div>
                  ))}
                </div>
              </div>

              <button
                onClick={handlePay}
                disabled={isPaying}
                style={{
                  width: '100%', padding: '16px', borderRadius: '12px', border: 'none',
                  background: 'var(--color-accent)', color: '#080C14',
                  fontSize: '1.1rem', fontWeight: 700, cursor: isPaying ? 'wait' : 'pointer',
                  display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '12px',
                  marginTop: '16px'
                }}
              >
                {isPaying ? (
                  <>
                    <div className="spinner" style={{ width: '20px', height: '20px', border: '3px solid rgba(8,12,20,0.3)', borderTopColor: '#080C14', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                    Processing...
                  </>
                ) : (
                  <>
                    <CreditCard size={20} />
                    PAY ₹{selectedRoute.fare}
                  </>
                )}
              </button>
            </div>
          )}

          {/* STEP 4: Digital Ticket */}
          {step === 4 && ticket && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', alignItems: 'center' }}>
              
              <div style={{
                width: '100%', background: 'white', borderRadius: '24px', overflow: 'hidden',
                boxShadow: '0 20px 40px rgba(0,212,255,0.15)', color: '#0F172A'
              }}>
                {/* Ticket Top */}
                <div style={{ padding: '24px', background: '#F8FAFC', borderBottom: '2px dashed #CBD5E1', position: 'relative' }}>
                  <div style={{ position: 'absolute', bottom: '-12px', left: '-12px', width: '24px', height: '24px', background: 'rgba(8,12,20,0.95)', borderRadius: '50%' }} />
                  <div style={{ position: 'absolute', bottom: '-12px', right: '-12px', width: '24px', height: '24px', background: 'rgba(8,12,20,0.95)', borderRadius: '50%' }} />
                  
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                    <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#0F172A', letterSpacing: '-0.5px' }}>PULSE TRANSIT</h3>
                    <span style={{ fontSize: '0.8rem', color: '#64748B', fontWeight: 600 }}>{new Date(ticket.purchasedAt).toLocaleDateString()}</span>
                  </div>

                  <div style={{ textAlign: 'center', marginBottom: '8px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ flex: 1, textAlign: 'left' }}>
                        <p style={{ fontSize: '0.75rem', color: '#64748B', fontWeight: 600, marginBottom: '4px' }}>FROM</p>
                        <p style={{ fontSize: '1.2rem', fontWeight: 800, lineHeight: 1.2 }}>CHN<br/>CEN</p>
                      </div>
                      <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                        <div style={{ background: '#0EA5E9', color: 'white', padding: '4px 12px', borderRadius: '16px', fontWeight: 800, fontSize: '1rem', marginBottom: '8px' }}>
                          {ticket.route}
                        </div>
                        <Bus size={20} color="#0EA5E9" />
                      </div>
                      <div style={{ flex: 1, textAlign: 'right' }}>
                        <p style={{ fontSize: '0.75rem', color: '#64748B', fontWeight: 600, marginBottom: '4px' }}>TO</p>
                        <p style={{ fontSize: '1.2rem', fontWeight: 800, lineHeight: 1.2 }}>{(ticket.toStop || '').substring(0, 3).toUpperCase()}<br/>{(ticket.toStop || '').substring(3, 6).toUpperCase()}</p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Ticket Bottom */}
                <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', marginBottom: '24px' }}>
                    <div>
                      <p style={{ fontSize: '0.75rem', color: '#64748B', fontWeight: 600 }}>FARE</p>
                      <p style={{ fontSize: '1.5rem', fontWeight: 800, color: '#0F172A' }}>₹{ticket.fare}</p>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <p style={{ fontSize: '0.75rem', color: '#64748B', fontWeight: 600 }}>ASSIGNED BUS</p>
                      <p style={{ fontSize: '1.1rem', fontWeight: 700, color: '#0F172A' }}>{ticket.busId}</p>
                    </div>
                  </div>

                  {/* SVG Fake QR Pattern */}
                  <svg width="120" height="120" viewBox="0 0 120 120" style={{ marginBottom: '16px' }}>
                    <rect width="120" height="120" fill="#F8FAFC" rx="8" />
                    {/* Generative pattern based on ticket id string length/chars */}
                    {Array.from({ length: 64 }).map((_, i) => {
                      const row = Math.floor(i / 8);
                      const col = i % 8;
                      const isDark = (ticket.id.charCodeAt(i % ticket.id.length) * (i + 1)) % 2 === 0;
                      // add alignment squares
                      if ((row < 2 && col < 2) || (row < 2 && col > 5) || (row > 5 && col < 2)) {
                        return <rect key={i} x={col * 15} y={row * 15} width="15" height="15" fill="#0F172A" />;
                      }
                      return isDark ? <rect key={i} x={col * 15 + 2} y={row * 15 + 2} width="11" height="11" fill="#0F172A" rx="2" /> : null;
                    })}
                  </svg>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#10B981', boxShadow: '0 0 8px #10B981', animation: 'pulse 2s infinite' }} />
                    <span style={{ color: '#10B981', fontWeight: 700, letterSpacing: '1px' }}>ACTIVE TICKET</span>
                  </div>
                  <p style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '1.1rem', fontWeight: 600, color: '#475569' }}>
                    {ticket.id}
                  </p>
                </div>
              </div>

              <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <button
                  onClick={handleTrackBus}
                  style={{
                    width: '100%', padding: '16px', borderRadius: '12px', border: 'none',
                    background: 'var(--color-accent)', color: '#080C14',
                    fontSize: '1.1rem', fontWeight: 700, cursor: 'pointer',
                    display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px'
                  }}
                >
                  <MapPin size={20} />
                  TRACK MY BUS
                </button>
                <button
                  onClick={onClose}
                  style={{
                    width: '100%', padding: '16px', borderRadius: '12px', border: '1px solid var(--color-border)',
                    background: 'transparent', color: 'var(--color-text-primary)',
                    fontSize: '1.1rem', fontWeight: 700, cursor: 'pointer',
                  }}
                >
                  DONE
                </button>
              </div>

            </div>
          )}

        </div>
      </div>
      <style>{`
        @keyframes slideLeft {
          from { transform: translateX(20px); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @keyframes pulse {
          0% { opacity: 1; }
          50% { opacity: 0.5; }
          100% { opacity: 1; }
        }
      `}</style>
    </div>
  );
}
