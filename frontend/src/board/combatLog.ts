// Pure formatting helpers for the shared combat log (Phase 5).
//
// Kept free of React/Konva so the log math/format is unit-testable in isolation.
// Every board change the server BROADCASTS (a move/mark/damage/heal/attack/endTurn
// Action) becomes a human-readable line everyone in the room sees in the same
// order. The log is transient/client-built (like pings) — a reconnecting client
// rebuilds from the boardState push and only sees subsequent lines; it is NOT a
// durable, replayable transcript (that would be an architect-gated change).

import type { Action, AttackResultPayload, BroadcastActionPayload } from '../api/types';

/** Keep at most this many log lines client-side (newest kept, oldest dropped). */
export const MAX_LOG_ENTRIES = 50;

/** A single combat-log entry, keyed by the broadcast Action's id. */
export interface CombatLogEntry {
  id: string;
  payload: BroadcastActionPayload;
}

/** Build a log entry from any broadcast Action. */
export function logEntry(action: Action): CombatLogEntry {
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
function formatAttackEntry(
  payload: AttackResultPayload,
  nameOf: (tokenId: string) => string,
): string {
  const attacker = nameOf(payload.attacker_token_id);
  const target = nameOf(payload.target_token_id);
  const adv =
    payload.advantage === 'advantage'
      ? ' (adv)'
      : payload.advantage === 'disadvantage'
        ? ' (dis)'
        : '';
  const roll =
    `d20 (${payload.attack_roll})${adv} ${formatBonus(payload.attack_bonus)} = ` +
    `${payload.attack_total} vs AC ${payload.armor_class}`;
  if (!payload.is_hit) {
    const miss = payload.is_critical_miss ? 'critical miss' : 'miss';
    return `${attacker} attacks ${target}: ${roll} — ${miss}`;
  }
  const hit = payload.is_critical_hit ? 'critical hit' : 'hit';
  const resisted =
    payload.defense === 'normal' ? '' : ` (${payload.damage_type} ${payload.defense})`;
  return (
    `${attacker} attacks ${target}: ${roll} — ${hit}; ` +
    `${payload.damage} → ${payload.damage_total} damage${resisted}`
  );
}

/**
 * Format any broadcast payload as a readable combat-log line. `nameOf` resolves a
 * token id to a display name (its character's name), falling back to a placeholder.
 */
export function formatLogEntry(
  payload: BroadcastActionPayload,
  nameOf: (tokenId: string) => string,
): string {
  switch (payload.type) {
    case 'move':
      return `${nameOf(payload.token_id)} moves to (${payload.x}, ${payload.y})`;
    case 'mark': {
      const where = `(${payload.x}, ${payload.y})`;
      return payload.label ? `Ping "${payload.label}" at ${where}` : `Ping at ${where}`;
    }
    case 'damage':
      return `${nameOf(payload.token_id)} takes ${payload.amount} damage`;
    case 'heal':
      return `${nameOf(payload.token_id)} heals ${payload.amount} HP`;
    case 'attack':
      return formatAttackEntry(payload, nameOf);
    case 'endTurn':
      return 'Turn ended';
  }
}
