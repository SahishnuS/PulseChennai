import React, { useState, useEffect } from 'react';
import { Bell, Map, Globe, User, Shield, Info } from 'lucide-react';

// A simple local storage hook
function useLocalStorage(key, initialValue) {
  const [storedValue, setStoredValue] = useState(() => {
    try {
      const item = window.localStorage.getItem(key);
      return item ? JSON.parse(item) : initialValue;
    } catch (error) {
      console.warn(error);
      return initialValue;
    }
  });

  const setValue = (value) => {
    try {
      const valueToStore = value instanceof Function ? value(storedValue) : value;
      setStoredValue(valueToStore);
      window.localStorage.setItem(key, JSON.stringify(valueToStore));
    } catch (error) {
      console.warn(error);
    }
  };

  return [storedValue, setValue];
}

const CATEGORIES = [
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'map', label: 'Map Display', icon: Map },
  { id: 'language', label: 'Language', icon: Globe },
  { id: 'account', label: 'Account', icon: User },
  { id: 'privacy', label: 'Data & Privacy', icon: Shield },
  { id: 'about', label: 'About', icon: Info },
];

export default function SettingsPage() {
  const [activeCategory, setActiveCategory] = useState('notifications');

  // Settings State
  const [arrivalAlerts, setArrivalAlerts] = useLocalStorage('pulse_arrivalAlerts', true);
  const [deviationAlerts, setDeviationAlerts] = useLocalStorage('pulse_deviationAlerts', true);
  const [ghostWarnings, setGhostWarnings] = useLocalStorage('pulse_ghostWarnings', true);
  const [alertLeadTime, setAlertLeadTime] = useLocalStorage('pulse_alertLeadTime', '5');

  const [h3Heatmap, setH3Heatmap] = useLocalStorage('pulse_h3Heatmap', false);
  const [relScore, setRelScore] = useLocalStorage('pulse_relScore', false);
  const [routePolylines, setRoutePolylines] = useLocalStorage('pulse_routePolylines', true);
  const [mapTheme, setMapTheme] = useLocalStorage('pulse_mapTheme', 'dark');

  const [language, setLanguage] = useLocalStorage('pulse_language', 'en');

  const [displayName, setDisplayName] = useLocalStorage('pulse_displayName', 'Jeeva P.');
  const [registeredBus] = useLocalStorage('pulse_registeredBus', null); // read-only for now

  const [shareLocation, setShareLocation] = useLocalStorage('pulse_shareLocation', false);

  const renderToggle = (label, checked, onChange, description) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '0.95rem', fontWeight: 500, color: 'var(--color-text-primary)' }}>{label}</span>
        <div
          onClick={() => onChange(!checked)}
          style={{
            width: '44px',
            height: '24px',
            background: checked ? 'var(--color-accent)' : 'var(--color-bg-elevated)',
            border: `1px solid ${checked ? 'var(--color-accent)' : 'var(--color-border)'}`,
            borderRadius: '12px',
            position: 'relative',
            cursor: 'pointer',
            transition: 'background 0.2s',
          }}
        >
          <div style={{
            width: '20px',
            height: '20px',
            background: checked ? '#080C14' : 'var(--color-text-secondary)',
            borderRadius: '50%',
            position: 'absolute',
            top: '1px',
            left: checked ? '21px' : '1px',
            transition: 'left 0.2s',
          }} />
        </div>
      </div>
      {description && <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>{description}</div>}
    </div>
  );

  const renderCategoryContent = () => {
    switch (activeCategory) {
      case 'notifications':
        return (
          <div className="settings-panel">
            <h2 style={{ fontSize: '1.2rem', marginBottom: '24px', color: 'var(--color-text-primary)' }}>Notifications</h2>
            {renderToggle('Bus Arrival Alerts', arrivalAlerts, setArrivalAlerts, 'Alerts when watched bus is 400m away.')}
            {renderToggle('Route Deviation Alerts', deviationAlerts, setDeviationAlerts)}
            {renderToggle('Ghost Bus Warnings', ghostWarnings, setGhostWarnings, 'Notified when your bus loses GPS.')}
            
            <div style={{ marginTop: '24px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontSize: '0.95rem', fontWeight: 500, color: 'var(--color-text-primary)' }}>Alert lead time</label>
              <select
                value={alertLeadTime}
                onChange={e => setAlertLeadTime(e.target.value)}
                style={{
                  background: 'var(--color-bg-elevated)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-primary)',
                  padding: '10px 14px',
                  borderRadius: '8px',
                  fontFamily: 'inherit',
                  fontSize: '0.9rem',
                }}
              >
                <option value="2">2 min</option>
                <option value="5">5 min</option>
                <option value="10">10 min</option>
              </select>
            </div>
          </div>
        );

      case 'map':
        return (
          <div className="settings-panel">
            <h2 style={{ fontSize: '1.2rem', marginBottom: '24px', color: 'var(--color-text-primary)' }}>Map Display</h2>
            {renderToggle('H3 Demand Heatmap', h3Heatmap, setH3Heatmap)}
            {renderToggle('Show bus reliability score on markers', relScore, setRelScore)}
            {renderToggle('Show route polylines', routePolylines, setRoutePolylines)}
            
            <div style={{ marginTop: '24px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontSize: '0.95rem', fontWeight: 500, color: 'var(--color-text-primary)' }}>Map theme</label>
              <select
                value={mapTheme}
                onChange={e => setMapTheme(e.target.value)}
                style={{
                  background: 'var(--color-bg-elevated)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-primary)',
                  padding: '10px 14px',
                  borderRadius: '8px',
                  fontFamily: 'inherit',
                  fontSize: '0.9rem',
                }}
              >
                <option value="dark">Dark</option>
                <option value="satellite">Satellite</option>
                <option value="standard">Standard</option>
              </select>
            </div>
          </div>
        );

      case 'language':
        return (
          <div className="settings-panel">
            <h2 style={{ fontSize: '1.2rem', marginBottom: '24px', color: 'var(--color-text-primary)' }}>Language</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
                <input type="radio" value="en" checked={language === 'en'} onChange={() => setLanguage('en')} />
                <span style={{ fontSize: '0.95rem', color: 'var(--color-text-primary)' }}>English</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
                <input type="radio" value="ta" checked={language === 'ta'} onChange={() => setLanguage('ta')} />
                <span style={{ fontSize: '0.95rem', color: 'var(--color-text-primary)' }}>தமிழ் (Tamil)</span>
              </label>
            </div>
            <p style={{ marginTop: '16px', fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>
              Note: Powers the Gemini AI assistant responses.
            </p>
          </div>
        );

      case 'account':
        return (
          <div className="settings-panel">
            <h2 style={{ fontSize: '1.2rem', marginBottom: '24px', color: 'var(--color-text-primary)' }}>Account</h2>
            
            <div style={{ marginBottom: '20px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontSize: '0.95rem', fontWeight: 500, color: 'var(--color-text-primary)' }}>Display Name</label>
              <input
                type="text"
                value={displayName}
                onChange={e => setDisplayName(e.target.value)}
                style={{
                  background: 'var(--color-bg-elevated)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-primary)',
                  padding: '10px 14px',
                  borderRadius: '8px',
                  fontFamily: 'inherit',
                  fontSize: '0.95rem',
                }}
              />
            </div>

            <div style={{ marginBottom: '24px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontSize: '0.95rem', fontWeight: 500, color: 'var(--color-text-primary)' }}>Registered Bus</label>
              <div style={{
                background: 'rgba(255,255,255,0.05)',
                padding: '12px 14px',
                borderRadius: '8px',
                color: registeredBus ? 'var(--color-accent)' : 'var(--color-text-secondary)',
                fontSize: '0.95rem',
                fontFamily: 'var(--font-data)',
                border: '1px dashed var(--color-border)'
              }}>
                {registeredBus ? registeredBus : 'Not registered'}
              </div>
            </div>

            <button style={{
              background: 'var(--color-bg-elevated)',
              border: '1px solid var(--color-accent)',
              color: 'var(--color-accent)',
              padding: '10px 16px',
              borderRadius: '8px',
              cursor: 'pointer',
              fontWeight: 600,
            }}>
              Manage Registration
            </button>
          </div>
        );

      case 'privacy':
        return (
          <div className="settings-panel">
            <h2 style={{ fontSize: '1.2rem', marginBottom: '24px', color: 'var(--color-text-primary)' }}>Data & Privacy</h2>
            {renderToggle('Share anonymous location for crowdsource GPS', shareLocation, setShareLocation, 'Used to recover Ghost Bus positions. No personal data stored.')}
            
            <div style={{ marginTop: '32px', paddingTop: '24px', borderTop: '1px solid var(--color-border)' }}>
              <button style={{
                background: 'transparent',
                border: '1px solid var(--color-danger)',
                color: 'var(--color-danger)',
                padding: '10px 16px',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: 600,
                width: '100%',
              }}>
                Clear local ticket history
              </button>
            </div>
          </div>
        );

      case 'about':
        return (
          <div className="settings-panel">
            <h2 style={{ fontSize: '1.2rem', marginBottom: '24px', color: 'var(--color-text-primary)' }}>About</h2>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '0.9rem', color: 'var(--color-text-primary)' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '12px' }}>
                <span style={{ color: 'var(--color-text-secondary)' }}>App name:</span>
                <span>PULSE Chennai Transit Engine</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '12px' }}>
                <span style={{ color: 'var(--color-text-secondary)' }}>Version:</span>
                <span style={{ fontFamily: 'var(--font-data)' }}>1.0.0-hackathon</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '12px' }}>
                <span style={{ color: 'var(--color-text-secondary)' }}>Backend:</span>
                <span>FastAPI + PostGIS + Kafka</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '12px' }}>
                <span style={{ color: 'var(--color-text-secondary)' }}>ML Models:</span>
                <span>XGBoost + LightGBM Ensemble</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '12px' }}>
                <span style={{ color: 'var(--color-text-secondary)' }}>Data Sources:</span>
                <span>MTC GTFS, TomTom Traffic, Uber Movement (825K records)</span>
              </div>
            </div>

            <div style={{ marginTop: '24px' }}>
              <a href="/architecture" style={{ color: 'var(--color-accent)', textDecoration: 'underline', fontSize: '0.9rem' }}>
                View Architecture Diagram
              </a>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div style={{
      width: '100%',
      height: '100%',
      overflowY: 'auto',
      padding: '24px',
      background: 'var(--color-bg-base)',
      display: 'flex',
      flexDirection: 'column'
    }}>
      <h1 style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--color-text-primary)', marginBottom: '32px' }}>
        Settings
      </h1>
      
      <div className="settings-layout">
        {/* Left Column - Categories */}
        <div className="settings-sidebar">
          {CATEGORIES.map(cat => {
            const Icon = cat.icon;
            const isActive = activeCategory === cat.id;
            return (
              <button
                key={cat.id}
                onClick={() => setActiveCategory(cat.id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: '12px',
                  width: '100%', padding: '12px 16px',
                  background: isActive ? 'var(--color-bg-elevated)' : 'transparent',
                  border: 'none',
                  borderRadius: '8px',
                  color: isActive ? 'var(--color-accent)' : 'var(--color-text-secondary)',
                  fontWeight: isActive ? 600 : 500,
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s',
                }}
              >
                <Icon size={18} />
                {cat.label}
              </button>
            );
          })}
        </div>

        {/* Right Column - Panel */}
        <div className="settings-content">
          <div style={{
            background: 'var(--color-bg-panel)',
            border: '1px solid var(--color-border)',
            borderRadius: '16px',
            padding: '24px',
            boxShadow: 'var(--shadow-panel)'
          }}>
            {renderCategoryContent()}
          </div>
        </div>
      </div>
      
      <style>{`
        .settings-layout {
          display: grid;
          grid-template-columns: 240px 1fr;
          gap: 32px;
          align-items: flex-start;
          max-width: 1000px;
        }
        
        @media (max-width: 768px) {
          .settings-layout {
            grid-template-columns: 1fr;
            gap: 24px;
          }
          .settings-sidebar {
            display: flex;
            overflow-x: auto;
            padding-bottom: 8px;
            gap: 8px;
          }
          .settings-sidebar button {
            width: auto;
            white-space: nowrap;
          }
        }
      `}</style>
    </div>
  );
}
