/**
 * Bus Simulator — 9 buses across 6 routes with progress-along-polyline movement.
 * Ghost bus BUS_070_001 cycles GPS on a 45s interval.
 */

export const INITIAL_BUSES = [
  { id: "BUS_019_001", route: "19",   label: "19",   crowding: "medium", reliability: 0.88, progress: 0.10, speed_kmh: 28, isGhost: false },
  { id: "BUS_019_002", route: "19",   label: "19",   crowding: "low",    reliability: 0.91, progress: 0.55, speed_kmh: 32, isGhost: false },
  { id: "BUS_102X_001",route: "102X", label: "102X", crowding: "high",   reliability: 0.74, progress: 0.20, speed_kmh: 24, isGhost: false },
  { id: "BUS_102X_002",route: "102X", label: "102X", crowding: "medium", reliability: 0.85, progress: 0.70, speed_kmh: 30, isGhost: false },
  { id: "BUS_515_001", route: "515",  label: "515",  crowding: "low",    reliability: 0.93, progress: 0.35, speed_kmh: 38, isGhost: false },
  { id: "BUS_21C_001", route: "21C",  label: "21C",  crowding: "medium", reliability: 0.80, progress: 0.15, speed_kmh: 22, isGhost: false },
  { id: "BUS_070_001", route: "70",   label: "70",   crowding: "high",   reliability: 0.22, progress: 0.45, speed_kmh: 18, isGhost: true  },
  { id: "BUS_070_002", route: "70",   label: "70",   crowding: "medium", reliability: 0.77, progress: 0.80, speed_kmh: 26, isGhost: false },
  { id: "BUS_47A_001", route: "47A",  label: "47A",  crowding: "low",    reliability: 0.89, progress: 0.60, speed_kmh: 34, isGhost: false },
];

/**
 * Calculate total polyline length in meters using Haversine.
 */
export function getPolylineLengthM(polyline) {
  if (!polyline || polyline.length < 2) return 0;
  let total = 0;
  for (let i = 1; i < polyline.length; i++) {
    total += haversine(polyline[i - 1][0], polyline[i - 1][1], polyline[i][0], polyline[i][1]);
  }
  return total;
}

export function getPolylineLengthKm(polyline) {
  return getPolylineLengthM(polyline) / 1000;
}

function haversine(lat1, lng1, lat2, lng2) {
  const R = 6371000;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
    Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/**
 * Get interpolated [lat, lng] at a given progress (0.0–1.0) along a polyline.
 */
export function getPositionAtProgress(polyline, progress) {
  if (!polyline || polyline.length === 0) return [13.0827, 80.2707]; // Chennai Central fallback
  if (polyline.length === 1) return polyline[0];
  
  const clampedProgress = Math.max(0, Math.min(1, progress));
  const totalLength = getPolylineLengthM(polyline);
  const targetDist = clampedProgress * totalLength;

  let cumDist = 0;
  for (let i = 1; i < polyline.length; i++) {
    const segDist = haversine(polyline[i - 1][0], polyline[i - 1][1], polyline[i][0], polyline[i][1]);
    if (cumDist + segDist >= targetDist) {
      // Interpolate within this segment
      const remaining = targetDist - cumDist;
      const frac = segDist > 0 ? remaining / segDist : 0;
      const lat = polyline[i - 1][0] + (polyline[i][0] - polyline[i - 1][0]) * frac;
      const lng = polyline[i - 1][1] + (polyline[i][1] - polyline[i - 1][1]) * frac;
      return [lat, lng];
    }
    cumDist += segDist;
  }

  return polyline[polyline.length - 1];
}

/**
 * Create a mutable simulator state from INITIAL_BUSES.
 * Returns a fresh deep copy each time.
 */
export function createSimulatorState() {
  return INITIAL_BUSES.map(b => ({ ...b }));
}

/**
 * Advance all buses one tick (2 seconds).
 * Returns updated bus array with lat/lng positions.
 */
export function tickBuses(busesState, roadPolylines, tickCount) {
  const TICK_SECONDS = 2;

  return busesState.map(bus => {
    const polyline = roadPolylines.get(bus.route);
    if (!polyline || polyline.length === 0) return bus;

    const totalLengthM = getPolylineLengthM(polyline);
    if (totalLengthM === 0) return bus;

    // Ghost bus: skip position update every 6th tick (GPS dropout)
    const isGhostTick = bus.isGhost && tickCount % 6 === 0;
    
    // Ghost bus speed is slower
    const effectiveSpeed = bus.isGhost ? 12 : bus.speed_kmh;
    const distPerTick = (effectiveSpeed * 1000 / 3600) * TICK_SECONDS;
    const progressDelta = distPerTick / totalLengthM;

    let newProgress = bus.progress + progressDelta;
    if (newProgress >= 1.0) newProgress = 0.0; // Loop

    const position = isGhostTick
      ? getPositionAtProgress(polyline, bus.progress) // Don't update position on ghost tick
      : getPositionAtProgress(polyline, newProgress);

    // Ghost bus BUS_070_001: cycle isGhost on 45s (every ~22.5 ticks)
    let ghostState = bus.isGhost;
    if (bus.id === 'BUS_070_001') {
      const cyclePos = (tickCount * TICK_SECONDS) % 90; // 90s full cycle
      ghostState = cyclePos < 45; // ghost for first 45s, normal for next 45s
    }

    return {
      ...bus,
      progress: isGhostTick ? bus.progress : newProgress,
      lat: position[0],
      lng: position[1],
      isGhost: ghostState,
      is_ghost: ghostState,
      speed: effectiveSpeed,
      reliability_score: bus.reliability,
    };
  });
}
