// Shared combat-log overlay (Phase 5): renders the lines the server has broadcast
// (move/mark/damage/heal/attack/endTurn) so EVERYONE in the room sees the same log
// in the same order. Names are resolved from the current tokens at render time, so
// the log stays correct regardless of when an entry was recorded. The panel
// scrolls and auto-sticks to the newest line.

import { useEffect, useRef } from 'react';
import { type CombatLogEntry, formatLogEntry } from './combatLog';
import type { PlacedToken } from './tokens';

export interface CombatLogPanelProps {
  /** Log entries, oldest first. */
  entries: CombatLogEntry[];
  /** Current placed tokens, used to resolve a token id to its character's name. */
  tokens: PlacedToken[];
}

const UNKNOWN_NAME = 'Unknown';

export default function CombatLogPanel({ entries, tokens }: CombatLogPanelProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Keep the newest line in view as entries arrive.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [entries]);

  if (entries.length === 0) {
    return null;
  }

  const nameOf = (tokenId: string): string =>
    tokens.find((t) => t.token.id === tokenId)?.character.name ?? UNKNOWN_NAME;

  return (
    <div
      ref={scrollRef}
      className="map-board__combat-log"
      role="log"
      aria-label="Combat log"
      aria-live="polite"
    >
      <ul>
        {entries.map((entry) => (
          <li key={entry.id} data-action-type={entry.payload.type}>
            {formatLogEntry(entry.payload, nameOf)}
          </li>
        ))}
      </ul>
    </div>
  );
}
