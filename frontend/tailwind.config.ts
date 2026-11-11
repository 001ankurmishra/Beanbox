import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}'
  ],
  theme: {
    extend: {
      colors: {
        espresso: {
          50: '#FBF7F2',
          100: '#F4EAE0',
          200: '#E6D3C0',
          300: '#D2B397',
          400: '#B88964',
          500: '#9B6540',
          600: '#7C4B2C',
          700: '#5C341E',
          800: '#3D2317',
          900: '#26150E',
          950: '#160B07'
        },
        caramel: {
          DEFAULT: '#C27035',
          light: '#DDA15E',
          dark: '#9C5220'
        },
        sage: {
          DEFAULT: '#3A6B4C',
          light: '#EBF3EE'
        }
      },
      fontFamily: {
        serif: ['var(--font-fraunces)', 'Georgia', 'serif'],
        sans: ['var(--font-jakarta)', 'system-ui', 'sans-serif']
      },
      boxShadow: {
        warm: '0 10px 30px -10px rgba(38, 21, 14, 0.12)'
      }
    }
  },
  plugins: []
};

export default config;
