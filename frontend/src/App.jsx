import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import MapView from './views/MapView';
import AssistantView from './views/AssistantView';
import JourneyView from './views/JourneyView';
import GhostBusBanner from './components/GhostBusBanner';
import DemoMode from './components/DemoMode';
import './index.css';

const TABS = [
  { id: 'map', label: '🗺 Map', labelTa: '🗺 வரைபடம்' },
  { id: 'assistant', label: '🤖 Assistant', labelTa: '🤖 உதவியாளர்' },
  { id: 'journey', label: '🎯 Journey', labelTa: '🎯 பயணம்' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('map');
  const [language, setLanguage] = useState('en');
  const [loading, setLoading] = useState(true);

  // Simulate initial connection
  React.useEffect(() => {
    const timer = setTimeout(() => setLoading(false), 1500);
    return () => clearTimeout(timer);
  }, []);

  const toggleLanguage = () => setLanguage(prev => prev === 'en' ? 'ta' : 'en');

  const [toastMessage, setToastMessage] = useState(null);
  const showToast = (msg) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  if (loading) {
    return (
      <div style={{
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#0F172A',
        gap: '1rem',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <PulseIcon size={40} />
          <h1 style={{ fontSize: '1.8rem', fontWeight: 700, color: '#F8FAFC' }}>Pulse Chennai</h1>
        </div>
        <p style={{ color: '#94A3B8', fontSize: '0.9rem' }}>
          {language === 'en' ? 'Connecting to live bus network...' : 'நேரடி பேருந்து நெட்வொர்க்குடன் இணைக்கிறது...'}
        </p>
        <div style={{
          width: '200px', height: '4px', background: '#1E293B', borderRadius: '2px', overflow: 'hidden',
        }}>
          <div style={{
            width: '60%', height: '100%', background: 'linear-gradient(90deg, #3B82F6, #60A5FA)',
            borderRadius: '2px',
            animation: 'shimmer 1.5s infinite',
          }} />
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* ── Sidebar (Desktop) ── */}
      <aside className="sidebar">
        <div style={{ marginBottom: '40px', paddingLeft: '8px' }}>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--accent-green)', letterSpacing: '-0.5px' }}>
            Transit Pro
          </h1>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 500, marginTop: '2px' }}>
            {language === 'en' ? 'Urban Commuter' : 'நகர பயணி'}
          </p>
        </div>

        <nav style={{ flex: 1 }}>
          <button 
            className={`sidebar-nav-item ${activeTab === 'map' ? 'active' : ''}`}
            onClick={() => setActiveTab('map')}
          >
            <span style={{ fontSize: '1.1rem' }}>⊞</span>
            {language === 'en' ? 'Dashboard' : 'முகப்பு'}
          </button>
          
          <button 
            className={`sidebar-nav-item ${activeTab === 'journey' ? 'active' : ''}`}
            onClick={() => setActiveTab('journey')}
          >
            <span style={{ fontSize: '1.1rem' }}>🎫</span>
            {language === 'en' ? 'My Tickets' : 'டிக்கெட்டுகள்'}
          </button>

          <button className="sidebar-nav-item" onClick={() => showToast(language === 'en' ? 'Routes directory coming soon' : 'வழிகள் விரைவில் வரும்')}>
            <span style={{ fontSize: '1.1rem' }}>🚌</span>
            {language === 'en' ? 'Routes' : 'வழிகள்'}
          </button>

          <button className="sidebar-nav-item" onClick={() => setActiveTab('assistant')}>
            <span style={{ fontSize: '1.1rem' }}>🎧</span>
            {language === 'en' ? 'Support' : 'உதவி'}
          </button>

          <button className="plan-trip-btn" onClick={() => showToast(language === 'en' ? 'Trip planner coming soon' : 'பயணத் திட்டம் விரைவில் வரும்')}>
            {language === 'en' ? 'Plan New Trip' : 'புதிய பயணம்'}
          </button>
        </nav>

        <div style={{ marginTop: 'auto', borderTop: '1px solid var(--border)', paddingTop: '16px' }}>
          <button className="sidebar-nav-item" onClick={() => showToast(language === 'en' ? 'Settings opened' : 'அமைப்புகள்')}>
            <span style={{ fontSize: '1.1rem' }}>⚙️</span>
            {language === 'en' ? 'Settings' : 'அமைப்புகள்'}
          </button>
          <button className="sidebar-nav-item" onClick={() => showToast(language === 'en' ? 'Logged out safely' : 'வெளியேறியது')}>
            <span style={{ fontSize: '1.1rem' }}>🚪</span>
            {language === 'en' ? 'Logout' : 'வெளியேறு'}
          </button>
        </div>
      </aside>

      {/* ── Main Content Area ── */}
      <main className="main-content">
        {/* Top Header */}
        <header style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          padding: '16px 24px',
          background: 'transparent',
          position: 'absolute',
          top: 0, right: 0, left: 0,
          zIndex: 1000,
          pointerEvents: 'none' /* let clicks pass to map underneath except for buttons */
        }}>
          <div style={{ display: 'flex', gap: '16px', pointerEvents: 'auto' }}>
            <button
              onClick={toggleLanguage}
              style={{
                padding: '6px 14px',
                borderRadius: '20px',
                border: '1px solid var(--border)',
                background: 'var(--bg-secondary)',
                color: 'var(--text-primary)',
                fontSize: '0.8rem',
                cursor: 'pointer',
                fontWeight: 600,
                transition: 'all 0.2s',
              }}
            >
              {language === 'en' ? 'EN | தமிழ்' : 'தமிழ் | EN'}
            </button>
            <div style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              padding: '6px 12px', borderRadius: '20px',
              background: 'var(--bg-secondary)', border: '1px solid var(--border)'
            }}>
              <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px' }}>
                J
              </div>
              <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>Jeeva P.</span>
            </div>
          </div>
        </header>

        {/* ── Ghost Bus Banner ── */}
        <div style={{ position: 'absolute', top: 60, left: 0, right: 0, zIndex: 1000 }}>
          <GhostBusBanner language={language} />
        </div>

        {/* ── Demo Mode ── */}
        <DemoMode
          language={language}
          setActiveTab={setActiveTab}
        />

        {/* ── View Content ── */}
        <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
          <AnimatePresence mode="wait">
            {activeTab === 'map' && (
              <motion.div key="map" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }} style={{ height: '100%' }}>
                <MapView language={language} />
              </motion.div>
            )}
            {activeTab === 'assistant' && (
              <motion.div key="assistant" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }} style={{ height: '100%' }}>
                <AssistantView language={language} />
              </motion.div>
            )}
            {activeTab === 'journey' && (
              <motion.div key="journey" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }} style={{ height: '100%' }}>
                <JourneyView language={language} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* ── Floating Assistant Button (Matches Mockup) ── */}
        {activeTab !== 'assistant' && (
          <button 
            onClick={() => setActiveTab('assistant')}
            style={{
              position: 'absolute', bottom: '24px', right: '24px',
              width: '56px', height: '56px', borderRadius: '50%',
              background: 'var(--accent-green)', border: 'none',
              boxShadow: '0 4px 12px rgba(52, 211, 153, 0.4)',
              cursor: 'pointer', zIndex: 1000,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '1.5rem'
            }}
          >
            💬
          </button>
        )}

        {/* ── Bottom Tab Bar (Mobile Only) ── */}
        <nav className="bottom-tabs" style={{
          background: 'var(--bg-secondary)',
          borderTop: '1px solid var(--border)',
          zIndex: 1000,
        }}>
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                flex: 1,
                padding: '12px 0',
                background: 'transparent',
                border: 'none',
                color: activeTab === tab.id ? 'var(--accent)' : 'var(--text-secondary)',
                fontSize: '0.8rem',
                fontWeight: activeTab === tab.id ? 600 : 400,
                cursor: 'pointer',
                borderTop: activeTab === tab.id ? '2px solid var(--accent)' : '2px solid transparent',
                transition: 'all 0.2s',
                fontFamily: 'Inter, sans-serif',
              }}
            >
              {language === 'en' ? tab.label : tab.labelTa}
            </button>
          ))}
        </nav>
        {/* ── Toast Message ── */}
        <AnimatePresence>
          {toastMessage && (
            <motion.div
              initial={{ opacity: 0, y: 50, x: '-50%' }}
              animate={{ opacity: 1, y: 0, x: '-50%' }}
              exit={{ opacity: 0, y: 50, x: '-50%' }}
              style={{
                position: 'absolute', bottom: '100px', left: '50%',
                background: 'rgba(15, 23, 42, 0.9)', backdropFilter: 'blur(10px)',
                color: 'white', padding: '12px 24px', borderRadius: '30px',
                fontWeight: 600, fontSize: '0.95rem', zIndex: 9999,
                boxShadow: '0 10px 25px rgba(0,0,0,0.5)', border: '1px solid rgba(255,255,255,0.1)'
              }}
            >
              {toastMessage}
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}

function PulseIcon({ size = 24 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none">
      <circle cx="20" cy="20" r="4" fill="#3B82F6" />
      <circle cx="20" cy="20" r="10" stroke="#3B82F6" strokeWidth="2" opacity="0.6" fill="none" />
      <circle cx="20" cy="20" r="16" stroke="#3B82F6" strokeWidth="1.5" opacity="0.3" fill="none" />
      <circle cx="20" cy="20" r="19" stroke="#60A5FA" strokeWidth="1" opacity="0.15" fill="none" />
    </svg>
  );
}