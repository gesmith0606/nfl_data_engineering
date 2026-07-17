/**
 * League context for the AI advisor.
 *
 * The chat client (use-persistent-chat) sends the user's connected Sleeper
 * leagues with every request. This module sanitizes that untrusted payload
 * and renders the system-prompt block that makes the advisor league-aware.
 */

export interface AdvisorLeague {
  league_id: string;
  league_name: string;
  season: string;
  user_id: string;
  username: string;
  roster_positions: string[];
  scoring_format_label: string;
}

const MAX_LEAGUES = 3;

// Sleeper IDs are numeric snowflakes (18-19 digits); allow word chars only,
// length-capped, so untrusted client payloads can never smuggle path segments
// into backend URLs.
const SAFE_ID = /^\w{1,30}$/;

// Free-text fields flow into the system prompt: strip newlines and cap length
// so a crafted value can't open a fake system-prompt block.
function asLabel(value: unknown, fallback: string, maxLen: number): string {
  const s = typeof value === 'string' && value.length > 0 ? value : fallback;
  return s.replace(/\s+/g, ' ').trim().slice(0, maxLen);
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

/**
 * Sanitize the `leagues` field of the chat request body. Drops entries
 * without the identifiers required to call league endpoints; never throws.
 */
export function parseAdvisorLeagues(raw: unknown): AdvisorLeague[] {
  if (!Array.isArray(raw)) return [];
  const leagues: AdvisorLeague[] = [];
  for (const entry of raw) {
    if (leagues.length >= MAX_LEAGUES) break;
    if (typeof entry !== 'object' || entry === null) continue;
    const e = entry as Record<string, unknown>;
    const leagueId = asString(e.league_id);
    const userId = asString(e.user_id);
    if (!SAFE_ID.test(leagueId) || !SAFE_ID.test(userId)) continue;
    leagues.push({
      league_id: leagueId,
      user_id: userId,
      league_name: asLabel(e.league_name, 'Unnamed league', 100),
      season: asLabel(e.season, '', 10),
      username: asLabel(e.username, '', 40),
      roster_positions: Array.isArray(e.roster_positions)
        ? e.roster_positions
            .filter((p): p is string => typeof p === 'string')
            .slice(0, 25)
            .map((p) => asLabel(p, '', 12))
        : [],
      scoring_format_label: asLabel(e.scoring_format_label, 'Half PPR', 60)
    });
  }
  return leagues;
}

/**
 * Render the system-prompt block describing the user's connected leagues.
 * Returns '' when no leagues are connected so the base prompt is unchanged.
 */
export function buildLeagueContextPrompt(leagues: AdvisorLeague[]): string {
  if (leagues.length === 0) return '';

  const lines = leagues.map((l, i) => {
    const starters = l.roster_positions.filter((p) => p !== 'BN');
    const roster =
      starters.length > 0 ? ` | Starting slots: ${starters.join(', ')}` : '';
    const primary = i === 0 && leagues.length > 1 ? ' (PRIMARY)' : '';
    return `- "${l.league_name}"${primary} — league_id: ${l.league_id}, season: ${l.season}, Sleeper user: ${l.username} (user_id: ${l.user_id}), scoring: ${l.scoring_format_label}${roster}`;
  });

  return `

CONNECTED LEAGUE CONTEXT:
The user has connected the following Sleeper league(s) on this site:
${lines.join('\n')}

Because of this you KNOW who the user is — never ask them for a league ID or user ID.
- When they ask about "my team", "my lineup", "my roster", "who should I start",
  or "who should I drop": call getMyRoster or getMyLineup first (they default to
  the primary league) so advice is grounded in their actual players.
- When they ask about waivers or free agents: call getMyWaiverTargets — it only
  returns players actually unrostered in their league, ranked under league scoring.
- Use the league's scoring format shown above (not generic Half-PPR) when framing advice.
- If they name a different connected league, pass that league's leagueId to the tools.`;
}
