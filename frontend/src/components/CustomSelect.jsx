import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';

/**
 * CustomSelect - A premium, highly visible dark-themed dropdown selector.
 * Resolves browser/OS-level option text rendering issues in dark mode.
 * 
 * @param {Object} props
 * @param {any} props.value - The active selected value.
 * @param {Function} props.onChange - Callback triggered on selection: (e) => void.
 * @param {Array<{value: any, label: string}>} props.options - Array of available options.
 * @param {Object} [props.style] - Styles applied to the root container.
 * @param {Object} [props.buttonStyle] - Styles applied to the select button itself.
 * @param {Object} [props.dropdownStyle] - Styles applied to the floating options menu.
 * @param {Object} [props.optionStyle] - Styles applied to each option row.
 */
export default function CustomSelect({
  value,
  onChange,
  options = [],
  style = {},
  buttonStyle = {},
  dropdownStyle = {},
  optionStyle = {}
}) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef(null);

  // Close the dropdown when clicking outside of it
  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const selectedOption = options.find(opt => String(opt.value) === String(value)) || options[0];

  const handleSelect = (val) => {
    if (onChange) {
      // Mock standard HTML event structure for drop-in compatibility
      onChange({ target: { value: val } });
    }
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} style={{ position: 'relative', width: '100%', ...style }}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        style={{
          width: '100%',
          padding: '10px 14px',
          background: 'var(--color-bg-elevated, #131E2E)',
          border: '1px solid var(--color-border, rgba(0, 212, 255, 0.12))',
          borderRadius: '8px',
          color: 'var(--color-text-primary, #E8F4FF)',
          fontSize: '0.9rem',
          textAlign: 'left',
          cursor: 'pointer',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontFamily: 'inherit',
          outline: 'none',
          boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
          transition: 'border-color 0.2s, box-shadow 0.2s',
          ...buttonStyle,
        }}
      >
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {selectedOption ? selectedOption.label : 'Select option...'}
        </span>
        <ChevronDown
          size={16}
          style={{
            color: 'var(--color-text-secondary, #6B8CAE)',
            transform: isOpen ? 'rotate(180deg)' : 'rotate(0)',
            transition: 'transform 0.2s ease',
            flexShrink: 0,
            marginLeft: '8px'
          }}
        />
      </button>

      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            zIndex: 9999,
            background: 'var(--color-bg-panel, #0D1520)',
            border: '1px solid var(--color-border, rgba(0, 212, 255, 0.12))',
            borderRadius: '8px',
            boxShadow: 'var(--shadow-panel, 0 8px 32px rgba(0,0,0,0.5))',
            maxHeight: '220px',
            overflowY: 'auto',
            padding: '4px',
            animation: 'fadeInDropdown 0.15s ease-out',
            ...dropdownStyle,
          }}
        >
          {options.length > 0 ? (
            options.map((opt) => {
              const isSelected = opt.value === value;
              return (
                <div
                  key={opt.value}
                  onClick={() => handleSelect(opt.value)}
                  style={{
                    padding: '10px 12px',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    color: isSelected ? 'var(--color-accent, #00D4FF)' : 'var(--color-text-primary, #E8F4FF)',
                    background: isSelected ? 'var(--color-accent-dim, rgba(0, 212, 255, 0.15))' : 'transparent',
                    fontSize: '0.9rem',
                    transition: 'background 0.15s, color 0.15s',
                    fontWeight: isSelected ? 600 : 400,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    ...optionStyle,
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) {
                      e.currentTarget.style.background = 'var(--color-bg-elevated, #131E2E)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) {
                      e.currentTarget.style.background = 'transparent';
                    }
                  }}
                >
                  {opt.label}
                </div>
              );
            })
          ) : (
            <div style={{ padding: '10px 12px', color: 'var(--color-text-muted, #3A5068)', fontSize: '0.9rem', textAlign: 'center' }}>
              No options available
            </div>
          )}
        </div>
      )}

      {/* Embedded CSS animation keyframes */}
      <style>{`
        @keyframes fadeInDropdown {
          from { opacity: 0; transform: translateY(-4px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
