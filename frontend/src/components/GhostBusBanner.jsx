import React, { useState, useEffect, useRef } from 'react';
import { WifiOff, CheckCircle } from 'lucide-react';
import { API_BASE } from '../lib/supabase';

export default function GhostBusBanner({ language }) {
  const [banner, setBanner] = useState(null); // { type: 'ghost'|'recovered', busId, route }
  const prevGhosts = useRef(new Set());
  const dismissTimer = useRef(null);

  useEffect(() => {
    const checkGhosts = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/buses`);
        const data = await res.json();
        const buses = data.buses || [];

        const currentGhosts = new Set(
          buses.filter(b => b.is_ghost).map(b => b.id)
        );

        // Detect new ghosts
        for (const ghostId of currentGhosts) {
          if (!prevGhosts.current.has(ghostId)) {
            const bus = buses.find(b => b.id === ghostId);
            setBanner({ type: 'ghost', busId: ghostId, route: bus?.route || '?' });
            autoDismiss();
          }
        }

        // Detect recoveries
        for (const prevId of prevGhosts.current) {
          if (!currentGhosts.has(prevId)) {
            const bus = buses.find(b => b.id === prevId);
            setBanner({ type: 'recovered', busId: prevId, route: bus?.route || '?' });
            autoDismiss();
          }
        }

        prevGhosts.current = currentGhosts;
      } catch (e) { /* ignore */ }
    };

    checkGhosts();
    const interval = setInterval(checkGhosts, 3000);
    return () => {
      clearInterval(interval);
      if (dismissTimer.current) clearTimeout(dismissTimer.current);
    };
  }, []);

  const autoDismiss = () => {
    if (dismissTimer.current) clearTimeout(dismissTimer.current);
    dismissTimer.current = setTimeout(() => setBanner(null), 5000);
  };

  if (!banner) return null;

  const isGhost = banner.type === 'ghost';

  return (
    <div
      className="slide-in"
      style={{
        padding: '12px 16px',
        background: isGhost ? 'rgba(255, 69, 96, 0.10)' : 'rgba(0, 229, 160, 0.10)',
        borderTop: `3px solid ${isGhost ? '#FF4560' : '#00E5A0'}`,
        color: isGhost ? '#FF4560' : '#00E5A0',
        fontSize: '0.85rem',
        fontWeight: 600,
        textAlign: 'center',
        zIndex: 999,
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '8px'
      }}
    >
      {isGhost ? <WifiOff size="1.1em" color="currentColor" /> : <CheckCircle size="1.1em" color="currentColor" />}
      
      {isGhost ? (
        language === 'ta'
          ? `பேருந்து ${banner.route} — சமிக்ஞை இல்லை. நிலையை மதிப்பிடுகிறோம்.`
          : `BUS ${banner.route} — Signal Lost. Estimating position via dead reckoning.`
      ) : (
        language === 'ta'
          ? `பேருந்து ${banner.route} — சமிக்ஞை மீட்டெடுக்கப்பட்டது. நேரடி கண்காணிப்பு தொடர்கிறது.`
          : `BUS ${banner.route} — Signal restored. Live tracking resumed.`
      )}
    </div>
  );
}
