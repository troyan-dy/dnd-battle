import { describe, expect, it } from 'vitest';
import type { Action, AttackResultPayload } from '../api/types';
import {
  appendLogEntry,
  attackLogEntry,
  formatAttackEntry,
  MAX_LOG_ENTRIES,
  type CombatLogEntry,
} from './combatLog';

function attackPayload(overrides: Partial<AttackResultPayload> = {}): AttackResultPayload {
  return {
    type: 'attack',
    attacker_token_id: 'ta',
    target_token_id: 'tb',
    attack_roll: 14,
    attack_bonus: 5,
    attack_total: 19,
    damage: '1d8+3',
    damage_rolls: [6],
    damage_total: 9,
    ...overrides,
  };
}

function attackAction(id = 'act-1'): Action {
  return {
    version: 1,
    id,
    room_id: 'room-1',
    actor_participant_id: 'p-1',
    seq: 0,
    payload: attackPayload(),
  };
}

describe('attackLogEntry', () => {
  it('builds an entry from an attack action', () => {
    const entry = attackLogEntry(attackAction('act-9'));
    expect(entry).not.toBeNull();
    expect(entry?.id).toBe('act-9');
    expect(entry?.payload.damage_total).toBe(9);
  });

  it('returns null for a non-attack action', () => {
    const move: Action = {
      version: 1,
      id: 'act-2',
      room_id: 'room-1',
      actor_participant_id: 'p-1',
      seq: 1,
      payload: { type: 'move', token_id: 't1', x: 1, y: 1 },
    };
    expect(attackLogEntry(move)).toBeNull();
  });
});

describe('appendLogEntry', () => {
  it('appends newest last', () => {
    const a: CombatLogEntry = { id: 'a', payload: attackPayload() };
    const b: CombatLogEntry = { id: 'b', payload: attackPayload() };
    const result = appendLogEntry(appendLogEntry([], a), b);
    expect(result.map((e) => e.id)).toEqual(['a', 'b']);
  });

  it('caps at MAX_LOG_ENTRIES, dropping the oldest', () => {
    let entries: CombatLogEntry[] = [];
    for (let i = 0; i < MAX_LOG_ENTRIES + 5; i++) {
      entries = appendLogEntry(entries, { id: `e${i}`, payload: attackPayload() });
    }
    expect(entries.length).toBe(MAX_LOG_ENTRIES);
    expect(entries[0].id).toBe('e5');
    expect(entries[entries.length - 1].id).toBe(`e${MAX_LOG_ENTRIES + 4}`);
  });
});

describe('formatAttackEntry', () => {
  it('formats a readable line resolving names', () => {
    const names: Record<string, string> = { ta: 'Goblin', tb: 'Aria' };
    const line = formatAttackEntry(attackPayload(), (id) => names[id] ?? '?');
    expect(line).toBe('Goblin attacks Aria: d20 (14) +5 = 19; 1d8+3 → 9 damage');
  });

  it('renders a negative bonus with its sign', () => {
    const line = formatAttackEntry(
      attackPayload({ attack_bonus: -1, attack_total: 13 }),
      () => 'X',
    );
    expect(line).toContain('(14) -1 = 13');
  });
});
