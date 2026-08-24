/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg:        { DEFAULT: '#080c14', 100: '#0d1220', 200: '#111827', 300: '#1a2235' },
        surface:   { DEFAULT: '#0f1520', card: 'rgba(255,255,255,0.03)', hover: 'rgba(255,255,255,0.06)' },
        border:    { DEFAULT: 'rgba(255,255,255,0.07)', bright: 'rgba(255,255,255,0.14)' },
        accent:    { DEFAULT: '#1e90ff', dim: 'rgba(30,144,255,0.15)', glow: 'rgba(30,144,255,0.3)' },
        bull:      { DEFAULT: '#00d97e', dim: 'rgba(0,217,126,0.15)' },
        bear:      { DEFAULT: '#ff4560', dim: 'rgba(255,69,96,0.15)' },
        gold:      { DEFAULT: '#fbbf24', dim: 'rgba(251,191,36,0.15)' },
        text:      { primary: '#e2e8f0', secondary: '#8b96a7', muted: '#4a5568' },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
        sans: ['"Inter"', 'system-ui', 'sans-serif'],
      },
      backdropBlur: { xs: '2px' },
      animation: {
        'fade-in':    'fadeIn 0.2s ease-out',
        'slide-up':   'slideUp 0.3s ease-out',
        'slide-in':   'slideIn 0.25s ease-out',
        'pulse-slow': 'pulse 3s infinite',
        'glow':       'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        fadeIn:  { from: { opacity: '0' },                              to: { opacity: '1' } },
        slideUp: { from: { opacity: '0', transform: 'translateY(8px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        slideIn: { from: { opacity: '0', transform: 'translateX(-8px)' },to: { opacity: '1', transform: 'translateX(0)' } },
        glow:    { from: { boxShadow: '0 0 5px rgba(30,144,255,0.2)' }, to: { boxShadow: '0 0 20px rgba(30,144,255,0.5)' } },
      },
      boxShadow: {
        glass: '0 4px 24px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.06)',
        panel: '0 0 0 1px rgba(255,255,255,0.07), 0 8px 32px rgba(0,0,0,0.5)',
        accent: '0 0 20px rgba(30,144,255,0.25)',
      },
    },
  },
  plugins: [],
}
