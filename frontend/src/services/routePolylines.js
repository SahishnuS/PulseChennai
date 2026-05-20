/**
 * Route Polylines — OSRM road-snapped routing
 * Primary: OSRM public API, Fallback: TomTom, Final fallback: straight lines
 */

export const ROUTE_WAYPOINTS = {
  "19": [
    { lat: 12.6877, lng: 80.2000 }, // Thiruporur
    { lat: 12.9165, lng: 80.2012 }, // Velachery
    { lat: 13.0389, lng: 80.2619 }, // T Nagar
    { lat: 13.0827, lng: 80.2707 }, // Chennai Central
  ],
  "102X": [
    { lat: 12.7825, lng: 80.2209 }, // Kelambakkam
    { lat: 12.8697, lng: 80.2261 }, // Sholinganallur
    { lat: 13.0067, lng: 80.2206 }, // Adyar
    { lat: 13.0878, lng: 80.2785 }, // Broadway
  ],
  "515": [
    { lat: 12.9249, lng: 80.1000 }, // Tambaram
    { lat: 12.8500, lng: 80.2300 }, // Perungalathur
    { lat: 12.6200, lng: 80.2500 }, // Mamallapuram
  ],
  "21C": [
    { lat: 13.0694, lng: 80.1948 }, // Koyambedu
    { lat: 13.0524, lng: 80.2123 }, // Vadapalani
    { lat: 13.0012, lng: 80.2565 }, // Adyar
  ],
  "70": [
    { lat: 13.0827, lng: 80.2707 }, // Central
    { lat: 13.0732, lng: 80.2609 }, // Egmore
    { lat: 13.1117, lng: 80.2489 }, // Perambur
    { lat: 13.1143, lng: 80.1548 }, // Ambattur
  ],
  "47A": [
    { lat: 13.0389, lng: 80.2619 }, // T Nagar
    { lat: 12.9716, lng: 80.2209 }, // Guindy
    { lat: 12.9516, lng: 80.1389 }, // Chromepet
  ],
};

const ROUTE_COLORS = {
  '19': '#00D4FF', '102X': '#00E5A0', '515': '#FFB800',
  '21C': '#FF6B35', '70': '#C084FC', '47A': '#F472B6'
};

const polylineCache = new Map();

/**
 * Fetch road-snapped polyline via OSRM public API.
 * Returns [lat, lng][] for Leaflet.
 */
export async function getRoadPolyline(waypoints) {
  const coords = waypoints.map(w => `${w.lng},${w.lat}`).join(';');
  const url = `https://router.project-osrm.org/route/v1/driving/${coords}?overview=full&geometries=geojson`;

  try {
    const res = await fetch(url);
    const data = await res.json();
    if (data.routes && data.routes.length > 0) {
      // OSRM returns [lng, lat] — convert to [lat, lng] for Leaflet
      return data.routes[0].geometry.coordinates.map(c => [c[1], c[0]]);
    }
  } catch (error) {
    console.warn('OSRM routing failed, trying TomTom fallback:', error.message);
  }

  // Fallback: TomTom
  try {
    const TOMTOM_KEY = import.meta.env.VITE_TOMTOM_API_KEY;
    if (TOMTOM_KEY) {
      const locs = waypoints.map(w => `${w.lat},${w.lng}`).join(':');
      const ttUrl = `https://api.tomtom.com/routing/1/calculateRoute/${locs}/json?key=${TOMTOM_KEY}&routeType=fastest&traffic=true&travelMode=bus`;
      const ttRes = await fetch(ttUrl);
      const ttData = await ttRes.json();
      if (ttData.routes && ttData.routes.length > 0) {
        const allPoints = [];
        ttData.routes[0].legs.forEach(leg => {
          leg.points.forEach(p => allPoints.push([p.latitude, p.longitude]));
        });
        return allPoints;
      }
    }
  } catch (e) {
    console.warn('TomTom fallback also failed:', e.message);
  }

  // Final fallback: straight lines
  return waypoints.map(w => [w.lat, w.lng]);
}

/**
 * Load all 6 route polylines in parallel with caching.
 */
export async function loadAllRoutePolylines() {
  const routes = Object.keys(ROUTE_WAYPOINTS);
  const promises = routes.map(async (routeId) => {
    if (polylineCache.has(routeId)) {
      return { routeId, polyline: polylineCache.get(routeId) };
    }
    const polyline = await getRoadPolyline(ROUTE_WAYPOINTS[routeId]);
    polylineCache.set(routeId, polyline);
    return { routeId, polyline };
  });

  const results = await Promise.all(promises);
  const map = new Map();
  results.forEach(res => map.set(res.routeId, res.polyline));
  return map;
}

/**
 * Snap a point to the nearest vertex on a polyline.
 */
export function snapToPolyline(point, polyline) {
  if (!polyline || polyline.length === 0) return point;
  
  function distance(p1, p2) {
    const R = 6371000;
    const dLat = (p2[0] - p1[0]) * Math.PI / 180;
    const dLon = (p2[1] - p1[1]) * Math.PI / 180;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(p1[0] * Math.PI / 180) * Math.cos(p2[0] * Math.PI / 180) *
              Math.sin(dLon/2) * Math.sin(dLon/2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  }

  let minDist = Infinity;
  let closestPoint = point;
  for (let i = 0; i < polyline.length; i++) {
    const d = distance(point, polyline[i]);
    if (d < minDist) { minDist = d; closestPoint = polyline[i]; }
  }
  return closestPoint;
}
