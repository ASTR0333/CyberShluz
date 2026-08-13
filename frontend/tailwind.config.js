
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        cyber: {
          blue: {
            DEFAULT: '#173E7E',
            light: '#83D0F5',
            dark: '#00204D',
            accent: '#003FFF',
          },
          gray: {
            dark: '#282828',
            DEFAULT: '#737373',
            light: '#737373',
            surface: '#F4F8FC',
            border: '#D4E5F7',
          }
        },
        sidebar: {
          dark: '#00204D',
          icon: '#173E7E'
        }
      },
      borderRadius: {
        'brand': '10px',
      },
      fontFamily: {
        sans: ['Arial', 'Helvetica Neue', 'system-ui', 'sans-serif'],
        display: ['Arial', 'Helvetica Neue', 'system-ui', 'sans-serif'],
      },
      letterSpacing: {
        'brand': '-0.02em',
      }
    },
  },
  plugins: [],
}
