import React, { useState, useRef, useEffect } from 'react';
import { API_BASE } from '../lib/supabase';

const STARTER_PROMPTS = {
  en: [
    'Which bus goes to T Nagar?',
    'Is bus 19 crowded right now?',
    'Alert me before my stop',
  ],
  ta: [
    'T நகரம் செல்ல எந்த பேருந்து?',
    '19 இப்போது நெரிசலாக உள்ளதா?',
    'என் நிறுத்தத்திற்கு முன் எச்சரி',
  ],
};

export default function AssistantView({ language }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const chatEndRef = useRef(null);
  const recognitionRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const [interimText, setInterimText] = useState('');

  // Initialize speech recognition
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;

      recognition.onresult = (event) => {
        let final = '';
        let interim = '';

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            final += event.results[i][0].transcript;
          } else {
            interim += event.results[i][0].transcript;
          }
        }

        setInterimText(interim);
        
        if (final) {
          setInput(final);
          setInterimText('');
          setIsListening(false);
          recognition.stop();
          // Auto-send
          setTimeout(() => handleSend(final), 300);
        }
      };

      recognition.onerror = () => { setIsListening(false); setInterimText(''); };
      recognition.onend = () => { setIsListening(false); setInterimText(''); };

      recognitionRef.current = recognition;
    }
  }, []);

  // Update recognition language when it changes
  useEffect(() => {
    if (recognitionRef.current) {
      recognitionRef.current.lang = language === 'ta' ? 'ta-IN' : 'en-IN';
    }
  }, [language]);

  const speak = (text, lang) => {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang === 'ta' ? 'ta-IN' : 'en-IN';
    utterance.rate = 0.9;
    window.speechSynthesis.speak(utterance);
  };

  const toggleMic = () => {
    if (!recognitionRef.current) return;
    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      recognitionRef.current.lang = language === 'ta' ? 'ta-IN' : 'en-IN';
      recognitionRef.current.start();
      setIsListening(true);
    }
  };

  const handleSend = async (textOverride) => {
    const text = textOverride || input;
    if (!text.trim()) return;

    const userMsg = { role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsTyping(true);

    try {
      // Fetch bus context
      let busContext = {};
      try {
        const busRes = await fetch(`${API_BASE}/api/buses`);
        const busData = await busRes.json();
        busContext = { buses: busData.buses, routes: ['19', '102X', '515'] };
      } catch (e) { /* ignore */ }

      const res = await fetch(`${API_BASE}/api/ai/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          language,
          context: busContext,
        }),
      });

      const data = await res.json();
      const reply = data.response || 'Sorry, I could not process that.';

      setMessages(prev => [...prev, { role: 'assistant', content: reply }]);
      speak(reply, language);
    } catch (e) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: language === 'en' ? 'Sorry, I encountered an error. Please try again.' : 'மன்னிக்கவும், பிழை ஏற்பட்டது. மீண்டும் முயற்சிக்கவும்.',
      }]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleChipClick = (text) => {
    setInput(text);
    handleSend(text);
  };

  return (
    <div style={{
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      background: '#0F172A',
    }}>
      {/* ── Chat Messages ── */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
      }}>
        {messages.length === 0 && (
          <div style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '24px',
          }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '3rem', marginBottom: '12px' }}>🚌</div>
              <h2 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '4px' }}>
                {language === 'en' ? 'Chennai Bus Assistant' : 'சென்னை பேருந்து உதவியாளர்'}
              </h2>
              <p style={{ color: '#94A3B8', fontSize: '0.85rem' }}>
                {language === 'en' ? 'Ask me about routes, ETAs, or bus status' : 'வழிகள், ETA அல்லது பேருந்து நிலை பற்றி கேளுங்கள்'}
              </p>
            </div>

            {/* Starter chips */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%', maxWidth: '320px' }}>
              {(STARTER_PROMPTS[language] || STARTER_PROMPTS.en).map((prompt, i) => (
                <button
                  key={i}
                  onClick={() => handleChipClick(prompt)}
                  style={{
                    padding: '12px 16px',
                    borderRadius: '12px',
                    border: '1px solid #334155',
                    background: '#1E293B',
                    color: '#F8FAFC',
                    fontSize: '0.85rem',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'all 0.2s',
                    fontFamily: 'Inter, sans-serif',
                  }}
                  onMouseOver={e => e.target.style.background = '#334155'}
                  onMouseOut={e => e.target.style.background = '#1E293B'}
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} style={{
            display: 'flex',
            justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
            gap: '8px',
          }}>
            {msg.role === 'assistant' && (
              <div style={{
                width: '32px', height: '32px', borderRadius: '50%',
                background: '#1E293B', display: 'flex', alignItems: 'center',
                justifyContent: 'center', fontSize: '16px', flexShrink: 0,
              }}>
                🚌
              </div>
            )}
            <div style={{
              maxWidth: '75%',
              padding: '12px 16px',
              borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
              background: msg.role === 'user' ? '#3B82F6' : '#1E293B',
              color: '#F8FAFC',
              fontSize: '0.9rem',
              lineHeight: 1.5,
            }}>
              {msg.content}
              {msg.role === 'assistant' && (
                <button
                  onClick={() => speak(msg.content, language)}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: '#94A3B8', fontSize: '14px', marginLeft: '8px',
                    padding: '2px',
                  }}
                  title={language === 'en' ? 'Replay' : 'மீண்டும் கேளுங்கள்'}
                >
                  🔊
                </button>
              )}
            </div>
          </div>
        ))}

        {/* Typing indicator */}
        {isTyping && (
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <div style={{
              width: '32px', height: '32px', borderRadius: '50%',
              background: '#1E293B', display: 'flex', alignItems: 'center',
              justifyContent: 'center', fontSize: '16px',
            }}>
              🚌
            </div>
            <div style={{
              padding: '12px 16px', borderRadius: '16px 16px 16px 4px',
              background: '#1E293B',
            }}>
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* ── Input Bar ── */}
      <div style={{
        display: 'flex',
        gap: '8px',
        padding: '12px 16px',
        background: '#1E293B',
        borderTop: '1px solid #334155',
      }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          placeholder={language === 'en' ? 'Ask about buses...' : 'பேருந்துகள் பற்றி கேளுங்கள்...'}
          style={{
            flex: 1,
            padding: '12px 16px',
            borderRadius: '24px',
            border: '1px solid #334155',
            background: '#0F172A',
            color: '#F8FAFC',
            fontSize: '0.9rem',
            outline: 'none',
            fontFamily: 'Inter, sans-serif',
          }}
        />
        <button
          onClick={toggleMic}
          className={isListening ? 'mic-active' : ''}
          style={{
            width: '48px', height: '48px', borderRadius: '50%',
            border: 'none', cursor: 'pointer',
            background: isListening ? '#EF4444' : '#334155',
            color: 'white', fontSize: '20px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'background 0.2s',
          }}
        >
          🎤
        </button>
        <button
          onClick={() => handleSend()}
          style={{
            width: '48px', height: '48px', borderRadius: '50%',
            border: 'none', cursor: 'pointer',
            background: '#3B82F6',
            color: 'white', fontSize: '18px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          ➤
        </button>
      </div>

      {/* Listening indicator */}
      {isListening && (
        <div style={{
          position: 'absolute', inset: 0,
          background: 'rgba(10, 10, 10, 0.85)', backdropFilter: 'blur(16px)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          zIndex: 100, color: 'white',
        }}>
          <div style={{ position: 'relative', width: '120px', height: '120px', marginBottom: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {/* Pulsing rings */}
            <div style={{ position: 'absolute', inset: '-20px', border: '2px solid var(--accent)', borderRadius: '50%', animation: 'ripple 1.5s linear infinite' }} />
            <div style={{ position: 'absolute', inset: '-40px', border: '2px solid var(--accent)', borderRadius: '50%', animation: 'ripple 1.5s linear infinite 0.5s', opacity: 0 }} />
            
            <div style={{
              position: 'relative', width: '80px', height: '80px', borderRadius: '50%',
              background: 'linear-gradient(135deg, var(--accent), var(--accent-green))', 
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '32px', boxShadow: '0 0 40px var(--accent)', zIndex: 2
            }}>
              🎤
            </div>
          </div>

          <div style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '16px', color: 'var(--text-secondary)', letterSpacing: '1px', textTransform: 'uppercase' }}>
            {language === 'en' ? 'Listening...' : 'கேட்கிறது...'}
          </div>
          <div style={{ 
            fontSize: '1.8rem', fontWeight: 800, color: 'white', 
            maxWidth: '80%', textAlign: 'center', minHeight: '60px',
            lineHeight: 1.3
          }}>
            {interimText || (language === 'en' ? 'Speak now' : 'இப்போது பேசுங்கள்')}
          </div>
        </div>
      )}
    </div>
  );
}
