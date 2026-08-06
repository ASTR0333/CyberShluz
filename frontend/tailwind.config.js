
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
            DEFAULT: '#3164c9',
            light: '#5382e6',
            dark: '#141f36',
            accent: '#2b61c4',
          },
          gray: {
            dark: '#0f1729',
            DEFAULT: '#374151',
            light: '#6b7280',
            surface: '#f4f6fa',
            border: '#e5e8ef',
          }
        },
        sidebar: {
          dark: '#141f36',
          icon: '#214389'
        }
      },
      borderRadius: {
        'brand': '6px',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Helvetica Neue', 'Arial', 'sans-serif'],
        display: ['Inter', 'system-ui', 'sans-serif'],
      },
      letterSpacing: {
        'brand': '-0.02em',
      }
    },
  },
  plugins: [],
}
