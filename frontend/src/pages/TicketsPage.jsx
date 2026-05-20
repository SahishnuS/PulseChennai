import React, { useState, useEffect } from 'react';
import { Ticket, ArrowRight, Clock, Navigation } from 'lucide-react';
import { getTickets, completeTicket } from '../store/ticketStore';

export default function TicketsPage({ onTrackBus }) {
  const [tickets, setTickets] = useState([]);

  // Load tickets on mount and when window gains focus
  useEffect(() => {
    const load = () => setTickets(getTickets());
    load();
    window.addEventListener('focus', load);
    return () => window.removeEventListener('focus', load);
  }, []);

  const activeTickets = tickets.filter(t => t.status === 'active');
  const pastTickets = tickets.filter(t => t.status === 'completed');

  if (tickets.length === 0) {
    return (
      <div style={{
        height: '100%', display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        background: 'var(--color-bg-base)', padding: '24px',
        textAlign: 'center'
      }}>
        <Ticket size={48} style={{ color: 'var(--color-text-muted)', opacity: 0.3, marginBottom: '16px' }} />
        <p style={{ color: 'var(--color-text-secondary)', fontSize: '1rem', maxWidth: '300px', lineHeight: 1.5 }}>
          No tickets yet. Tap "Plan New Trip" to get started.
        </p>
      </div>
    );
  }

  const formatTime = (isoString) => {
    if (!isoString) return '—';
    return new Date(isoString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatDate = (isoString) => {
    if (!isoString) return '—';
    return new Date(isoString).toLocaleDateString();
  };

  return (
    <div style={{
      height: '100%', overflowY: 'auto', background: 'var(--color-bg-base)',
      padding: '24px', maxWidth: '600px', margin: '0 auto',
    }}>
      <h2 style={{
        fontSize: '1.2rem', fontWeight: 800, color: 'var(--color-text-primary)',
        marginBottom: '24px',
      }}>
        MY TICKETS
      </h2>

      {/* ── Active Tickets ── */}
      {activeTickets.length > 0 && (
        <div style={{ marginBottom: '32px' }}>
          <h3 style={{
            fontSize: '0.8rem', fontWeight: 700, color: 'var(--color-text-muted)',
            fontFamily: 'var(--font-data)', letterSpacing: '1.5px', marginBottom: '16px',
          }}>
            ACTIVE TICKETS
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {activeTickets.map(ticket => (
              <div key={ticket.id} style={{
                background: 'var(--color-bg-panel)',
                borderRadius: '12px',
                border: '1px solid var(--color-accent)',
                borderLeft: '4px solid var(--color-accent)',
                padding: '20px',
                position: 'relative',
              }}>
                <div style={{ position: 'absolute', top: '16px', right: '16px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--color-success)', boxShadow: '0 0 6px var(--color-success)' }} />
                  <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--color-success)', letterSpacing: '0.05em' }}>ACTIVE</span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                  <span style={{
                    fontFamily: 'var(--font-data)', fontWeight: 800, fontSize: '1rem',
                    color: 'var(--color-accent)', background: 'rgba(0,212,255,0.1)',
                    padding: '4px 10px', borderRadius: '6px',
                  }}>
                    {ticket.route}
                  </span>
                  <span style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--color-text-primary)' }}>
                    {ticket.busId}
                  </span>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <div style={{ flex: 1 }}>
                    <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', fontWeight: 600, marginBottom: '4px' }}>FROM</p>
                    <p style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--color-text-primary)', lineHeight: 1.2 }}>{ticket.fromStop}</p>
                  </div>
                  <div style={{ padding: '0 16px', color: 'var(--color-text-muted)' }}>
                    <ArrowRight size={20} />
                  </div>
                  <div style={{ flex: 1, textAlign: 'right' }}>
                    <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', fontWeight: 600, marginBottom: '4px' }}>TO</p>
                    <p style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--color-text-primary)', lineHeight: 1.2 }}>{ticket.toStop}</p>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px dashed var(--color-border)', paddingTop: '16px', marginBottom: '16px' }}>
                  <div>
                    <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginBottom: '2px' }}>Purchased</p>
                    <p style={{ fontSize: '0.85rem', color: 'var(--color-text-primary)', fontWeight: 500 }}>
                      {formatDate(ticket.purchasedAt)} · {formatTime(ticket.purchasedAt)}
                    </p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginBottom: '2px' }}>Fare</p>
                    <p style={{ fontSize: '1.2rem', fontFamily: 'var(--font-data)', fontWeight: 800, color: 'var(--color-text-primary)' }}>
                      ₹{ticket.fare}
                    </p>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '12px' }}>
                  <button
                    onClick={() => {
                      completeTicket(ticket.id);
                      setTickets(getTickets());
                    }}
                    style={{
                      flex: 1, padding: '12px', borderRadius: '8px',
                      background: 'transparent', border: '1px solid var(--color-border)',
                      color: 'var(--color-text-primary)', fontWeight: 600, cursor: 'pointer',
                      transition: 'all 0.2s',
                    }}
                    onMouseOver={e => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
                    onMouseOut={e => e.currentTarget.style.background = 'transparent'}
                  >
                    COMPLETE JOURNEY
                  </button>
                  <button
                    onClick={() => { if (onTrackBus) onTrackBus(ticket.busId); }}
                    style={{
                      flex: 1, padding: '12px', borderRadius: '8px',
                      background: 'var(--color-accent)', border: 'none',
                      color: '#080C14', fontWeight: 700, cursor: 'pointer',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
                    }}
                  >
                    <Navigation size={16} /> TRACK BUS
                  </button>
                </div>

              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Past Tickets ── */}
      {pastTickets.length > 0 && (
        <div>
          <h3 style={{
            fontSize: '0.8rem', fontWeight: 700, color: 'var(--color-text-muted)',
            fontFamily: 'var(--font-data)', letterSpacing: '1.5px', marginBottom: '16px',
          }}>
            PAST JOURNEYS
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {pastTickets.map(ticket => (
              <div key={ticket.id} style={{
                background: 'var(--color-bg-panel)',
                borderRadius: '12px',
                border: '1px solid var(--color-border)',
                padding: '16px',
                position: 'relative',
              }}>
                <div style={{ position: 'absolute', top: '16px', right: '16px' }}>
                  <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--color-text-muted)', letterSpacing: '0.05em' }}>COMPLETED</span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                  <span style={{
                    fontFamily: 'var(--font-data)', fontWeight: 800, fontSize: '0.9rem',
                    color: 'var(--color-text-secondary)', background: 'var(--color-bg-base)',
                    padding: '2px 8px', borderRadius: '4px', border: '1px solid var(--color-border)',
                  }}>
                    {ticket.route}
                  </span>
                  <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                    {ticket.busId}
                  </span>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <div style={{ flex: 1 }}>
                    <p style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--color-text-primary)' }}>{ticket.fromStop}</p>
                  </div>
                  <div style={{ padding: '0 12px', color: 'var(--color-border)' }}>
                    <ArrowRight size={16} />
                  </div>
                  <div style={{ flex: 1, textAlign: 'right' }}>
                    <p style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--color-text-primary)' }}>{ticket.toStop}</p>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px dashed var(--color-border)', paddingTop: '12px' }}>
                  <p style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
                    {formatDate(ticket.purchasedAt)}
                  </p>
                  <p style={{ fontSize: '1rem', fontFamily: 'var(--font-data)', fontWeight: 700, color: 'var(--color-text-secondary)' }}>
                    ₹{ticket.fare}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
