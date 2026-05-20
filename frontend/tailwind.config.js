/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          accent: 'var(--color-accent)',
          ghost: 'var(--color-ghost-pulse)',
        },
        ui: {
          base: 'var(--color-bg-base)',
          panel: 'var(--color-bg-panel)',
          elevated: 'var(--color-bg-elevated)',
          border: 'var(--color-border)',
          success: 'var(--color-success)',
          warning: 'var(--color-warning)',
          danger: 'var(--color-danger)',
          text: {
            primary: 'var(--color-text-primary)',
            secondary: 'var(--color-text-secondary)',
            muted: 'var(--color-text-muted)',
          }
        }
      },
      fontFamily: {
        sans: ['var(--font-ui)'],
        mono: ['var(--font-data)'],
      },
    },
  },
  plugins: [],
}