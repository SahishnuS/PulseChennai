import { useState, useEffect } from 'react';
import { useWatchedStop } from '../context/WatchedStopContext';

// Haversine formula for distance in meters
function haversineDistanceMeters(lat1, lng1, lat2, lng2) {
  const R = 6371e3; // metres
  const phi1 = lat1 * Math.PI/180;
  const phi2 = lat2 * Math.PI/180;
  const deltaPhi = (lat2-lat1) * Math.PI/180;
  const deltaLambda = (lng2-lng1) * Math.PI/180;

  const a = Math.sin(deltaPhi/2) * Math.sin(deltaPhi/2) +
            Math.cos(phi1) * Math.cos(phi2) *
            Math.sin(deltaLambda/2) * Math.sin(deltaLambda/2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));

  return R * c;
}

export function useStopArrivalAlert(buses) {
  const { watchedStop, setWatchedStop } = useWatchedStop();
  const [alert, setAlert] = useState(null);

  useEffect(() => {
    if (!watchedStop || !buses.length) return;

    const routeBuses = buses.filter(b => String(b.route) === String(watchedStop.routeId));
    if (!routeBuses.length) return;

    let minDistance = Infinity;
    let closestBus = null;

    for (const bus of routeBuses) {
      const dist = haversineDistanceMeters(bus.lat, bus.lng, watchedStop.stopCoords[0], watchedStop.stopCoords[1]);
      if (dist < minDistance) {
        minDistance = dist;
        closestBus = bus;
      }
    }

    if (closestBus) {
      if (minDistance <= 150) {
        setAlert({ 
          message: `Route ${watchedStop.routeId} has ARRIVED`, 
          status: 'arrived' 
        });
      } else if (minDistance <= 400) {
        const speedMs = (closestBus.speed || 20) * (1000 / 3600);
        const timeSecs = minDistance / (speedMs || 1);
        const timeMins = Math.max(1, Math.ceil(timeSecs / 60));
        setAlert({ 
          message: `Route ${watchedStop.routeId} is ${Math.round(minDistance)}m away — ${timeMins} min`, 
          status: 'approaching' 
        });
      }
    }
  }, [buses, watchedStop]);

  // Auto-dismiss after 12 seconds
  useEffect(() => {
    if (alert) {
      const timer = setTimeout(() => {
        setAlert(null);
        if (alert.status === 'arrived') {
            setWatchedStop(null); // Clear watched stop after arrival dismissal
        }
      }, 12000);
      return () => clearTimeout(timer);
    }
  }, [alert, setWatchedStop]);

  return { alert, setAlert };
}
