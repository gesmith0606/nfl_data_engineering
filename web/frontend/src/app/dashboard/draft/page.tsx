import PageContainer from '@/components/layout/page-container'
import { Suspense } from 'react'
import { DraftToolView } from '@/features/draft/components/draft-tool-view'

export const metadata = {
  title: 'NFL Draft Tool',
  description:
    'Interactive snake draft board with ADP, VORP rankings, AI recommendations, and mock draft simulation.'
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
