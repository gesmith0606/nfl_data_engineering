import type { Metadata } from "next";
import LineupView from "@/components/LineupView";

const DEFAULT_SEASON = 2026;
const DEFAULT_WEEK = 1;
const DEFAULT_SCORING = "half_ppr" as const;

export const metadata: Metadata = {
  title: "Team Lineups - Field View",
  description:
    "Visual field-style lineup view showing each team's starting offense with projected fantasy points. Select a team to see player positions on the field.",
  openGraph: {
    title: "NFL Team Lineups - Field View",
    description:
      "Visual lineup view with fantasy projections positioned on a football field.",
  },
};

export default function LineupsPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white sm:text-3xl">
          Team Lineups
        </h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          Select a team to see their starting lineup on the field with projected
          fantasy points. Click any player for details.
        </p>
      </div>
      <LineupView
        initialSeason={DEFAULT_SEASON}
        initialWeek={DEFAULT_WEEK}
        initialScoring={DEFAULT_SCORING}
      />
    </div>
  );
}
