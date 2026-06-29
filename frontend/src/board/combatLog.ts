// Pure formatting helpers for the shared combat log (Phase 5).
//
// Kept free of React/Konva so the log math/format is unit-testable in isolation.
// An attack the server broadcasts (an `attack` Action) becomes a human-readable
// line everyone in the room sees. The full shared combat-log PANEL (more entry
// types, scrolling, etc.) is the next Phase-5 task; this module covers the attack
// entries this task introduces.

import type { Action, AttackResultPayload } from '../api/types';

/** Keep at most this many log lines client-side (newest kept, oldest dropped). */
export const MAX_LOG_ENTRIES = 50;

/** A single combat-log entry, keyed by the broadcast Action's id. */
export interface CombatLogEntry {
  id: string;
  payload: AttackResultPayload;
}

/** Build a log entry from a broadcast Action, or null for any non-attack action. */
export function attackLogEntry(action: Action): CombatLogEntry | null {
  if (action.payload.type !== 'attack') {
    return null;
  }
  return { id: action.id, payload: action.payload };
}

/** Append an entry, keeping at most {@link MAX_LOG_ENTRIES} (newest last). */
export function appendLogEntry(entries: CombatLogEntry[], entry: CombatLogEntry): CombatLogEntry[] {
  const next = [...entries, entry];
  return next.length > MAX_LOG_ENTRIES ? next.slice(next.length - MAX_LOG_ENTRIES) : next;
}

/** Format the signed to-hit bonus, e.g. `+3` or `-1`. */
function formatBonus(bonus: number): string {
  return bonus >= 0 ? `+${bonus}` : `${bonus}`;
}

/**
 * Format an attack result as a readable line. `nameOf` resolves a token id to a
 * display name (its character's name), falling back to a placeholder.
 */
export function formatAttackEntry(
  payload: AttackResultPayload,
  nameOf: (tokenId: string) => string,
): string {
  const attacker = nameOf(payload.attacker_token_id);
  const target = nameOf(payload.target_token_id);
  return (
    `${attacker} attacks ${target}: ` +
    `d20 (${payload.attack_roll}) ${formatBonus(payload.attack_bonus)} = ${payload.attack_total}; ` +
    `${payload.damage} → ${payload.damage_total} damage`
  );
}
