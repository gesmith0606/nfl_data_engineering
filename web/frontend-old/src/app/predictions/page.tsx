import type { Metadata } from "next";
import { fetchPredictions } from "@/lib/api";
import PredictionsView from "@/components/PredictionsView";
import type { GamePrediction } from "@/lib/types";

const DEFAULT_SEASON = 2026;
const DEFAULT_WEEK = 1;

export const metadata: Metadata = {
  title: "Game Predictions",
  description:
    "NFL game predictions with spread and total edges vs Vegas lines. Model-generated picks with confidence tiers.",
  openGraph: {
    title: "NFL Game Predictions - Week 1 2026",
    description:
      "Model-generated spread and total predictions with edge detection vs Vegas lines.",
  },
};

export default async function PredictionsPage() {
  let predictions: GamePrediction[] = [];

  try {
    const data = await fetchPredictions(DEFAULT_SEASON, DEFAULT_WEEK);
    predictions = data.predictions;
  } catch {
    // Backend not running -- render with empty data.
    // The client component will show a graceful error state.
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white sm:text-3xl">
          Game Predictions
        </h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          Model-generated spread and total predictions with edge detection vs
          Vegas lines.
        </p>
      </div>
      <PredictionsView
        initialPredictions={predictions}
        initialSeason={DEFAULT_SEASON}
        initialWeek={DEFAULT_WEEK}
      />
    </div>
  );
}
