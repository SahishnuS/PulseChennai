import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { LayoutDashboard, Ticket, Route, Headphones, Settings, LogOut, MessageCircle } from 'lucide-react';
import MapView from './views/MapView';
import AssistantView from './views/AssistantView';
import JourneyView from './views/JourneyView';
import GhostBusBanner from './components/GhostBusBanner';
import SettingsPage from './pages/SettingsPage';
import TicketsPage from './pages/TicketsPage';
import PlanTripModal from './components/PlanTripModal';
import './index.css';

function DraggableChatButton({ onClick, isVisible }) {
  const [pos, setPos] = useState(() => {
    const saved = localStorage.getItem('chatBtnPos');
    return saved ? JSON.parse(saved) : { right: 24, bottom: 24 };
  });
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = React.useRef({ startX: 0, startY: 0, startRight: 0, startBottom: 0 });
  const [showGrid, setShowGrid] = useState(false);

  useEffect(() => {
    localStorage.setItem('chatBtnPos', JSON.stringify(pos));
  }, [pos]);

  const handlePointerDown = (e) => {
    e.preventDefault();
    e.target.setPointerCapture(e.pointerId);
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      startRight: pos.right,
      startBottom: pos.bottom
    };
    setIsDragging(false);
    setShowGrid(true);
  };

  const handlePointerMove = (e) => {
    if (!e.target.hasPointerCapture(e.pointerId)) return;
    
    const deltaX = e.clientX - dragRef.current.startX;
    const deltaY = e.clientY - dragRef.current.startY;
    
    // Only count as drag if moved more than 3px to avoid accidental drags on click
    if (!isDragging && (Math.abs(deltaX) > 3 || Math.abs(deltaY) > 3)) {
      setIsDragging(true);
    }
    
    if (isDragging) {
      const newRight = Math.max(16, Math.min(window.innerWidth - 72, dragRef.current.startRight - deltaX));
      const newBottom = Math.max(16, Math.min(window.innerHeight - 72, dragRef.current.startBottom - deltaY));
      setPos({ right: newRight, bottom: newBottom });
    }
  };

  const handlePointerUp = (e) => {
    e.target.releasePointerCapture(e.pointerId);
    setShowGrid(false);
    if (!isDragging) {
      onClick(); // Handle click if it wasn't a drag
    }
    // Small delay to prevent click from firing right after drag
    setTimeout(() => setIsDragging(false), 50);
  };

  if (!isVisible) return null;

  return (
    <>
      {showGrid && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          backgroundImage: 'linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)',
          backgroundSize: '40px 40px',
          zIndex: 9998,
          pointerEvents: 'none'
        }} />
      )}
      <button 
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        title="Drag to move"
        style={{
          position: 'absolute', bottom: pos.bottom, right: pos.right,
          width: '56px', height: '56px', borderRadius: '50%',
          background: 'var(--color-accent)', color: '#080C14', border: 'none',
          boxShadow: isDragging ? '0 10px 25px rgba(0,212,255,0.4)' : 'var(--shadow-accent)',
          cursor: isDragging ? 'grabbing' : 'grab', zIndex: 1000,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          transition: isDragging ? 'none' : 'box-shadow 0.2s',
          touchAction: 'none'
        }}
      >
        <MessageCircle size={24} style={{ pointerEvents: 'none' }} />
      </button>
    </>
  );
}

const TABS = [
  { id: 'map', label: 'Map', labelTa: 'வரைபடம்' },
  { id: 'assistant', label: 'Assistant', labelTa: 'உதவியாளர்' },
  { id: 'journey', label: 'Routes', labelTa: 'வழிகள்' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('map');
  const [language, setLanguage] = useState('en');
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [focusBusId, setFocusBusId] = useState(null);

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
          <h1 style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--color-accent)', fontFamily: 'var(--font-data)', letterSpacing: '-0.5px' }}>
            PULSE
          </h1>
          <p style={{ fontSize: '10px', color: 'var(--color-text-secondary)', fontWeight: 500, marginTop: '2px' }}>
            Chennai Transit Engine
          </p>
        </div>

        <nav style={{ flex: 1 }}>
          <button 
            className={`sidebar-nav-item ${activeTab === 'map' ? 'active' : ''}`}
            onClick={() => setActiveTab('map')}
          >
            <LayoutDashboard size={20} />
            {language === 'en' ? 'Dashboard' : 'முகப்பு'}
          </button>
          
          <button 
            className={`sidebar-nav-item ${activeTab === 'tickets' ? 'active' : ''}`}
            onClick={() => setActiveTab('tickets')}
          >
            <Ticket size={20} />
            {language === 'en' ? 'My Tickets' : 'டிக்கெட்டுகள்'}
          </button>

          <button 
            className={`sidebar-nav-item ${activeTab === 'journey' ? 'active' : ''}`}
            onClick={() => setActiveTab('journey')}
          >
            <Route size={20} />
            {language === 'en' ? 'Routes' : 'வழிகள்'}
          </button>

          <button className="sidebar-nav-item" onClick={() => setActiveTab('assistant')}>
            <Headphones size={20} />
            {language === 'en' ? 'Support' : 'உதவி'}
          </button>

          <button className="plan-trip-btn" onClick={() => setIsModalOpen(true)}>
            {language === 'en' ? 'Plan New Trip' : 'புதிய பயணம்'}
          </button>
        </nav>

        <div style={{ marginTop: 'auto', borderTop: '1px solid var(--color-border)', paddingTop: '16px' }}>
          <button 
            className={`sidebar-nav-item ${activeTab === 'settings' ? 'active' : ''}`} 
            onClick={() => setActiveTab('settings')}
          >
            <Settings size={20} />
            {language === 'en' ? 'Settings' : 'அமைப்புகள்'}
          </button>
          <button className="sidebar-nav-item" onClick={() => showToast(language === 'en' ? 'Logged out safely' : 'வெளியேறியது')}>
            <LogOut size={20} />
            {language === 'en' ? 'Logout' : 'வெளியேறு'}
          </button>
        </div>
      </aside>

      {/* ── Main Content Area ── */}
      <main className="main-content" style={{ position: 'relative', display: 'flex', flexDirection: 'column' }}>
        {/* Fixed Top Header */}
        <header style={{
          height: '52px',
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 24px',
          background: 'var(--color-bg-panel)',
          borderBottom: '1px solid var(--color-border)',
          zIndex: 100,
          position: 'relative'
        }}>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--color-text-primary)' }}>
              {activeTab === 'map' && (language === 'en' ? 'Dashboard' : 'முகப்பு')}
              {activeTab === 'tickets' && (language === 'en' ? 'My Tickets' : 'டிக்கெட்டுகள்')}
              {activeTab === 'journey' && (language === 'en' ? 'Routes' : 'வழிகள்')}
              {activeTab === 'assistant' && (language === 'en' ? 'Support' : 'உதவி')}
              {activeTab === 'settings' && (language === 'en' ? 'Settings' : 'அமைப்புகள்')}
            </h2>
          </div>
          
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
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
        <div style={{ position: 'absolute', top: 52, left: 0, right: 0, zIndex: 99 }}>
          <GhostBusBanner language={language} />
        </div>



        {/* ── View Content ── */}
        <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
          <AnimatePresence mode="wait">
            {activeTab === 'map' && (
              <motion.div key="map" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }} style={{ height: '100%' }}>
                <MapView language={language} focusBusId={focusBusId} onClearFocus={() => setFocusBusId(null)} />
              </motion.div>
            )}
            {activeTab === 'assistant' && (
              <motion.div key="assistant" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }} style={{ height: '100%' }}>
                <AssistantView language={language} />
              </motion.div>
            )}
            {activeTab === 'journey' && (
              <motion.div key="journey" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }} style={{ height: '100%' }}>
                <JourneyView language={language} onTrackBus={(busId) => {
                  setFocusBusId(busId);
                  setActiveTab('map');
                }} />
              </motion.div>
            )}
            {activeTab === 'settings' && (
              <motion.div key="settings" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }} style={{ height: '100%' }}>
                <SettingsPage />
              </motion.div>
            )}
            {activeTab === 'tickets' && (
              <motion.div key="tickets" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }} style={{ height: '100%' }}>
                <TicketsPage language={language} onTrackBus={(busId) => {
                  setFocusBusId(busId);
                  setActiveTab('map');
                }} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* ── Floating Assistant Button ── */}
        <DraggableChatButton 
          onClick={() => setActiveTab('assistant')} 
          isVisible={activeTab !== 'assistant' && !isModalOpen} 
        />

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
            <div className="toast slide-up">
              {toastMessage}
            </div>
          )}
        </AnimatePresence>

        <PlanTripModal 
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          language={language}
          onTrackBus={(busId) => {
            setFocusBusId(busId);
            setActiveTab('map');
          }}
        />
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