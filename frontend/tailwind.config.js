/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  safelist: [
    'bg-primary', 'text-primary-foreground', 'hover:bg-primary/90',
    'bg-secondary', 'text-secondary-foreground', 'hover:bg-secondary/80',
    'bg-accent', 'text-accent-foreground', 'hover:bg-accent',
    'bg-muted', 'text-muted-foreground',
    'bg-success', 'text-success-foreground',
    'bg-warning', 'text-warning-foreground',
    'bg-destructive', 'text-destructive-foreground',
    'border-primary', 'border-input', 'border-destructive', 'border-transparent',
    'rounded-md', 'rounded-lg', 'rounded-full',
    'btn', 'btn-primary', 'btn-secondary', 'btn-outline', 'btn-ghost',
    'input', 'textarea', 'card',
    'fixed', 'inset-0', 'z-50', 'bg-black/50',
    'flex', 'flex-col', 'h-screen', 'w-80', 'w-0', 'flex-1',
    'border-r', 'border-b', 'overflow-hidden', 'overflow-y-auto',
    'p-4', 'p-3', 'p-6', 'px-4', 'py-2', 'py-3', 'py-8',
    'mb-1', 'mb-2', 'mb-3', 'mb-4', 'mt-1', 'mt-2', 'ml-2',
    'text-sm', 'text-xs', 'text-lg', 'text-xl', 'text-2xl',
    'font-medium', 'font-semibold',
    'truncate', 'whitespace-pre-wrap',
    'animate-pulse', 'transition-all', 'transition-colors',
    'hover:bg-accent', 'hover:text-accent-foreground',
  ],
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        success: {
          DEFAULT: 'hsl(var(--success))',
          foreground: 'hsl(var(--success-foreground))',
        },
        warning: {
          DEFAULT: 'hsl(var(--warning))',
          foreground: 'hsl(var(--warning-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
    },
  },
  plugins: [],
}
