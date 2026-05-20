import React from 'react';
import ReactDOM from 'react-dom/client';
import './styles/tokens.css';
import App from './App';
import './index.css';
import { WatchedStopProvider } from './context/WatchedStopContext';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <WatchedStopProvider>
      <App />
    </WatchedStopProvider>
  </React.StrictMode>
);