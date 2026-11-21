/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#1F4FD1',
          hover: '#1841B2',
          light: '#EEF3FE',
          surface: '#E8EEFC',
        },
        page: '#F3F5F8',
        surface: '#FFFFFF',
        border: {
          DEFAULT: '#E1E5EB',
          subtle: '#EEF1F5',
        },
        content: {
          primary: '#141A24',
          secondary: '#4A5363',
          muted: '#616977',
          subtle: '#8E939D',
        },
        accent: {
          orange: '#FF7A45',
          peach: '#FFF6EC',
          amberBg: '#FFF8E8',
          amberBorder: '#F3E2B5',
          amberBadge: '#FFEFD9',
          green: '#1D7A40',
          greenBg: '#E3F2E7',
          greenBorder: '#9FD0AC',
          purpleBg: '#F1EDFF',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      maxWidth: {
        container: '1230px',
      },
      borderRadius: {
        card: '16px',
        banner: '20px',
        input: '8px',
        btn: '8px',
        badge: '6px',
      }
    },
  },
  plugins: [],
}
