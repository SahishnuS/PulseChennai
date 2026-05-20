/**
 * useDeviationAlert.js
 * Subscribes to the /ws/live WebSocket stream and extracts
 * ROUTE_DEVIATION events, exposing them as React state.
 */
import { useState, useEffect, useRef } from 'react';
import { API_BASE } from '../lib/supabase';

const WS_URL = API_BASE.replace(/^http/, 'ws') + '/ws/live';
const RECONNECT_DELAY_MS = 4000;

/**
 * Returns:
 *   deviationAlert: {
 *     bus_id, route, affected_stops, next_available_stop, distance_m, message
 *   } | null
 *   dismissAlert: () => void
 *   deviatedBusIds: Set<string>   ← for marking markers on the map
 */
export function useDeviationAlert() {
  const [deviationAlert, setDeviationAlert]   = useState(null);
  const [deviatedBusIds, setDeviatedBusIds]   = useState(new Set());
  const wsRef          = useRef(null);
  const reconnectTimer = useRef(null);

  useEffect(() => {
    const connect = () => {
      try {
        const ws = new WebSocket(WS_URL);
        wsRef.current = ws;

        ws.onopen = () => {
          clearTimeout(reconnectTimer.current);
        };

        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data);
            if (msg.type === 'ROUTE_DEVIATION') {
              setDeviationAlert(msg);
              setDeviatedBusIds((prev) => new Set([...prev, msg.bus_id]));
            }
          } catch { /* ignore parse errors */ }
        };

        ws.onclose = (e) => {
          if (!e.wasClean) {
            reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
          }
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch { /* ignore if WS not available */ }
    };

    connect();

    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close(1000, 'Component unmounted');
    };
  }, []);

  const dismissAlert = () => {
    setDeviationAlert(null);
    // Don't clear deviatedBusIds — keep the "!" badge on the map marker
    // until bus comes back on route (handled by server-side TTL)
  };

  return { deviationAlert, dismissAlert, deviatedBusIds };
}
