import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "2rem", screens: { "2xl": "1400px" } },
    extend: {
      colors: {
        // CSS-variable-backed palette so themes can swap at runtime.
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: "hsl(var(--card))",
        "card-foreground": "hsl(var(--card-foreground))",
        muted: "hsl(var(--muted))",
        "muted-foreground": "hsl(var(--muted-foreground))",
        border: "hsl(var(--border))",
        accent: "hsl(var(--accent))",
        "accent-foreground": "hsl(var(--accent-foreground))",
        primary: "hsl(var(--primary))",
        "primary-foreground": "hsl(var(--primary-foreground))",
        destructive: "hsl(var(--destructive))",
        warning: "hsl(var(--warning))",
        success: "hsl(var(--success))",
        "agent-meetings": "hsl(280 70% 65%)",
        "agent-markets":  "hsl(160 70% 55%)",
        "agent-security": "hsl(0   80% 65%)",
        "agent-research": "hsl(210 80% 65%)",
        "agent-content":  "hsl(35  90% 60%)",
        "agent-operations": "hsl(50 90% 60%)",
      },
      borderRadius: { lg: "1rem", md: "0.75rem", sm: "0.5rem" },
      backgroundImage: {
        "grid-glow":
          "radial-gradient(circle at 20% 0%, hsl(var(--primary)/0.18), transparent 50%), radial-gradient(circle at 80% 100%, hsl(var(--accent)/0.18), transparent 50%)",
      },
      boxShadow: {
        glow: "0 0 0 1px hsl(var(--border)), 0 8px 40px -8px hsl(var(--primary)/0.35)",
      },
      animation: {
        shimmer: "shimmer 2.4s linear infinite",
        "pulse-slow": "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "200% 0" },
          "100%": { backgroundPosition: "-200% 0" },
        },
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
