import { describe, expect, it } from 'vitest';
import type { Action, AttackResultPayload } from '../api/types';
import {
  appendLogEntry,
  formatLogEntry,
  logEntry,
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

describe('logEntry', () => {
  it('builds an entry from an attack action', () => {
    const entry = logEntry(attackAction('act-9'));
    expect(entry.id).toBe('act-9');
    expect(entry.payload.type).toBe('attack');
  });

  it('builds an entry from a non-attack action, preserving the payload', () => {
    const move: Action = {
      version: 1,
      id: 'act-2',
      room_id: 'room-1',
      actor_participant_id: 'p-1',
      seq: 1,
      payload: { type: 'move', token_id: 't1', x: 1, y: 1 },
    };
    const entry = logEntry(move);
    expect(entry.id).toBe('act-2');
    expect(entry.payload).toEqual({ type: 'move', token_id: 't1', x: 1, y: 1 });
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

describe('formatLogEntry', () => {
  const names: Record<string, string> = { ta: 'Goblin', tb: 'Aria' };
  const nameOf = (id: string) => names[id] ?? '?';

  it('formats an attack line resolving names', () => {
    const line = formatLogEntry(attackPayload(), nameOf);
    expect(line).toBe('Goblin attacks Aria: d20 (14) +5 = 19; 1d8+3 → 9 damage');
  });

  it('renders a negative attack bonus with its sign', () => {
    const line = formatLogEntry(attackPayload({ attack_bonus: -1, attack_total: 13 }), () => 'X');
    expect(line).toContain('(14) -1 = 13');
  });

  it('formats a move line', () => {
    const line = formatLogEntry({ type: 'move', token_id: 'ta', x: 3, y: 4 }, nameOf);
    expect(line).toBe('Goblin moves to (3, 4)');
  });

  it('formats a damage line', () => {
    const line = formatLogEntry({ type: 'damage', token_id: 'tb', amount: 7 }, nameOf);
    expect(line).toBe('Aria takes 7 damage');
  });

  it('formats a heal line', () => {
    const line = formatLogEntry({ type: 'heal', token_id: 'tb', amount: 4 }, nameOf);
    expect(line).toBe('Aria heals 4 HP');
  });

  it('formats a plain ping line', () => {
    const line = formatLogEntry({ type: 'mark', x: 2, y: 5 }, nameOf);
    expect(line).toBe('Ping at (2, 5)');
  });

  it('formats a labelled ping line', () => {
    const line = formatLogEntry({ type: 'mark', x: 2, y: 5, label: 'Trap' }, nameOf);
    expect(line).toBe('Ping "Trap" at (2, 5)');
  });

  it('formats an end-turn line', () => {
    expect(formatLogEntry({ type: 'endTurn' }, nameOf)).toBe('Turn ended');
  });
});
