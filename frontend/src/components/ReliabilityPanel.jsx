import React, { useState } from 'react';

export default function ReliabilityPanel({ buses, language }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div style={{
      position: 'absolute',
      bottom: '16px',
      right: '16px',
      zIndex: 1000,
    }}>
      {/* Toggle button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          padding: '8px 14px',
          borderRadius: '10px',
          border: '1px solid #334155',
          background: 'rgba(30, 41, 59, 0.95)',
          color: '#F8FAFC',
          fontSize: '0.75rem',
          fontWeight: 600,
          cursor: 'pointer',
          backdropFilter: 'blur(8px)',
          fontFamily: 'Inter, sans-serif',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}
      >
        📡 {language === 'en' ? 'Signal Health' : 'சமிக்ஞை நிலை'}
        <span style={{ fontSize: '10px' }}>{isOpen ? '▼' : '▲'}</span>
      </button>

      {/* Panel */}
      {isOpen && (
        <div style={{
          marginTop: '8px',
          padding: '16px',
          borderRadius: '12px',
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border)',
          boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
          minWidth: '320px',
        }}>
          <h4 style={{ color: 'var(--text-secondary)', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '12px' }}>
            Signal Health
          </h4>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <tbody>
              {(buses || []).map(bus => {
                const score = bus.reliability_score || 0;
                const isGhost = bus.is_ghost;
                const barColor = score > 0.7 ? 'var(--success)' : score > 0.4 ? 'var(--warning)' : 'var(--danger)';

                return (
                  <tr key={bus.id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '10px 4px', color: 'var(--text-primary)', fontFamily: 'monospace' }}>
                      {bus.id}
                    </td>
                    <td style={{ padding: '10px 4px', color: 'var(--text-secondary)' }}>{bus.route}</td>
                    <td style={{ padding: '10px 4px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div style={{
                          width: '60px', height: '6px', background: 'var(--bg-tertiary)',
                          borderRadius: '3px', overflow: 'hidden',
                        }}>
                          <div style={{
                            width: `${score * 100}%`, height: '100%',
                            background: barColor, borderRadius: '3px',
                            transition: 'width 0.5s ease',
                          }} />
                        </div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
                          {score.toFixed(2)}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '10px 4px', textAlign: 'right' }}>
                      {isGhost ? '🔴' : '🟢'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div style={{
            marginTop: '12px', paddingTop: '12px', borderTop: '1px dashed var(--border)',
            fontSize: '0.8rem', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between'
          }}>
            <span>System Status:</span>
            <span style={{ color: 'var(--text-primary)' }}>
              {buses.filter(b => !b.is_ghost).length}/{buses.length} buses live
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
