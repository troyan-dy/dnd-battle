// Apply live HP changes from broadcast damage/heal Actions to character stat blocks.
//
// Kept free of React/Konva so the HP math is unit-testable in isolation. The
// server is authoritative (CLAUDE.md rule 1): a `damage`/`heal` Action it
// broadcasts must be reflected in the rendered token HP immediately, without
// waiting for the next full BoardState push. These pure helpers compute the new
// character list from a broadcast payload; they mirror the server's clamping
// (damage floors at 0, heal ceilings at max HP) so the optimistic-free client
// stays consistent with the durable rows.

import type { ActionPayload, CharacterResponse } from '../api/types';

/** Clamp an HP value to the valid [0, maxHp] range (maxHp <= 0 floors to 0). */
export function clampHp(value: number, maxHp: number): number {
  const ceiling = maxHp > 0 ? maxHp : 0;
  return Math.min(ceiling, Math.max(0, value));
}

/**
 * Apply a broadcast `damage`/`heal` payload to the character with `characterId`.
 *
 * Returns the SAME array reference when nothing changes (unrelated action type,
 * unknown character, or HP already at the clamp boundary) so React can bail out
 * of a re-render. Damage subtracts (clamped at 0); heal adds (clamped at max HP).
 */
export function applyHpAction(
  characters: CharacterResponse[],
  characterId: string,
  payload: ActionPayload,
): CharacterResponse[] {
  let delta: number;
  if (payload.type === 'damage') {
    delta = -payload.amount;
  } else if (payload.type === 'heal') {
    delta = payload.amount;
  } else {
    return characters;
  }

  let changed = false;
  const next = characters.map((c) => {
    if (c.id !== characterId) {
      return c;
    }
    const updated = clampHp(c.current_hp + delta, c.max_hp);
    if (updated === c.current_hp) {
      return c;
    }
    changed = true;
    return { ...c, current_hp: updated };
  });
  return changed ? next : characters;
}
