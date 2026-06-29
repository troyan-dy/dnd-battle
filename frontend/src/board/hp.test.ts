import { describe, expect, it } from 'vitest';
import type { ActionPayload, CharacterResponse } from '../api/types';
import { applyHpAction, clampHp } from './hp';

function char(overrides: Partial<CharacterResponse> = {}): CharacterResponse {
  return {
    id: 'c1',
    room_id: 'r1',
    name: 'Aria',
    max_hp: 30,
    current_hp: 20,
    portrait_url: null,
    ability_scores: {
      strength: 10,
      dexterity: 10,
      constitution: 10,
      intelligence: 10,
      wisdom: 10,
      charisma: 10,
    },
    conditions: [],
    ...overrides,
  };
}

describe('clampHp', () => {
  it('floors at 0 and ceilings at max', () => {
    expect(clampHp(-5, 30)).toBe(0);
    expect(clampHp(50, 30)).toBe(30);
    expect(clampHp(12, 30)).toBe(12);
  });

  it('floors to 0 when max is non-positive', () => {
    expect(clampHp(5, 0)).toBe(0);
  });
});

describe('applyHpAction', () => {
  const damage = (amount: number): ActionPayload => ({ type: 'damage', token_id: 't1', amount });
  const heal = (amount: number): ActionPayload => ({ type: 'heal', token_id: 't1', amount });

  it('reduces HP on damage, clamped at 0', () => {
    const next = applyHpAction([char({ current_hp: 20 })], 'c1', damage(5));
    expect(next[0].current_hp).toBe(15);
    const dead = applyHpAction([char({ current_hp: 3 })], 'c1', damage(100));
    expect(dead[0].current_hp).toBe(0);
  });

  it('restores HP on heal, clamped at max', () => {
    const next = applyHpAction([char({ current_hp: 20, max_hp: 30 })], 'c1', heal(5));
    expect(next[0].current_hp).toBe(25);
    const full = applyHpAction([char({ current_hp: 28, max_hp: 30 })], 'c1', heal(100));
    expect(full[0].current_hp).toBe(30);
  });

  it('only touches the targeted character', () => {
    const a = char({ id: 'c1', current_hp: 20 });
    const b = char({ id: 'c2', current_hp: 20 });
    const next = applyHpAction([a, b], 'c2', damage(4));
    expect(next[0]).toBe(a);
    expect(next[1].current_hp).toBe(16);
  });

  it('returns the same array reference when nothing changes', () => {
    const list = [char({ current_hp: 20 })];
    expect(applyHpAction(list, 'nope', damage(5))).toBe(list);
    const dead = [char({ current_hp: 0 })];
    expect(applyHpAction(dead, 'c1', damage(5))).toBe(dead);
    const move: ActionPayload = { type: 'move', token_id: 't1', x: 1, y: 1 };
    expect(applyHpAction(list, 'c1', move)).toBe(list);
  });
});
