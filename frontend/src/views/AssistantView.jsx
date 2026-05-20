import React, { useState, useRef, useEffect } from 'react';
import { Bus, Send, Plus, MessageCircle, Clock, Mic, Volume2, X } from 'lucide-react';
import { API_BASE } from '../lib/supabase';

// ── Mock past conversations for the sidebar ──
const MOCK_CONVERSATIONS = [
  { id: 'conv-1', title: 'Route 19 ETA query', time: '2 hours ago', preview: 'How long to T Nagar?' },
  { id: 'conv-2', title: 'Bus 102X crowding', time: '5 hours ago', preview: 'Is 102X crowded now?' },
  { id: 'conv-3', title: 'T Nagar schedule', time: 'Yesterday', preview: 'When is the last bus?' },
  { id: 'conv-4', title: 'Ghost bus alert', time: 'Yesterday', preview: 'Why did my bus disappear?' },
];

// ── Suggestion chips ──
const SUGGESTION_CHIPS = {
  en: [
    'Which bus reaches T Nagar fastest right now?',
    'Is BUS_102X_001 running on time?',
    'Show me my active ticket status',
    'Why did I get a route deviation alert?',
    'How does ghost bus recovery work?',
  ],
  ta: [
    'T Nagar போக எந்த பஸ் எடுக்கணும்?',
    'BUS_102X_001 நேரத்தில் வருகிறதா?',
    'என் active ticket status காட்டு',
    'Route deviation alert ஏன் வந்தது?',
    'Ghost bus recovery எப்படி வேலை செய்கிறது?',
  ],
};

export default function AssistantView({ language }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [activeConvId, setActiveConvId] = useState(null);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [isListening, setIsListening] = useState(false);
  const chatEndRef = useRef(null);
  const textareaRef = useRef(null);
  const recognitionRef = useRef(null);

  // ── Restore from sessionStorage on mount ──
  useEffect(() => {
    const saved = sessionStorage.getItem('pulse_chat_history');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed.length > 0) {
          setMessages(parsed);
          setShowSuggestions(false);
        }
      } catch (e) { /* ignore corrupt data */ }
    }
  }, []);

  // ── Persist to sessionStorage on every update ──
  useEffect(() => {
    if (messages.length > 0) {
      sessionStorage.setItem('pulse_chat_history', JSON.stringify(messages));
    }
  }, [messages]);

  // ── Auto-scroll to latest message ──
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  // ── Auto-resize textarea ──
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
    }
  }, [input]);

  // ── Speech recognition ──
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = language === 'ta' ? 'ta-IN' : 'en-IN';
      recognition.onresult = (event) => {
        const text = event.results[0][0].transcript;
        setInput(text);
        setIsListening(false);
      };
      recognition.onerror = () => setIsListening(false);
      recognition.onend = () => setIsListening(false);
      recognitionRef.current = recognition;
    }
  }, [language]);

  const speak = (text) => {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = language === 'ta' ? 'ta-IN' : 'en-IN';
    utterance.rate = 0.9;
    window.speechSynthesis.speak(utterance);
  };

  // ── Build ticket context from localStorage ──
  const getTicketContext = () => {
    try {
      const tickets = JSON.parse(localStorage.getItem('pulse_tickets') || '[]');
      const active = tickets.find(t => t.status === 'ACTIVE');
      if (active) {
        return `User holds ticket ${active.id} for Route ${active.route}, from ${active.from} to ${active.to}, fare ₹${active.fare}`;
      }
    } catch (e) { /* ignore */ }
    return '';
  };

  // ── Send message to /api/chat ──
  const handleSend = async (textOverride) => {
    const text = textOverride || input;
    if (!text.trim()) return;

    const userMsg = { role: 'user', content: text, timestamp: new Date().toISOString() };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setShowSuggestions(false);
    setIsTyping(true);

    try {
      // Build history for API (exclude timestamps for the API payload)
      const historyForApi = messages.map(m => ({ role: m.role, content: m.content }));
      const ticketContext = getTicketContext();

      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          history: historyForApi,
          user_id: localStorage.getItem('pulse_user_id') || 'demo_user',
          language,
          ticket_context: ticketContext,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        const assistantMsg = {
          role: 'assistant',
          content: data.reply,
          timestamp: new Date().toISOString(),
        };
        // Replace history with server's trimmed version + timestamps
        const updatedWithTimestamps = data.updated_history.map(m => ({
          ...m,
          timestamp: m.timestamp || new Date().toISOString(),
        }));
        setMessages(updatedWithTimestamps);
        speak(data.reply);
      } else {
        // Fallback: use old /api/ai/query endpoint
        const fallbackRes = await fetch(`${API_BASE}/api/ai/query`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text, language, context: {} }),
        });
        const fallbackData = await fallbackRes.json();
        const reply = fallbackData.response || 'Sorry, I encountered an error.';
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: reply,
          timestamp: new Date().toISOString(),
        }]);
        speak(reply);
      }
    } catch (e) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: language === 'en'
          ? "I'm having trouble connecting. Please check if the backend server is running on port 8000."
          : 'இணைப்பில் சிக்கல். Backend server port 8000-ல் இயங்குகிறதா சரிபார்க்கவும்.',
        timestamp: new Date().toISOString(),
      }]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleNewChat = () => {
    setMessages([]);
    setShowSuggestions(true);
    setActiveConvId(null);
    sessionStorage.removeItem('pulse_chat_history');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return '';
    const d = new Date(timestamp);
    return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div style={{
      height: '100%', display: 'flex',
      background: 'var(--color-bg-base)',
    }}>
      {/* ── Left Sidebar: Conversations ── */}
      <aside style={{
        width: '260px', flexShrink: 0,
        borderRight: '1px solid var(--color-border)',
        display: 'flex', flexDirection: 'column',
        background: 'var(--color-bg-panel)',
      }}>
        <div style={{ padding: '20px 16px 12px' }}>
          <p style={{
            fontSize: '10px', fontWeight: 700, color: 'var(--color-text-muted)',
            fontFamily: 'var(--font-data)', letterSpacing: '1.5px', marginBottom: '12px',
          }}>
            CONVERSATIONS
          </p>
          <button
            onClick={handleNewChat}
            style={{
              width: '100%', padding: '10px 14px',
              border: '1px solid var(--color-accent)',
              borderRadius: '8px', background: 'transparent',
              color: 'var(--color-accent)', cursor: 'pointer',
              fontWeight: 600, fontSize: '0.85rem',
              display: 'flex', alignItems: 'center', gap: '8px',
              transition: 'all 0.2s',
            }}
            onMouseOver={e => { e.currentTarget.style.background = 'rgba(0,212,255,0.08)'; }}
            onMouseOut={e => { e.currentTarget.style.background = 'transparent'; }}
          >
            <Plus size={16} />
            New Chat
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px' }}>
          {/* Current active conversation */}
          {messages.length > 0 && (
            <div
              style={{
                padding: '12px',
                borderRadius: '8px',
                background: 'rgba(0,212,255,0.06)',
                borderLeft: '3px solid var(--color-accent)',
                marginBottom: '4px', cursor: 'pointer',
              }}
            >
              <p style={{
                fontSize: '0.85rem', fontWeight: 600,
                color: 'var(--color-text-primary)',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                {messages[0]?.content?.substring(0, 30) || 'Current chat'}...
              </p>
              <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '4px' }}>
                Just now
              </p>
            </div>
          )}

          {/* Mock past conversations */}
          {MOCK_CONVERSATIONS.map(conv => (
            <div
              key={conv.id}
              onClick={() => setActiveConvId(conv.id)}
              style={{
                padding: '12px',
                borderRadius: '8px',
                cursor: 'pointer',
                borderLeft: activeConvId === conv.id
                  ? '3px solid var(--color-accent)'
                  : '3px solid transparent',
                background: activeConvId === conv.id
                  ? 'rgba(0,212,255,0.06)'
                  : 'transparent',
                transition: 'all 0.15s',
                marginBottom: '2px',
              }}
              onMouseOver={e => {
                if (activeConvId !== conv.id) e.currentTarget.style.background = 'rgba(255,255,255,0.03)';
              }}
              onMouseOut={e => {
                if (activeConvId !== conv.id) e.currentTarget.style.background = 'transparent';
              }}
            >
              <p style={{
                fontSize: '0.85rem', fontWeight: 600,
                color: 'var(--color-text-primary)',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                {conv.title}
              </p>
              <div style={{
                display: 'flex', justifyContent: 'space-between', marginTop: '4px',
              }}>
                <p style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                  {conv.preview}
                </p>
                <p style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)', flexShrink: 0 }}>
                  {conv.time}
                </p>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* ── Right Main Area ── */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        position: 'relative',
      }}>
        {/* Chat Messages */}
        <div style={{
          flex: 1, overflowY: 'auto', padding: '24px',
          display: 'flex', flexDirection: 'column',
        }}>
          {/* ── Empty state / Suggestions ── */}
          {showSuggestions && messages.length === 0 && (
            <div style={{
              flex: 1, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center',
              gap: '24px', maxWidth: '560px', margin: '0 auto',
            }}>
              <Bus size={48} color="var(--color-accent)" style={{ opacity: 0.5 }} />
              <h2 style={{
                fontFamily: 'var(--font-data)',
                fontSize: '1.2rem', fontWeight: 700,
                color: 'var(--color-text-primary)',
                letterSpacing: '0.5px',
              }}>
                PULSE TRANSIT ASSISTANT
              </h2>
              <p style={{
                color: 'var(--color-text-secondary)',
                fontSize: '0.9rem', textAlign: 'center',
              }}>
                {language === 'en'
                  ? 'Ask about routes, ETAs, delays, or your active ticket.'
                  : 'Routes, ETAs, தாமதங்கள் அல்லது உங்கள் active ticket பற்றி கேளுங்கள்.'}
              </p>

              <div style={{
                display: 'grid', gridTemplateColumns: '1fr 1fr',
                gap: '10px', width: '100%', marginTop: '8px',
              }}>
                {(SUGGESTION_CHIPS[language] || SUGGESTION_CHIPS.en).map((chip, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(chip)}
                    style={{
                      padding: '14px 16px',
                      background: 'transparent',
                      border: '1px solid var(--color-border)',
                      borderRadius: '4px',
                      color: 'var(--color-text-primary)',
                      fontSize: '0.82rem',
                      fontFamily: 'var(--font-body)',
                      textAlign: 'left',
                      cursor: 'pointer',
                      transition: 'all 0.15s',
                      lineHeight: 1.4,
                    }}
                    onMouseOver={e => {
                      e.currentTarget.style.borderColor = 'var(--color-accent)';
                      e.currentTarget.style.background = 'rgba(0,212,255,0.04)';
                    }}
                    onMouseOut={e => {
                      e.currentTarget.style.borderColor = 'var(--color-border)';
                      e.currentTarget.style.background = 'transparent';
                    }}
                  >
                    {chip}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* ── Messages ── */}
          {messages.map((msg, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: '12px',
              }}
            >
              <div style={{
                maxWidth: '72%',
                padding: '14px 18px',
                borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                background: msg.role === 'user'
                  ? 'rgba(0,212,255,0.1)'
                  : 'var(--color-bg-elevated, rgba(30,41,59,0.8))',
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-primary)',
                fontSize: '0.9rem',
                lineHeight: 1.6,
                position: 'relative',
              }}>
                <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{msg.content}</p>
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
                  gap: '8px', marginTop: '8px',
                }}>
                  <span style={{
                    fontSize: '0.65rem', color: 'var(--color-text-muted)',
                    fontFamily: 'var(--font-data)',
                  }}>
                    {formatTime(msg.timestamp)}
                  </span>
                  {msg.role === 'assistant' && (
                    <button
                      onClick={() => speak(msg.content)}
                      style={{
                        background: 'none', border: 'none',
                        color: 'var(--color-text-muted)', cursor: 'pointer',
                        padding: '2px', display: 'flex',
                      }}
                      title="Read aloud"
                    >
                      <Volume2 size={12} />
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}

          {/* ── Typing indicator ── */}
          {isTyping && (
            <div style={{
              display: 'flex', justifyContent: 'flex-start',
              marginBottom: '12px',
            }}>
              <div style={{
                padding: '14px 22px',
                borderRadius: '16px 16px 16px 4px',
                background: 'var(--color-bg-elevated, rgba(30,41,59,0.8))',
                border: '1px solid var(--color-border)',
                display: 'flex', gap: '6px', alignItems: 'center',
              }}>
                {[0, 1, 2].map(dot => (
                  <div key={dot} style={{
                    width: '8px', height: '8px', borderRadius: '50%',
                    background: 'var(--color-accent)',
                    animation: `typingPulse 1.4s infinite ease-in-out`,
                    animationDelay: `${dot * 0.2}s`,
                  }} />
                ))}
              </div>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        {/* ── Bottom Input Bar ── */}
        <div style={{
          padding: '16px 24px',
          background: 'var(--color-bg-elevated, rgba(30,41,59,0.8))',
          borderTop: '1px solid var(--color-border)',
          display: 'flex', alignItems: 'flex-end', gap: '12px',
        }}>
          <button
            onClick={() => {
              if (!recognitionRef.current) return;
              if (isListening) {
                recognitionRef.current.stop();
                setIsListening(false);
              } else {
                recognitionRef.current.start();
                setIsListening(true);
              }
            }}
            style={{
              width: '40px', height: '40px', borderRadius: '50%',
              border: isListening ? '2px solid var(--color-accent)' : '1px solid var(--color-border)',
              background: isListening ? 'rgba(0,212,255,0.1)' : 'transparent',
              color: isListening ? 'var(--color-accent)' : 'var(--color-text-muted)',
              cursor: 'pointer', display: 'flex',
              alignItems: 'center', justifyContent: 'center',
              flexShrink: 0, transition: 'all 0.2s',
            }}
            title={isListening ? 'Stop listening' : 'Voice input'}
          >
            <Mic size={18} />
          </button>

          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={language === 'en' ? 'Ask PULSE anything...' : 'PULSE-ஐ எதையும் கேளுங்கள்...'}
            rows={1}
            style={{
              flex: 1, resize: 'none',
              background: 'transparent',
              border: '1px solid var(--color-border)',
              borderRadius: '12px',
              color: 'var(--color-text-primary)',
              fontSize: '0.95rem',
              padding: '10px 16px',
              outline: 'none',
              fontFamily: 'var(--font-body)',
              lineHeight: 1.5,
              maxHeight: '120px',
              transition: 'border-color 0.2s',
            }}
            onFocus={e => { e.target.style.borderColor = 'var(--color-accent)'; }}
            onBlur={e => { e.target.style.borderColor = 'var(--color-border)'; }}
          />

          <button
            onClick={() => handleSend()}
            disabled={!input.trim()}
            style={{
              width: '40px', height: '40px', borderRadius: '50%',
              border: 'none',
              background: input.trim() ? 'var(--color-accent)' : 'var(--color-border)',
              color: input.trim() ? '#080C14' : 'var(--color-text-muted)',
              cursor: input.trim() ? 'pointer' : 'not-allowed',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0, transition: 'all 0.2s',
            }}
          >
            <Send size={18} />
          </button>
        </div>
      </div>

      {/* ── Keyframe animation injected ── */}
      <style>{`
        @keyframes typingPulse {
          0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
          40% { transform: scale(1); opacity: 1; }
        }
      `}</style>
    </div>
  );
}
