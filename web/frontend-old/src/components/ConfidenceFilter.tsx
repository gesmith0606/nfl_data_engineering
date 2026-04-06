"use client";

export type ConfidenceTier = "ALL" | "HIGH" | "MEDIUM" | "LOW";

const TIERS: { value: ConfidenceTier; label: string; activeClass: string }[] = [
  { value: "ALL", label: "All", activeClass: "bg-gray-600 text-white" },
  {
    value: "HIGH",
    label: "High Edge",
    activeClass: "bg-green-600 text-white",
  },
  {
    value: "MEDIUM",
    label: "Medium Edge",
    activeClass: "bg-yellow-500 text-white",
  },
  { value: "LOW", label: "Low Edge", activeClass: "bg-gray-500 text-white" },
];

interface ConfidenceFilterProps {
  value: ConfidenceTier;
  onChange: (tier: ConfidenceTier) => void;
}

export default function ConfidenceFilter({
  value,
  onChange,
}: ConfidenceFilterProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {TIERS.map(({ value: tierValue, label, activeClass }) => {
        const isActive = value === tierValue;
        return (
          <button
            key={tierValue}
            onClick={() => onChange(tierValue)}
            className={`rounded-full px-3 py-1 text-sm font-medium transition-all ${
              isActive
                ? `${activeClass} shadow-sm`
                : "bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
