import type { Metadata } from "next";
import { fetchProjections } from "@/lib/api";
import ProjectionsView from "@/components/ProjectionsView";
import type { PlayerProjection } from "@/lib/types";

const DEFAULT_SEASON = 2026;
const DEFAULT_WEEK = 1;
const DEFAULT_SCORING = "half_ppr" as const;

export const metadata: Metadata = {
  title: "Fantasy Projections - Week 1 2026",
  description:
    "Weekly fantasy football projections for QB, RB, WR, TE with floor/ceiling ranges. PPR, Half-PPR, and Standard scoring.",
  openGraph: {
    title: "NFL Fantasy Projections - Week 1 2026",
    description:
      "Weekly fantasy football projections with floor/ceiling ranges powered by historical analytics.",
  },
};

export default async function ProjectionsPage() {
  let projections: PlayerProjection[] = [];

  try {
    const data = await fetchProjections(
      DEFAULT_SEASON,
      DEFAULT_WEEK,
      DEFAULT_SCORING,
    );
    projections = data.projections;
  } catch {
    // Backend not running -- render with empty data.
    // The client component will show a graceful error state.
  }

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Dataset",
    name: "NFL Fantasy Football Projections",
    description:
      "Weekly fantasy football projections for QB, RB, WR, TE with floor/ceiling ranges.",
    url: "https://nfl-projections.vercel.app/projections",
    creator: {
      "@type": "Organization",
      name: "NFL Data Engineering",
    },
    temporalCoverage: "2020/2026",
    keywords: [
      "fantasy football",
      "NFL projections",
      "PPR",
      "Half PPR",
      "player rankings",
    ],
  };

  return (
    <div>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white sm:text-3xl">
          Fantasy Projections
        </h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          Player projections with floor/ceiling ranges. Click any column to sort,
          or click a player for details.
        </p>
      </div>
      <ProjectionsView
        initialProjections={projections}
        initialSeason={DEFAULT_SEASON}
        initialWeek={DEFAULT_WEEK}
        initialScoring={DEFAULT_SCORING}
      />
    </div>
  );
}
