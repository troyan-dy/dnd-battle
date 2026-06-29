// Pure initiative / turn-order helpers, kept free of React/Konva so they are
// unit-testable (mirrors the established board pattern). The server is
// authoritative (CLAUDE.md rule 1): the full InitiativeState arrives in every
// `boardState` push (reconnect-safe, rule 2). When an `endTurn` Action is
// broadcast it carries no new index, so the client advances its local pointer the
// SAME way the server does (`app.services.initiative.advance_turn`) for instant
// feedback; the next boardState push reconciles any drift.

import type { InitiativeEntryResponse, InitiativeState } from '../api/types';

/** An empty, "combat not started" initiative state. */
export const EMPTY_INITIATIVE: InitiativeState = {
  active_index: null,
  round: 1,
  entries: [],
};

/**
 * Advance the turn pointer to the next combatant, mirroring the server.
 *
 * Wrapping past the last seat resets to seat 0 and increments the round. A no-op
 * (returns the SAME reference, so React can bail on the update) when no order is
 * set — no entries or `active_index` is null.
 */
export function advanceInitiative(state: InitiativeState): InitiativeState {
  const count = state.entries.length;
  if (count === 0 || state.active_index === null) {
    return state;
  }
  const next = state.active_index + 1;
  if (next >= count) {
    return { ...state, active_index: 0, round: state.round + 1 };
  }
  return { ...state, active_index: next };
}

/** The combatant whose turn it currently is, or null (combat not started / OOB). */
export function activeEntry(state: InitiativeState): InitiativeEntryResponse | null {
  if (state.active_index === null) {
    return null;
  }
  return state.entries[state.active_index] ?? null;
}

/** Whether it is currently the given character's turn. */
export function isActiveCharacter(
  state: InitiativeState,
  characterId: string | null | undefined,
): boolean {
  if (characterId == null) {
    return false;
  }
  const entry = activeEntry(state);
  return entry !== null && entry.character_id === characterId;
}
