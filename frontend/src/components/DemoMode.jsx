import React, { useState, useRef } from 'react';

const DEMO_STEPS = [
  { time: 0,  label: 'Dashboard View & Signal Panel' },
  { time: 15, label: 'Ghost Bus detected' },
  { time: 18, label: 'Alert broadcast & Marker change' },
  { time: 30, label: 'Switch to Journey Tracking' },
  { time: 50, label: 'Switch to Assistant View' },
  { time: 52, label: 'Voice input triggers' },
  { time: 56, label: 'AI replies in Tamil/English' },
  { time: 75, label: 'Signal Restored on Map' },
];

export default function DemoMode({ language, setActiveTab }) {
  const [running, setRunning] = useState(false);
  const [currentStep, setCurrentStep] = useState(-1);
  const timers = useRef([]);

  const startDemo = () => {
    if (running) return;
    setRunning(true);
    setCurrentStep(0);

    // Clear any existing timers
    timers.current.forEach(clearTimeout);
    timers.current = [];

    // Step 1: Map view
    setActiveTab('map');

    // Step 4 (30s): Switch to Journey
    timers.current.push(setTimeout(() => {
      setActiveTab('journey');
    }, 30000));

    // Step 5 (50s): Switch to Assistant
    timers.current.push(setTimeout(() => {
      setActiveTab('assistant');
    }, 50000));

    // Step 8 (75s): Back to map
    timers.current.push(setTimeout(() => {
      setActiveTab('map');
    }, 75000));

    // Update step indicators
    DEMO_STEPS.forEach((step, i) => {
      timers.current.push(setTimeout(() => {
        setCurrentStep(i);
      }, step.time * 1000));
    });

    // End demo
    timers.current.push(setTimeout(() => {
      setRunning(false);
      setCurrentStep(-1);
    }, 85000));
  };

  const stopDemo = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setRunning(false);
    setCurrentStep(-1);
  };

  return (
    <>
      {/* Demo button - floating bottom center */}
      <button
        onClick={running ? stopDemo : startDemo}
        style={{
          position: 'fixed',
          bottom: '24px',
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 2000,
          padding: '12px 24px',
          borderRadius: '30px',
          border: 'none',
          background: running ? 'var(--danger)' : 'var(--accent)',
          color: 'white',
          fontSize: '1rem',
          fontWeight: 800,
          cursor: 'pointer',
          fontFamily: 'Inter, sans-serif',
          boxShadow: running ? '0 8px 32px rgba(239, 68, 68, 0.5)' : '0 8px 32px rgba(37, 99, 235, 0.5)',
          transition: 'all 0.3s ease',
          letterSpacing: '1px'
        }}
      >
        {running ? '⏹ STOP DEMO' : '▶ RUN DEMO'}
      </button>

      {/* Step indicator */}
      {running && (
        <div style={{
          position: 'fixed',
          bottom: '80px',
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 2000,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '8px',
          padding: '12px 24px',
          borderRadius: '20px',
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border)',
          backdropFilter: 'blur(12px)',
          boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
        }}>
          <div style={{ display: 'flex', gap: '8px' }}>
            {DEMO_STEPS.map((_, i) => (
              <div
                key={i}
                className={`demo-dot ${i === currentStep ? 'active' : i < currentStep ? 'completed' : ''}`}
                style={{ width: '10px', height: '10px' }}
              />
            ))}
          </div>
          {currentStep >= 0 && currentStep < DEMO_STEPS.length && (
            <div style={{
              color: 'var(--accent-green)',
              fontSize: '0.85rem',
              fontWeight: 700,
              whiteSpace: 'nowrap',
            }}>
              Step {currentStep + 1}: {DEMO_STEPS[currentStep].label}
            </div>
          )}
        </div>
      )}
    </>
  );
}
