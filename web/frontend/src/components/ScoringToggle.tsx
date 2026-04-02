"use client";

import type { ScoringFormat } from "@/lib/types";

const OPTIONS: { value: ScoringFormat; label: string }[] = [
  { value: "ppr", label: "PPR" },
  { value: "half_ppr", label: "Half PPR" },
  { value: "standard", label: "Standard" },
];

interface ScoringToggleProps {
  value: ScoringFormat;
  onChange: (format: ScoringFormat) => void;
}

export default function ScoringToggle({ value, onChange }: ScoringToggleProps) {
  return (
    <div className="inline-flex rounded-lg bg-gray-100 p-1 dark:bg-gray-800">
      {OPTIONS.map(({ value: optValue, label }) => (
        <button
          key={optValue}
          onClick={() => onChange(optValue)}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
            value === optValue
              ? "bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-white"
              : "text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
