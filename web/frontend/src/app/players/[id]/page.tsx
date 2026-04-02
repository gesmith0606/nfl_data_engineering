import { notFound } from "next/navigation";
import PlayerDetailView from "@/components/PlayerDetailView";
import type { PlayerProjection, ScoringFormat } from "@/lib/types";

export const metadata = {
  title: "Player Detail | NFL Projections",
  description: "Detailed player projections and stat breakdowns.",
};

const DEFAULT_SEASON = 2026;
const DEFAULT_WEEK = 1;
const DEFAULT_SCORING: ScoringFormat = "half_ppr";

async function getPlayer(
  playerId: string,
  season: number,
  week: number,
  scoring: ScoringFormat,
): Promise<PlayerProjection | null> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    scoring,
  });

  try {
    const res = await fetch(`${baseUrl}/api/players/${playerId}?${params}`, {
      cache: "no-store",
    });

    if (res.status === 404) {
      return null;
    }

    if (!res.ok) {
      return null;
    }

    return (await res.json()) as PlayerProjection;
  } catch {
    // Backend unreachable — render the page with null so client can retry
    return null;
  }
}

export default async function PlayerDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const player = await getPlayer(
    id,
    DEFAULT_SEASON,
    DEFAULT_WEEK,
    DEFAULT_SCORING,
  );

  return (
    <PlayerDetailView
      playerId={id}
      initialPlayer={player}
      initialSeason={DEFAULT_SEASON}
      initialWeek={DEFAULT_WEEK}
      initialScoring={DEFAULT_SCORING}
    />
  );
}
