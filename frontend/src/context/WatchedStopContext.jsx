import React, { createContext, useState, useContext } from 'react';

const WatchedStopContext = createContext();

export function WatchedStopProvider({ children }) {
  const [watchedStop, setWatchedStop] = useState(null);

  return (
    <WatchedStopContext.Provider value={{ watchedStop, setWatchedStop }}>
      {children}
    </WatchedStopContext.Provider>
  );
}

export function useWatchedStop() {
  return useContext(WatchedStopContext);
}
