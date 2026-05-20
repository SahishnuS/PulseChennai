import React, { useState } from 'react';
import { getPolylineLengthKm } from '../services/busSimulator';

// Confidence arc badge radius / circumference
const RADIUS = 18;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

const LEVEL_COLORS = {
  HIGH:     '#00E5A0',
  MODERATE: '#FFB800',
  LOW:      '#FF4560',
};

/**
 * computeETA — ML-simulated ETA calculation per bus.
 * Uses distance-based ETA with rush hour factor + Gaussian noise.
 */
export function computeETA(bus, roadPolylines) {
  const polyline = roadPolylines ? roadPolylines.get(bus.route) : null;
  if (!polyline || polyline.length === 0) {
    return { eta: Math.floor(Math.random() * 20 + 5), confidence: 50, label: 'MODERATE', model: 'fallback' };
  }

  const remainingProgress = 1.0 - (bus.progress || 0);
  const totalLengthKm = getPolylineLengthKm(polyline);
  const remainingKm = remainingProgress * totalLengthKm;

  // Rush hour factor
  const hour = new Date().getHours();
  const rushFactor = (hour >= 8 && hour <= 10) || (hour >= 17 && hour <= 20) ? 1.35 : 1.0;
  const speed = bus.speed_kmh || bus.speed || 25;
  const baseETA = speed > 0 ? (remainingKm / speed) * 60 * rushFactor : 30;

  // Gaussian noise ±15%
  const noise = 1 + (Math.random() - 0.5) * 0.3;
  const eta = Math.max(1, Math.round(baseETA * noise));

  // Confidence calculation
  let confidence = 85;
  if (bus.isGhost || bus.is_ghost) confidence -= 30;
  if ((bus.reliability || 1) < 0.5) confidence -= 20;
  else if ((bus.reliability || 1) < 0.7) confidence -= 10;
  if (eta > 30) confidence -= 10;
  else if (eta > 20) confidence -= 5;
  confidence += Math.round((Math.random() - 0.5) * 8);
  confidence = Math.max(25, Math.min(95, confidence));

  const label = confidence >= 75 ? 'HIGH' : confidence >= 50 ? 'MODERATE' : 'LOW';
  const model = (bus.isGhost || bus.is_ghost) ? 'dead-reckoning' : (bus.reliability || 1) > 0.8 ? 'ensemble' : 'single-model';

  return { eta, confidence, label, model };
}

/**
 * ETABadge — shows ETA in minutes + a radial SVG confidence arc.
 *
 * Props:
 *   eta_minutes      number   — the best-estimate ETA
 *   confidence_pct   number   — 25–95 integer
 *   confidence_label string   — "HIGH" | "MODERATE" | "LOW"
 *   model            string   — ML model used
 */
export default function ETABadge({ eta_minutes, confidence_pct, confidence_label, model }) {
  const [hovered, setHovered] = useState(false);

  const color = LEVEL_COLORS[confidence_label] || LEVEL_COLORS.LOW;
  const dashLen = ((confidence_pct || 0) / 100) * 113.1; // circumference of r=18

  return (
    <div
      style={{
        display: 'flex', flexDirection: 'row',
        alignItems: 'center', gap: '8px', position: 'relative',
      }}
    >
      {/* ETA number */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
        <span style={{
          fontFamily: 'var(--font-data)', fontSize: '22px',
          fontWeight: 700, color: 'var(--color-accent)', lineHeight: 1,
        }}>
          {eta_minutes != null ? Math.round(eta_minutes) : '—'}
        </span>
        <span style={{
          fontSize: '10px', color: 'var(--color-text-muted)',
          lineHeight: 1.2, marginTop: '2px',
        }}>
          min
        </span>
      </div>

      {/* SVG Arc Badge */}
      <div
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '3px', cursor: 'default' }}
      >
        <svg width="48" height="48" viewBox="0 0 48 48" style={{ display: 'block' }}>
          {/* Background circle */}
          <circle cx="24" cy="24" r="18" fill="none" stroke="#1a2535" strokeWidth="5" />
          {/* Colored arc */}
          <circle
            cx="24" cy="24" r="18" fill="none"
            stroke={color} strokeWidth="5"
            strokeLinecap="round"
            strokeDasharray={`${dashLen} 113.1`}
            strokeDashoffset="28.3"
            transform="rotate(-90 24 24)"
            style={{ transition: 'stroke-dasharray 0.6s ease, stroke 0.3s ease' }}
          />
          {/* Center percentage */}
          <text
            x="24" y="27" textAnchor="middle"
            fontFamily="var(--font-data)" fontSize="9" fontWeight="700" fill={color}
          >
            {confidence_pct != null ? `${confidence_pct}%` : '?'}
          </text>
        </svg>

        {/* Label below */}
        <span style={{
          fontFamily: 'var(--font-data)', fontSize: '8px',
          fontWeight: 700, color, textTransform: 'uppercase',
          letterSpacing: '0.1em', lineHeight: 1,
        }}>
          {confidence_label || 'N/A'}
        </span>
      </div>

      {/* Tooltip */}
      {hovered && (
        <div style={{
          position: 'absolute', bottom: '100%', left: '50%',
          transform: 'translateX(-50%)', marginBottom: '8px',
          background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)',
          borderRadius: '8px', padding: '8px 12px', width: '260px',
          fontSize: '0.72rem', color: 'var(--color-text-secondary)',
          lineHeight: 1.5, boxShadow: 'var(--shadow-panel)',
          pointerEvents: 'none', zIndex: 9999,
          fontFamily: 'var(--font-data)',
        }}>
          ML Model: {model || 'ensemble'} · Confidence factors: GPS reliability, rush hour, route progress
        </div>
      )}
    </div>
  );
}
