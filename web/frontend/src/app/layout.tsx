import Providers from '@/components/layout/providers';
import { ClerkProvider } from '@clerk/nextjs';
import { dark } from '@clerk/themes';
import { isClerkEnabled } from '@/lib/billing/flags';
import { Toaster } from '@/components/ui/sonner';
import { fontVariables } from '@/components/themes/font.config';
import { DEFAULT_THEME } from '@/components/themes/theme.config';
import ThemeProvider from '@/components/themes/theme-provider';
import { ServiceWorkerRegister } from '@/components/pwa/sw-register';
import { cn } from '@/lib/utils';
import type { Metadata, Viewport } from 'next';
import NextTopLoader from 'nextjs-toploader';
import { NuqsAdapter } from 'nuqs/adapters/next/app';
import '../styles/globals.css';

const META_THEME_COLORS = {
  light: '#ffffff',
  dark: '#0e0f16' // worldcup26 deep-ink background
};

export const metadata: Metadata = {
  title: {
    default: 'GIQ — NFL Analytics',
    template: '%s | GIQ'
  },
  description:
    'NFL fantasy football projections, game predictions, and player analytics powered by machine learning.',
  keywords: ['NFL', 'fantasy football', 'projections', 'game predictions', 'player analytics'],
  manifest: '/manifest.webmanifest',
  icons: {
    icon: [
      { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
      { url: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' }
    ],
    apple: '/icons/icon-192.png'
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'GIQ'
  },
  openGraph: {
    type: 'website',
    siteName: 'NFL Analytics',
    title: 'NFL Analytics — Fantasy Projections & AI Advisor',
    description:
      'Data-driven fantasy football projections with PPR, Half-PPR, and Standard scoring. AI-powered start/sit advice and game predictions.',
    url: 'https://frontend-jet-seven-33.vercel.app'
  },
  twitter: {
    card: 'summary_large_image',
    title: 'NFL Analytics',
    description:
      'Fantasy football projections and AI-powered start/sit advice. Game predictions vs. Vegas lines.'
  }
};

export const viewport: Viewport = {
  themeColor: META_THEME_COLORS.dark
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // GIQ is one design: the worldcup26 broadcast theme, dark, for every
  // visitor. The previous per-browser theme cookie and light/system modes
  // are ignored — they exposed un-designed surfaces (old template themes,
  // white light mode) to anyone with stale preferences.
  const themeToApply = DEFAULT_THEME;

  const app = (
    <html lang='en' suppressHydrationWarning data-theme={themeToApply}>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                // Set meta theme color
                if (localStorage.theme === 'dark' || !('theme' in localStorage) || (localStorage.theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', '${META_THEME_COLORS.dark}')
                }
              } catch (_) {}
            `
          }}
        />
      </head>
      <body
        className={cn(
          'bg-background overflow-x-hidden overscroll-none font-sans antialiased',
          fontVariables
        )}
      >
        <ServiceWorkerRegister />
        <NextTopLoader color='var(--primary)' showSpinner={false} />
        <NuqsAdapter>
          <ThemeProvider
            attribute='class'
            defaultTheme='dark'
            forcedTheme='dark'
            disableTransitionOnChange
            enableColorScheme
          >
            <Providers activeThemeValue={themeToApply}>
              <Toaster />
              {children}
            </Providers>
          </ThemeProvider>
        </NuqsAdapter>
      </body>
    </html>
  );

  // PLAN 2 feature flag: Clerk only mounts when the publishable key exists.
  // Without keys the tree is byte-identical to the pre-auth site.
  if (!isClerkEnabled()) return app;

  return <ClerkProvider appearance={{ baseTheme: dark }}>{app}</ClerkProvider>;
}
