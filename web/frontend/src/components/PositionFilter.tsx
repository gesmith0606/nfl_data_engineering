"use client";

import type { Position } from "@/lib/types";

const POSITIONS: { value: Position; label: string; color: string }[] = [
  { value: "ALL", label: "All", color: "bg-gray-600" },
  { value: "QB", label: "QB", color: "bg-red-600" },
  { value: "RB", label: "RB", color: "bg-blue-600" },
  { value: "WR", label: "WR", color: "bg-green-600" },
  { value: "TE", label: "TE", color: "bg-orange-500" },
  { value: "K", label: "K", color: "bg-purple-600" },
];

interface PositionFilterProps {
  value: Position;
  onChange: (position: Position) => void;
}

export default function PositionFilter({
  value,
  onChange,
}: PositionFilterProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {POSITIONS.map(({ value: posValue, label, color }) => {
        const isActive = value === posValue;
        return (
          <button
            key={posValue}
            onClick={() => onChange(posValue)}
            className={`rounded-full px-3 py-1 text-sm font-medium transition-all ${
              isActive
                ? `${color} text-white shadow-sm`
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
