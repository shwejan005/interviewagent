/** @type {import('tailwindcss').Config} */
module.exports = {
    darkMode: ["class"],
    content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./component/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
  	extend: {
  		fontFamily: {
  			sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
  			mono: ['var(--font-jetbrains-mono)', 'monospace'],
  		},
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		},
  		// Design-system tokens, namespaced so they never collide with the
  		// shadcn HSL scale below.
  		backgroundColor: {
  			'glass-low': 'var(--glass-bg-low)',
  			'glass-mid': 'var(--glass-bg-mid)',
  			'glass-high': 'var(--glass-bg-high)',
  		},
  		textColor: {
  			ink: 'var(--color-text)',
  			'ink-muted': 'var(--color-text-muted)',
  			'ink-subtle': 'var(--color-text-subtle)',
  			'ink-heading': 'var(--color-text-heading)',
  			brand: 'var(--color-primary)',
  		},
  		borderColor: {
  			subtle: 'var(--color-border)',
  			strong: 'var(--color-border-hover)',
  			brand: 'var(--color-primary)',
  		},
  		boxShadow: {
  			glass: 'var(--glass-highlight), var(--glass-shadow)',
  			'glass-lg': 'var(--glass-highlight), var(--glass-shadow-lg)',
  			'glow-primary': 'var(--glow-primary)',
  			'glow-success': 'var(--glow-success)',
  		},
  		backdropBlur: {
  			glass: 'var(--glass-blur-md)',
  		},
  		transitionTimingFunction: {
  			'out-expo': 'var(--ease-out)',
  			spring: 'var(--ease-spring)',
  		},
  		transitionDuration: {
  			fast: '150ms',
  			base: '250ms',
  			slow: '400ms',
  		},
  		colors: {
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			accent: {
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			chart: {
  				'1': 'hsl(var(--chart-1))',
  				'2': 'hsl(var(--chart-2))',
  				'3': 'hsl(var(--chart-3))',
  				'4': 'hsl(var(--chart-4))',
  				'5': 'hsl(var(--chart-5))'
  			}
  		}
  	}
  },
  plugins: [require("tailwindcss-animate")],
};
