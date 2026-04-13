import PageContainer from '@/components/layout/page-container'
import { Suspense } from 'react'
import { DraftToolView } from '@/features/draft/components/draft-tool-view'

export const metadata = {
  title: 'NFL Draft Tool',
  description:
    'Interactive snake draft board with ADP, VORP rankings, AI recommendations, and mock draft simulation.',
  openGraph: {
    title: 'NFL Draft Tool | NFL Analytics',
    description:
      'Interactive snake draft board with ADP, VORP rankings, AI recommendations, and mock draft simulation.',
    url: 'https://frontend-jet-seven-33.vercel.app/dashboard/draft'
  },
  twitter: {
    card: 'summary_large_image' as const,
    title: 'NFL Draft Tool',
    description: 'Interactive fantasy draft board with ADP, VORP, and AI recommendations.'
  }
}

export default function DraftPage() {
  return (
    <PageContainer
      scrollable={true}
      pageTitle='Draft Tool'
      pageDescription='Interactive draft board with ADP, VORP, and AI recommendations'
    >
      <Suspense>
        <DraftToolView />
      </Suspense>
    </PageContainer>
  )
}
