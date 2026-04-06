"use client";

import { useRouter } from "next/navigation";
import type { TeamLineup, LineupPlayer } from "@/lib/types";
import { getTeamColor } from "@/lib/teamColors";

/** Position badge colors matching existing design language. */
const POSITION_COLORS: Record<string, string> = {
  QB: "#E31837",
  RB: "#00A6A0",
  WR: "#4F46E5",
  TE: "#D97706",
  K: "#6B7280",
};

function getPositionColor(position: string): string {
  return POSITION_COLORS[position] ?? "#6B7280";
}

interface PlayerCardProps {
  player: LineupPlayer;
  compact?: boolean;
}

function PlayerCard({ player, compact }: PlayerCardProps) {
  const router = useRouter();
  const posColor = getPositionColor(player.position);

  const truncatedName =
    player.player_name.length > 14
      ? player.player_name.slice(0, 13) + "\u2026"
      : player.player_name;

  return (
    <button
      onClick={() => router.push(`/players/${player.player_id}`)}
      className={`group cursor-pointer rounded-lg bg-black/60 backdrop-blur-sm text-white text-center transition-all hover:bg-black/80 hover:scale-105 focus:outline-none focus:ring-2 focus:ring-white/50 ${
        compact ? "px-2 py-1.5" : "px-3 py-2"
      }`}
      style={{ borderTop: `3px solid ${posColor}` }}
      title={`${player.player_name} (${player.position}) - Click for details`}
    >
      <div className="flex items-center justify-center gap-1.5 mb-0.5">
        <span
          className="inline-flex items-center rounded px-1 py-0.5 text-[10px] font-bold uppercase leading-none"
          style={{ backgroundColor: posColor }}
        >
          {player.position}
        </span>
        <span className={`font-medium leading-tight ${compact ? "text-xs" : "text-sm"}`}>
          {truncatedName}
        </span>
      </div>

      {player.projected_points !== null ? (
        <>
          <div className={`font-bold tabular-nums ${compact ? "text-lg" : "text-xl"}`}>
            {player.projected_points.toFixed(1)}
          </div>
          {player.projected_floor !== null && player.projected_ceiling !== null && (
            <div className="text-[10px] text-white/60 tabular-nums">
              {player.projected_floor.toFixed(1)} - {player.projected_ceiling.toFixed(1)}
            </div>
          )}
        </>
      ) : (
        <div className={`font-bold text-white/40 ${compact ? "text-lg" : "text-xl"}`}>
          --
        </div>
      )}

      {player.snap_pct !== null && (
        <div className="text-[10px] text-white/50 mt-0.5">
          {Math.round(player.snap_pct * 100)}% snaps
        </div>
      )}
    </button>
  );
}

/** Horizontal yard line stripe. */
function YardLine({ top }: { top: string }) {
  return (
    <div
      className="absolute left-4 right-4 h-px bg-white/15"
      style={{ top }}
    />
  );
}

interface FieldViewProps {
  lineup: TeamLineup;
}

export default function FieldView({ lineup }: FieldViewProps) {
  const teamColor = getTeamColor(lineup.team);

  // Sort players by field position for consistent layout
  const positionOrder = ["wr_left", "wr_slot", "te", "wr_right", "rb", "qb", "k"];
  const sortedPlayers = [...lineup.offense]
    .filter((p) => p.is_starter)
    .sort((a, b) => positionOrder.indexOf(a.field_position) - positionOrder.indexOf(b.field_position));

  // Group by field position for the grid layout
  const playersByPos = new Map<string, LineupPlayer>();
  for (const p of sortedPlayers) {
    playersByPos.set(p.field_position, p);
  }

  return (
    <div className="w-full">
      {/* Desktop field view */}
      <div className="hidden md:block">
        <div
          className="relative rounded-xl overflow-hidden"
          style={{
            background: "linear-gradient(to bottom, #2d5a27, #1a3a17)",
          }}
        >
          {/* Yard lines */}
          <YardLine top="15%" />
          <YardLine top="30%" />
          <YardLine top="45%" />
          <YardLine top="60%" />
          <YardLine top="75%" />
          <YardLine top="90%" />

          {/* Team header */}
          <div className="relative z-10 flex items-center justify-between px-6 py-3">
            <div
              className="flex items-center gap-3 rounded-lg px-4 py-2"
              style={{ backgroundColor: `${teamColor}cc` }}
            >
              <span className="text-xl font-bold text-white">{lineup.team}</span>
              {lineup.implied_total !== null && (
                <span className="text-sm text-white/80">
                  Implied: {lineup.implied_total.toFixed(1)}
                </span>
              )}
            </div>
            {lineup.team_projected_total !== null && (
              <div className="rounded-lg bg-black/40 px-3 py-1.5 text-sm text-white/80">
                Projected Total:{" "}
                <span className="font-bold text-white">
                  {lineup.team_projected_total.toFixed(1)}
                </span>
              </div>
            )}
          </div>

          {/* Field grid */}
          <div className="relative z-10 px-6 pb-6">
            {/* Line of scrimmage label */}
            <div className="mb-2 text-center text-[10px] font-medium uppercase tracking-widest text-white/30">
              Line of Scrimmage
            </div>

            {/* Row 1: WR1, WR3/Slot, TE */}
            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="flex justify-center">
                {playersByPos.get("wr_left") && (
                  <PlayerCard player={playersByPos.get("wr_left")!} />
                )}
              </div>
              <div className="flex justify-center">
                {playersByPos.get("wr_slot") && (
                  <PlayerCard player={playersByPos.get("wr_slot")!} />
                )}
              </div>
              <div className="flex justify-center">
                {playersByPos.get("te") && (
                  <PlayerCard player={playersByPos.get("te")!} />
                )}
              </div>
            </div>

            {/* Row 2: WR2 (offset) */}
            <div className="grid grid-cols-3 gap-4 mb-6">
              <div />
              <div className="flex justify-center">
                {playersByPos.get("wr_right") && (
                  <PlayerCard player={playersByPos.get("wr_right")!} />
                )}
              </div>
              <div />
            </div>

            {/* Row 3: RB */}
            <div className="flex justify-center mb-6">
              {playersByPos.get("rb") && (
                <PlayerCard player={playersByPos.get("rb")!} />
              )}
            </div>

            {/* Row 4: QB */}
            <div className="flex justify-center mb-6">
              {playersByPos.get("qb") && (
                <PlayerCard player={playersByPos.get("qb")!} />
              )}
            </div>

            {/* Row 5: K (smaller) */}
            <div className="flex justify-center">
              {playersByPos.get("k") && (
                <PlayerCard player={playersByPos.get("k")!} compact />
              )}
            </div>
          </div>

          {/* End zone accent */}
          <div
            className="h-2 w-full"
            style={{ backgroundColor: teamColor }}
          />
        </div>
      </div>

      {/* Mobile list view */}
      <div className="block md:hidden">
        <div
          className="rounded-xl overflow-hidden"
          style={{ borderTop: `4px solid ${teamColor}` }}
        >
          {/* Team header */}
          <div
            className="flex items-center justify-between px-4 py-3"
            style={{ backgroundColor: `${teamColor}22` }}
          >
            <span className="text-lg font-bold text-gray-900 dark:text-white">
              {lineup.team}
            </span>
            <div className="flex gap-3 text-xs text-gray-600 dark:text-gray-400">
              {lineup.implied_total !== null && (
                <span>Implied: {lineup.implied_total.toFixed(1)}</span>
              )}
              {lineup.team_projected_total !== null && (
                <span>
                  Proj: <strong>{lineup.team_projected_total.toFixed(1)}</strong>
                </span>
              )}
            </div>
          </div>

          {/* Player list */}
          <div className="divide-y divide-gray-200 dark:divide-gray-700 bg-white dark:bg-gray-900">
            {sortedPlayers.map((player) => (
              <MobilePlayerRow key={player.player_id} player={player} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function MobilePlayerRow({ player }: { player: LineupPlayer }) {
  const router = useRouter();
  const posColor = getPositionColor(player.position);

  return (
    <button
      onClick={() => router.push(`/players/${player.player_id}`)}
      className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/50"
    >
      <div className="flex items-center gap-3">
        <span
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-xs font-bold text-white"
          style={{ backgroundColor: posColor }}
        >
          {player.position}
        </span>
        <div>
          <div className="text-sm font-medium text-gray-900 dark:text-white">
            {player.player_name}
          </div>
          {player.snap_pct !== null && (
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {Math.round(player.snap_pct * 100)}% snaps
            </div>
          )}
        </div>
      </div>

      <div className="text-right">
        {player.projected_points !== null ? (
          <>
            <div className="text-lg font-bold tabular-nums text-gray-900 dark:text-white">
              {player.projected_points.toFixed(1)}
            </div>
            {player.projected_floor !== null && player.projected_ceiling !== null && (
              <div className="text-[10px] tabular-nums text-gray-500 dark:text-gray-400">
                {player.projected_floor.toFixed(1)} - {player.projected_ceiling.toFixed(1)}
              </div>
            )}
          </>
        ) : (
          <div className="text-lg font-bold text-gray-400">--</div>
        )}
      </div>
    </button>
  );
}
