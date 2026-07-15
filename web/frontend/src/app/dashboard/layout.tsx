import KBar from '@/components/kbar';
import { ChatWidget } from '@/components/chat-widget';
import { BroadcastNav } from '@/components/layout/broadcast-nav';
import { MobileTabbar } from '@/components/layout/mobile-tabbar';
import { InfoSidebar } from '@/components/layout/info-sidebar';
import { InfobarProvider } from '@/components/ui/infobar';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'GIQ — NFL Analytics',
  description: 'Fantasy projections, game predictions, and player analytics',
  robots: {
    index: false,
    follow: false
  }
};

/**
 * App shell = the broadcast site shell (sketches 001-B/003/005): the same
 * near-black top nav with the mint rule as the marketing home, dark stadium
 * canvas, GX-01 launcher, and the mobile tab bar. The previous sidebar-admin
 * chrome is gone — GIQ is one design end to end.
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <KBar>
      <InfobarProvider defaultOpen={false}>
        <div className='flex min-h-svh w-full flex-col'>
          <BroadcastNav />
          {/* page main content — bottom padding clears the mobile tab bar */}
          <main className='flex-1 pb-16 md:pb-0'>{children}</main>
        </div>
        <InfoSidebar side='right' />
        <ChatWidget />
        <MobileTabbar />
      </InfobarProvider>
    </KBar>
  );
}
