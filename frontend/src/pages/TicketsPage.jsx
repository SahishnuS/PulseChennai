import React, { useState, useEffect } from 'react';
import { Ticket, ArrowRight, Clock, Navigation } from 'lucide-react';
import { API_BASE } from '../lib/supabase';
import { getPassengerId } from '../lib/passenger';

const ROUTE_COLORS = {
  '19': '#10B981',   // Emerald
  '102X': '#F59E0B', // Amber
  '515': '#3B82F6',  // Blue
};

function formatDateTime(isoString) {
  if (!isoString) return '';
  const d = new Date(isoString);
  return d.toLocaleString('en-IN', { 
    month: 'short', day: 'numeric', 
    hour: 'numeric', minute: '2-digit', hour12: true 
  });
}

function calculateDuration(start, end) {
  if (!start || !end) return '';
  const diffMs = new Date(end) - new Date(start);
  const diffMins = Math.floor(diffMs / 60000);
  const h = Math.floor(diffMins / 60);
  const m = diffMins % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function getCrowdColor(crowding) {
  switch(crowding) {
    case 'high': return 'var(--color-danger)';
    case 'medium': return 'var(--color-warning)';
    case 'low': return 'var(--color-success)';
    default: return 'var(--color-text-muted)';
  }
}

export default function TicketsPage({ onTrackBus }) {
  const [tickets, setTickets] = useState([]);
  const [filter, setFilter] = useState('all'); // all, active, completed
  const [routeFilter, setRouteFilter] = useState('all');
  const [etaData, setEtaData] = useState(null);
  
  // Alight Modal States
  const [showAlightModal, setShowAlightModal] = useState(false);
  const [stops, setStops] = useState([]);
  const [selectedAlightStop, setSelectedAlightStop] = useState('');
  const [alightLoading, setAlightLoading] = useState(false);
  const [finalFare, setFinalFare] = useState(null);

  useEffect(() => {
    const fetchTickets = () => {
      const pid = getPassengerId();
      fetch(`${API_BASE}/api/passengers/${pid}/tickets`)
        .then(r => r.ok ? r.json() : [])
        .then(data => setTickets(data))
        .catch(console.error);
    };
    
    fetchTickets();
    const interval = setInterval(fetchTickets, 15000); // refresh list occasionally
    return () => clearInterval(interval);
  }, []);

  const activeTicket = tickets.find(t => t.status === 'active');
  const totalSpend = tickets.filter(t => t.status === 'completed').reduce((sum, t) => sum + (t.fare || 0), 0);

  // Filter logic
  const displayedTickets = tickets.filter(t => {
    if (filter === 'active' && t.status !== 'active') return false;
    if (filter === 'completed' && t.status !== 'completed') return false;
    if (routeFilter !== 'all' && t.route !== routeFilter) return false;
    // Don't show active ticket in the main list if we are showing all
    if (filter === 'all' && t.status === 'active') return false; 
    return true;
  });

  useEffect(() => {
    if (!activeTicket) return;
    let mounted = true;
    
    const fetchEta = async () => {
      try {
        const url = new URL(`${API_BASE}/api/eta`);
        url.searchParams.append('bus_id', activeTicket.bus_id);
        // Using a generic stop to fetch ETA for demo purposes if specific stop isn't mapped
        url.searchParams.append('stop_name', activeTicket.to);
        
        const res = await fetch(url.toString());
        if (res.ok && mounted) {
          const data = await res.json();
          setEtaData(data);
        }
      } catch (err) {
        console.warn('ETA fetch error:', err);
      }
    };

    fetchEta();
    const timer = setInterval(fetchEta, 15000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [activeTicket]);

  const openAlightModal = async () => {
    setShowAlightModal(true);
    setFinalFare(null);
    try {
      const res = await fetch(`${API_BASE}/api/stops?route=${activeTicket.route}`);
      if (res.ok) {
        const data = await res.json();
        setStops(data.stops || []);
        if (data.stops && data.stops.length > 0) setSelectedAlightStop(data.stops[data.stops.length - 1].stop_name);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleAlight = async () => {
    setAlightLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/passengers/alight`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticket_id: activeTicket.id,
          alighting_stop: selectedAlightStop
        })
      });
      if (res.ok) {
        const data = await res.json();
        setFinalFare(data.final_fare);
        
        // Refresh tickets immediately
        const pid = getPassengerId();
        const tRes = await fetch(`${API_BASE}/api/passengers/${pid}/tickets`);
        if (tRes.ok) setTickets(await tRes.json());
      }
    } catch (e) {
      console.error(e);
    }
    setAlightLoading(false);
  };

  return (
    <div style={{
      width: '100%', height: '100%', overflowY: 'auto',
      padding: '24px', background: 'var(--color-bg-base)',
      display: 'flex', flexDirection: 'column', position: 'relative'
    }}>
      <div style={{ maxWidth: '800px', width: '100%', margin: '0 auto' }}>
        
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '32px' }}>
          <h1 style={{ 
            fontFamily: 'var(--font-data)', fontSize: '2rem', fontWeight: 800, 
            color: 'var(--color-text-primary)', margin: 0, letterSpacing: '-0.5px' 
          }}>
            MY TICKETS
          </h1>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              This Month
            </div>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-accent)' }}>
              ₹{totalSpend}
            </div>
          </div>
        </div>

        {/* Active Ticket / Boarding Pass */}
        {activeTicket && (filter === 'all' || filter === 'active') && (
          <div style={{
            background: 'var(--color-bg-panel)',
            border: '1px solid var(--color-border)',
            borderLeft: '4px solid var(--color-accent)',
            borderRadius: '16px',
            padding: '24px',
            marginBottom: '32px',
            boxShadow: '0 8px 30px rgba(0, 212, 255, 0.1)',
            position: 'relative',
            overflow: 'hidden'
          }}>
            {/* Subtle glow */}
            <div style={{
              position: 'absolute', top: 0, bottom: 0, left: 0, width: '100px',
              background: 'linear-gradient(90deg, rgba(0,212,255,0.05) 0%, transparent 100%)',
              pointerEvents: 'none'
            }} />

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
              <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                <span style={{
                  background: 'var(--color-bg-elevated)',
                  border: `2px solid ${ROUTE_COLORS[activeTicket.route] || 'var(--color-text-secondary)'}`,
                  color: 'var(--color-text-primary)',
                  fontFamily: 'var(--font-data)',
                  fontWeight: 800,
                  fontSize: '1.2rem',
                  padding: '4px 12px',
                  borderRadius: '8px'
                }}>
                  {activeTicket.route}
                </span>
                <span style={{ fontFamily: 'var(--font-data)', color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>
                  {activeTicket.bus_id}
                </span>
              </div>
              <span style={{
                background: 'rgba(16, 185, 129, 0.15)',
                color: 'var(--color-success)',
                padding: '4px 10px',
                borderRadius: '20px',
                fontSize: '0.75rem',
                fontWeight: 700,
                letterSpacing: '0.05em',
              }}>
                IN PROGRESS
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginBottom: '4px' }}>FROM</div>
                <div style={{ fontSize: '1.2rem', fontWeight: 600, color: 'var(--color-text-primary)' }}>{activeTicket.from}</div>
              </div>
              <ArrowRight size={24} style={{ color: 'var(--color-text-muted)' }} />
              <div style={{ flex: 1, textAlign: 'right' }}>
                <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginBottom: '4px' }}>TO</div>
                <div style={{ fontSize: '1.2rem', fontWeight: 600, color: 'var(--color-text-primary)' }}>{activeTicket.to}</div>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', borderTop: '1px solid var(--color-border)', paddingTop: '20px' }}>
              <div>
                <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginBottom: '4px' }}>Boarded</div>
                <div style={{ fontFamily: 'var(--font-data)', fontSize: '1rem', color: 'var(--color-text-primary)' }}>
                  {formatDateTime(activeTicket.boarded_at)}
                </div>
              </div>
              
              {etaData ? (
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginBottom: '4px' }}>ETA to Dest</div>
                  <div style={{ fontFamily: 'var(--font-data)', fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-accent)' }}>
                    {etaData.eta_corrected_minutes} <span style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', fontWeight: 400 }}>min</span>
                  </div>
                </div>
              ) : (
                <div style={{ textAlign: 'center', color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
                  Calculating ETA...
                </div>
              )}

              <div style={{ display: 'flex', gap: '8px' }}>
                <button 
                  onClick={() => onTrackBus && onTrackBus(activeTicket.bus_id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '8px',
                    background: 'var(--color-bg-elevated)', color: 'var(--color-text-primary)',
                    border: '1px solid var(--color-border)', padding: '10px 16px',
                    borderRadius: '12px', fontWeight: 700, cursor: 'pointer'
                  }}
                >
                  <Navigation size={18} />
                  Track
                </button>
                <button 
                  onClick={openAlightModal}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '8px',
                    background: 'var(--color-danger)', color: 'white',
                    border: 'none', padding: '10px 20px',
                    borderRadius: '12px', fontWeight: 700, cursor: 'pointer',
                    boxShadow: '0 4px 12px rgba(239,68,68,0.2)'
                  }}
                >
                  ALIGHT
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Filter Bar */}
        <div style={{ display: 'flex', gap: '16px', marginBottom: '24px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', background: 'var(--color-bg-elevated)', padding: '4px', borderRadius: '12px' }}>
            {['all', 'active', 'completed'].map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                style={{
                  background: filter === f ? 'var(--color-bg-panel)' : 'transparent',
                  color: filter === f ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                  border: 'none',
                  padding: '8px 16px',
                  borderRadius: '8px',
                  fontSize: '0.9rem',
                  fontWeight: filter === f ? 600 : 400,
                  cursor: 'pointer',
                  textTransform: 'capitalize'
                }}
              >
                {f}
              </button>
            ))}
          </div>

          <select
            value={routeFilter}
            onChange={(e) => setRouteFilter(e.target.value)}
            style={{
              background: 'var(--color-bg-elevated)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-primary)',
              padding: '8px 16px',
              borderRadius: '12px',
              fontSize: '0.9rem',
              outline: 'none',
              cursor: 'pointer'
            }}
          >
            <option value="all">All Routes</option>
            <option value="19">Route 19</option>
            <option value="102X">Route 102X</option>
            <option value="515">Route 515</option>
          </select>
        </div>

        {/* Past Tickets List */}
        {displayedTickets.length === 0 ? (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', padding: '64px 0', color: 'var(--color-text-muted)'
          }}>
            <Ticket size={48} style={{ marginBottom: '16px', opacity: 0.5 }} />
            <p style={{ fontSize: '1rem' }}>No journeys yet. Board a bus to get started.</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {displayedTickets.map(ticket => (
              <div key={ticket.id} style={{
                background: 'var(--color-bg-panel)',
                border: '1px solid var(--color-border)',
                borderRadius: '12px',
                padding: '16px',
                display: 'flex',
                alignItems: 'center',
                gap: '16px',
                transition: 'transform 0.2s, box-shadow 0.2s',
                cursor: 'default'
              }}>
                <div style={{
                  minWidth: '56px', textAlign: 'center',
                  fontFamily: 'var(--font-data)', fontWeight: 700,
                  border: `2px solid ${ROUTE_COLORS[ticket.route] || 'var(--color-border)'}`,
                  borderRadius: '8px', padding: '6px 0',
                  color: 'var(--color-text-primary)'
                }}>
                  {ticket.route}
                </div>
                
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                    <span style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>{ticket.from}</span>
                    <ArrowRight size={14} style={{ color: 'var(--color-text-muted)' }} />
                    <span style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>{ticket.to}</span>
                  </div>
                  
                  <div style={{ display: 'flex', gap: '16px', fontSize: '0.85rem', color: 'var(--color-text-secondary)', alignItems: 'center' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Clock size={14} />
                      <span style={{ fontFamily: 'var(--font-data)' }}>
                        {formatDateTime(ticket.boarded_at)}
                      </span>
                    </span>
                    {ticket.alighted_at && (
                      <span style={{ fontFamily: 'var(--font-data)' }}>
                        • {calculateDuration(ticket.boarded_at, ticket.alighted_at)}
                      </span>
                    )}
                  </div>
                </div>

                <div style={{ textAlign: 'right', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '8px' }}>
                  <div style={{ fontFamily: 'var(--font-data)', fontSize: '1.2rem', fontWeight: 700, color: 'var(--color-text-primary)' }}>
                    ₹{ticket.fare}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
                      <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: getCrowdColor(ticket.crowding) }} />
                      <span style={{ textTransform: 'capitalize' }}>{ticket.crowding}</span>
                    </div>
                    {ticket.status === 'completed' && (
                      <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--color-success)', background: 'rgba(16, 185, 129, 0.1)', padding: '2px 6px', borderRadius: '4px' }}>
                        COMPLETED
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Alight Modal */}
      {showAlightModal && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.8)', zIndex: 1010, borderRadius: '16px',
          display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', padding: '20px',
          animation: 'fadeIn 0.2s ease-out'
        }}>
          {!finalFare ? (
            <div style={{ width: '100%', maxWidth: '400px', background: 'var(--color-bg-panel)', padding: '24px', borderRadius: '16px', border: '1px solid var(--color-border)' }}>
              <h3 style={{ margin: '0 0 16px 0', fontSize: '1.2rem', fontFamily: 'var(--font-data)' }}>Alight Bus</h3>
              
              <div style={{ marginBottom: '24px' }}>
                <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginBottom: '8px' }}>Select Alighting Stop</label>
                <select 
                  value={selectedAlightStop} 
                  onChange={e => setSelectedAlightStop(e.target.value)}
                  style={{ width: '100%', padding: '12px', background: 'var(--color-bg-elevated)', color: 'white', border: '1px solid var(--color-border)', borderRadius: '8px' }}
                >
                  {stops.length > 0 ? stops.map(s => (
                    <option key={s.stop_id} value={s.stop_name}>{s.stop_name}</option>
                  )) : (
                    <option value="Unknown Dropoff">Unknown Dropoff</option>
                  )}
                </select>
              </div>

              <div style={{ display: 'flex', gap: '12px' }}>
                <button onClick={() => setShowAlightModal(false)} style={{ flex: 1, padding: '12px', background: 'transparent', border: '1px solid var(--color-border)', color: 'white', borderRadius: '8px', cursor: 'pointer' }}>Cancel</button>
                <button onClick={handleAlight} disabled={alightLoading} style={{ flex: 1, padding: '12px', background: 'var(--color-danger)', border: 'none', color: 'white', borderRadius: '8px', fontWeight: 'bold', cursor: 'pointer' }}>
                  {alightLoading ? 'Processing...' : 'Confirm Alight'}
                </button>
              </div>
            </div>
          ) : (
            <div style={{ width: '100%', maxWidth: '400px', background: 'var(--color-bg-panel)', padding: '24px', borderRadius: '16px', border: '1px solid var(--color-border)', textAlign: 'center' }}>
              <Ticket size={48} color="var(--color-success)" style={{ marginBottom: '16px' }} />
              <h2 style={{ fontFamily: 'var(--font-data)', margin: '0 0 8px 0', color: 'var(--color-success)' }}>JOURNEY COMPLETED</h2>
              <div style={{ fontSize: '1.2rem', color: 'var(--color-text-secondary)', marginBottom: '12px' }}>Final Fare</div>
              <div style={{ fontSize: '3rem', fontFamily: 'var(--font-data)', fontWeight: 800, color: 'var(--color-text-primary)', marginBottom: '24px' }}>
                ₹{finalFare}
              </div>
              <button onClick={() => setShowAlightModal(false)} style={{ width: '100%', background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)', color: 'white', padding: '12px', borderRadius: '8px', cursor: 'pointer', fontWeight: 600 }}>
                Close
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
