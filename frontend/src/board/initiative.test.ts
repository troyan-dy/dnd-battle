import { describe, expect, it } from 'vitest';

import type { InitiativeEntryResponse, InitiativeState } from '../api/types';
import { activeEntry, advanceInitiative, EMPTY_INITIATIVE, isActiveCharacter } from './initiative';

function entry(over: Partial<InitiativeEntryResponse> = {}): InitiativeEntryResponse {
  return {
    id: over.id ?? 'e1',
    character_id: over.character_id ?? null,
    name: over.name ?? 'Goblin',
    initiative: over.initiative ?? 10,
    order_index: over.order_index ?? 0,
  };
}

function state(active: number | null, count = 2, round = 1): InitiativeState {
  const entries = Array.from({ length: count }, (_unused, i) =>
    entry({ id: 'e' + i, name: 'C' + i, order_index: i, character_id: 'c' + i }),
  );
  return { active_index: active, round, entries };
}

describe('advanceInitiative', () => {
  it('moves the pointer to the next seat', () => {
    const next = advanceInitiative(state(0));
    expect(next.active_index).toBe(1);
    expect(next.round).toBe(1);
  });

  it('wraps past the last seat and increments the round', () => {
    const next = advanceInitiative(state(1, 2, 3));
    expect(next.active_index).toBe(0);
    expect(next.round).toBe(4);
  });

  it('returns the same reference when no order is set', () => {
    const empty = EMPTY_INITIATIVE;
    expect(advanceInitiative(empty)).toBe(empty);
    const noActive: InitiativeState = { active_index: null, round: 1, entries: [entry()] };
    expect(advanceInitiative(noActive)).toBe(noActive);
  });
});

describe('activeEntry', () => {
  it('returns the combatant at the active index', () => {
    expect(activeEntry(state(1))?.name).toBe('C1');
  });

  it('returns null when combat has not started', () => {
    expect(activeEntry(EMPTY_INITIATIVE)).toBeNull();
  });

  it('returns null when the index is out of range', () => {
    expect(activeEntry({ active_index: 9, round: 1, entries: [entry()] })).toBeNull();
  });
});

describe('isActiveCharacter', () => {
  it('is true only for the character whose turn it is', () => {
    const s = state(0);
    expect(isActiveCharacter(s, 'c0')).toBe(true);
    expect(isActiveCharacter(s, 'c1')).toBe(false);
  });

  it('is false for a null/undefined character', () => {
    expect(isActiveCharacter(state(0), null)).toBe(false);
    expect(isActiveCharacter(state(0), undefined)).toBe(false);
  });
});
