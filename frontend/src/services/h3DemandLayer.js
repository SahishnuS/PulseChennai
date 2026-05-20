/**
 * H3 Demand Layer — Frontend-side hex generation
 * Generates passenger pings ONLY within 400m of active bus positions,
 * bins them into H3 resolution-8 hexagons, and returns boundaries for rendering.
 */
import * as h3 from 'h3-js';

// ── Ping generation: within 400m of each bus ──
export function generatePassengerPingsForBus(busLat, busLng, count) {
  const pings = [];
  for (let i = 0; i < count; i++) {
    pings.push([
      busLat + (Math.random() - 0.5) * 0.007,
      busLng + (Math.random() - 0.5) * 0.007,
    ]);
  }
  return pings;
}

// ── Demand tracker with rolling window ──
const hexCounts = new Map(); // hexId → count
let lastClear = Date.now();
const WINDOW_MS = 600000; // 10 minutes

export function addPingsAndGetHexes(buses) {
  // Rolling window: clear every 10 min
  if (Date.now() - lastClear > WINDOW_MS) {
    hexCounts.clear();
    lastClear = Date.now();
  }

  // Generate pings for each active bus
  for (const bus of buses) {
    if (!bus.lat || !bus.lng) continue;
    const count = Math.floor(Math.random() * 4) + 3; // 3–6 pings
    const pings = generatePassengerPingsForBus(bus.lat, bus.lng, count);
    
    for (const [lat, lng] of pings) {
      try {
        const hexId = h3.latLngToCell(lat, lng, 8);
        hexCounts.set(hexId, (hexCounts.get(hexId) || 0) + 1);
      } catch (e) {
        // h3 may throw for invalid coords — ignore
      }
    }
  }

  // Build hex data for rendering
  const hexes = [];
  for (const [hexId, count] of hexCounts.entries()) {
    if (count <= 0) continue;
    try {
      const boundary = h3.cellToBoundary(hexId); // [[lat, lng], ...]
      let level = 'low';
      if (count >= 8) level = 'high';
      else if (count >= 3) level = 'medium';

      hexes.push({
        hex_id: hexId,
        boundary,
        count,
        level,
      });
    } catch (e) {
      // ignore invalid hex
    }
  }

  return hexes;
}

export function clearDemandData() {
  hexCounts.clear();
  lastClear = Date.now();
}
