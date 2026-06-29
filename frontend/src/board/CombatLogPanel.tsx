// Shared combat-log overlay (Phase 5): renders the attack lines the server has
// broadcast so EVERYONE in the room sees the same log. Names are resolved from the
// current tokens at render time, so the log stays correct regardless of when an
// entry was recorded.

import { type CombatLogEntry, formatAttackEntry } from './combatLog';
import type { PlacedToken } from './tokens';

export interface CombatLogPanelProps {
  /** Log entries, oldest first. */
  entries: CombatLogEntry[];
  /** Current placed tokens, used to resolve a token id to its character's name. */
  tokens: PlacedToken[];
}

const UNKNOWN_NAME = 'Unknown';

export default function CombatLogPanel({ entries, tokens }: CombatLogPanelProps) {
  if (entries.length === 0) {
    return null;
  }

  const nameOf = (tokenId: string): string =>
    tokens.find((t) => t.token.id === tokenId)?.character.name ?? UNKNOWN_NAME;

  return (
    <div className="map-board__combat-log" role="log" aria-label="Combat log">
      <ul>
        {entries.map((entry) => (
          <li key={entry.id}>{formatAttackEntry(entry.payload, nameOf)}</li>
        ))}
      </ul>
    </div>
  );
}
