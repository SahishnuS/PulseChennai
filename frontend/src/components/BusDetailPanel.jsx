import React from 'react';

export default function BusDetailPanel({ bus, onClose, language }) {
  if (!bus) return null;

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
      width: '340px',
      boxShadow: '0 12px 40px rgba(0,0,0,0.6)',
      animation: 'slideDown 0.3s ease-out',
      display: 'flex',
      flexDirection: 'column',
      gap: '16px'
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

      {/* Metrics */}
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

      {/* Ticket Pricing */}
      <div style={{ borderTop: '1px dashed var(--border)', paddingTop: '16px' }}>
        <h4 style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '12px' }}>
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
      <div style={{ display: 'flex', gap: '12px', marginTop: '4px' }}>
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
