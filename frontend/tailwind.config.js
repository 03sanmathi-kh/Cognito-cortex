import tailwindcssAnimate from "tailwindcss-animate"

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
      },
      colors: {
        page: "var(--color-page)",
        sidebar: {
          DEFAULT: "var(--color-sidebar)",
          border: "var(--sidebar-border)",
        },
        card: {
          DEFAULT: "var(--color-card)",
          raised: "var(--color-card-raised)",
          foreground: "var(--card-foreground)",
        },
        border: "var(--color-border)",
        input: "var(--input)",
        ring: "var(--ring)",
        background: "var(--background)",
        foreground: "var(--foreground)",
        
        // Brand palette
        lumen: {
          page: "#07070C",
          sidebar: "#0B0B12",
          card: "#10101A",
          raised: "#161622",
          border: "rgba(255, 255, 255, 0.07)",
          text: "#F1F1F7",
          secondary: "#9A9AB0",
          muted: "#6B6B80",
          magenta: "#D946EF",
          purple: "#8B5CF6",
          green: "#22C55E",
          warning: "#F59E0B",
          danger: "#F43F5E",
        },

        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
        destructive: {
          DEFAULT: "var(--destructive)",
          foreground: "var(--destructive-foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-foreground)",
        },
        popover: {
          DEFAULT: "var(--popover)",
          foreground: "var(--popover-foreground)",
        },
      },
      borderRadius: {
        '2xl': '1rem',      // cards
        'xl': '0.75rem',    // buttons and inputs
        'lg': '0.5rem',
        'md': '0.375rem',
        'sm': '0.25rem',
      },
      boxShadow: {
        'glow-sm': '0 0 15px -3px rgba(217, 70, 239, 0.25)',
        'glow-md': '0 0 25px -4px rgba(217, 70, 239, 0.35)',
        'glow-lg': '0 0 40px -6px rgba(217, 70, 239, 0.45)',
        'card-dark': '0 0 0 1px rgba(255, 255, 255, 0.07), 0 12px 32px -8px rgba(0, 0, 0, 0.6)',
      },
      backgroundImage: {
        'accent-gradient': 'linear-gradient(135deg, #D946EF 0%, #8B5CF6 100%)',
        'accent-gradient-hover': 'linear-gradient(135deg, #E879F9 0%, #A78BFA 100%)',
        'active-nav-glow': 'linear-gradient(90deg, rgba(217, 70, 239, 0.12) 0%, rgba(139, 92, 246, 0.03) 100%)',
        'radial-glow': 'radial-gradient(ellipse at top, rgba(217, 70, 239, 0.15), transparent 60%)',
      },
    },
  },
  plugins: [tailwindcssAnimate],
}
