/** Tailwind CSS 3 — design system do Chama Clínica */
module.exports = {
  content: ['../templates/**/*.html', '../static/js/**/*.js'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter Variable"', 'Inter', 'system-ui', '-apple-system', '"Segoe UI"', 'sans-serif'],
        display: ['"Plus Jakarta Sans Variable"', '"Plus Jakarta Sans"', '"Inter Variable"', 'system-ui', 'sans-serif'],
      },
      colors: {
        brand: {
          50: '#eef4ff', 100: '#dbe7ff', 200: '#bdd3ff', 300: '#8fb4ff', 400: '#5b8cf7',
          500: '#3468ea', 600: '#214bd0', 700: '#1c3ca8', 800: '#1b3787', 900: '#1b3169', 950: '#0b1635',
        },
        accent: { 300: '#fff07a', 400: '#ffe94d', 500: '#fce500', 600: '#e6cf00' },
        ink: { 900: '#0b1635', 700: '#2b3a5c', 500: '#5b6b8c', 400: '#8593b0' },
      },
      boxShadow: {
        card: '0 1px 2px rgba(11,22,53,.04), 0 12px 32px -12px rgba(27,49,105,.14)',
        lift: '0 2px 4px rgba(11,22,53,.06), 0 20px 40px -16px rgba(27,49,105,.28)',
        glow: '0 10px 30px -8px rgba(52,104,234,.55)',
      },
      keyframes: {
        'fade-up': { '0%': { opacity: 0, transform: 'translateY(10px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
        'ring-out': { '0%': { transform: 'scale(.9)', opacity: .55 }, '100%': { transform: 'scale(1.9)', opacity: 0 } },
        'bell-shake': { '0%,100%': { transform: 'rotate(0)' }, '15%': { transform: 'rotate(14deg)' }, '30%': { transform: 'rotate(-12deg)' }, '45%': { transform: 'rotate(9deg)' }, '60%': { transform: 'rotate(-6deg)' }, '75%': { transform: 'rotate(3deg)' } },
        'toast-in': { '0%': { opacity: 0, transform: 'translateY(12px) scale(.98)' }, '100%': { opacity: 1, transform: 'translateY(0) scale(1)' } },
        'name-in': { '0%': { opacity: 0, transform: 'translateY(18px) scale(.98)' }, '100%': { opacity: 1, transform: 'translateY(0) scale(1)' } },
        'spin-slow': { to: { transform: 'rotate(360deg)' } },
      },
      animation: {
        'fade-up': 'fade-up .5s cubic-bezier(.2,.8,.2,1) both',
        'ring-out': 'ring-out 2.2s ease-out infinite',
        'bell-shake': 'bell-shake 1.2s ease-in-out infinite',
        'toast-in': 'toast-in .28s cubic-bezier(.2,.8,.2,1) both',
        'name-in': 'name-in .7s cubic-bezier(.2,.8,.2,1) both',
        'spin-slow': 'spin-slow 1s linear infinite',
      },
    },
  },
  plugins: [],
};
