"use client";

const NFL_TEAMS = [
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
  "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG",
  "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
];

interface TeamFilterProps {
  value: string;
  onChange: (team: string) => void;
}

export default function TeamFilter({ value, onChange }: TeamFilterProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
    >
      <option value="">All Teams</option>
      {NFL_TEAMS.map((team) => (
        <option key={team} value={team}>
          {team}
        </option>
      ))}
    </select>
  );
}
