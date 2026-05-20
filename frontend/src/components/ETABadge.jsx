import React, { useState } from 'react';

// Confidence arc badge radius / circumference
const RADIUS = 18;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

const LEVEL_COLORS = {
  HIGH:     'var(--color-success)',
  MODERATE: 'var(--color-warning)',
  LOW:      'var(--color-danger)',
};

const TOOLTIP_TEXT =
  'Confidence based on: ML model health, bus GPS reliability, ' +
  'TomTom traffic correction, and ETA range uncertainty.';

/**
 * ETABadge — shows ETA in minutes + a radial confidence arc.
 *
 * Props:
 *   eta_minutes      number   — the best-estimate ETA
 *   confidence_pct   number   — 25–97 integer
 *   confidence_label string   — "HIGH" | "MODERATE" | "LOW"
 */
export default function ETABadge({ eta_minutes, confidence_pct, confidence_label }) {
  const [hovered, setHovered] = useState(false);

  const color      = LEVEL_COLORS[confidence_label] ?? LEVEL_COLORS.LOW;
  const arcLen     = ((confidence_pct ?? 0) / 100) * CIRCUMFERENCE;
  const dashOffset = CIRCUMFERENCE - arcLen;

  return (
    <div
      style={{
        display:    'flex',
        flexDirection: 'row',
        alignItems: 'center',
        gap:        '8px',
        position:   'relative',
      }}
    >
      {/* ETA number column */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
        <span style={{
          fontFamily: 'var(--font-data)',
          fontSize:   '20px',
          fontWeight: 700,
          color:      'var(--color-accent)',
          lineHeight: 1,
        }}>
          {eta_minutes != null ? Math.round(eta_minutes) : '—'}
        </span>
        <span style={{
          fontSize:   '10px',
          color:      'var(--color-text-muted, var(--color-text-secondary))',
          lineHeight: 1.2,
          marginTop:  '2px',
        }}>
          min
        </span>
      </div>

      {/* Confidence arc badge column */}
      <div
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '3px', cursor: 'default' }}
      >
        {/* SVG arc */}
        <svg
          width="44"
          height="44"
          viewBox="0 0 44 44"
          style={{ display: 'block' }}
        >
          {/* Background track */}
          <circle
            cx="22"
            cy="22"
            r={RADIUS}
            fill="none"
            stroke="var(--color-bg-elevated)"
            strokeWidth="4"
          />
          {/* Confidence arc */}
          <circle
            cx="22"
            cy="22"
            r={RADIUS}
            fill="none"
            stroke={color}
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray={`${CIRCUMFERENCE} ${CIRCUMFERENCE}`}
            strokeDashoffset={dashOffset}
            transform="rotate(-90 22 22)"
            style={{ transition: 'stroke-dashoffset 0.6s ease, stroke 0.3s ease' }}
          />
          {/* Center percentage text */}
          <text
            x="22"
            y="26"
            textAnchor="middle"
            fontFamily="var(--font-data)"
            fontSize="9"
            fontWeight="700"
            fill={color}
          >
            {confidence_pct != null ? `${confidence_pct}%` : '?'}
          </text>
        </svg>

        {/* Confidence label below arc */}
        <span style={{
          fontFamily:    'var(--font-data)',
          fontSize:      '9px',
          fontWeight:    700,
          color:         color,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          lineHeight:    1,
        }}>
          {confidence_label ?? 'N/A'}
        </span>
      </div>

      {/* Hover tooltip */}
      {hovered && (
        <div
          style={{
            position:     'absolute',
            bottom:       '100%',
            left:         '50%',
            transform:    'translateX(-50%)',
            marginBottom: '8px',
            background:   'var(--color-bg-elevated)',
            border:       '1px solid var(--color-border)',
            borderRadius: '8px',
            padding:      '8px 12px',
            width:        '240px',
            fontSize:     '0.72rem',
            color:        'var(--color-text-secondary)',
            lineHeight:   1.5,
            boxShadow:    'var(--shadow-panel)',
            pointerEvents:'none',
            zIndex:       9999,
            fontFamily:   'var(--font-ui)',
          }}
        >
          {TOOLTIP_TEXT}
        </div>
      )}
    </div>
  );
}
