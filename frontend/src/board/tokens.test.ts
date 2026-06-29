import { describe, expect, it } from 'vitest';
import { hpBarColor, hpFraction, joinTokens, tokenRect, worldToCell } from './tokens';
import type { GridConfig } from './grid';
import type { CharacterResponse, TokenResponse } from '../api/types';

const grid: GridConfig = { cellSize: 50, offsetX: 10, offsetY: 20 };

function character(over: Partial<CharacterResponse> = {}): CharacterResponse {
  return {
    id: 'c1',
    room_id: 'r1',
    name: 'Aria',
    max_hp: 20,
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
    armor_class: 10,
    resistances: {},
    conditions: [],
    ...over,
  };
}

function token(over: Partial<TokenResponse> = {}): TokenResponse {
  return { id: 't1', room_id: 'r1', character_id: 'c1', x: 0, y: 0, size: 1, ...over };
}

describe('tokenRect', () => {
  it('aligns a 1x1 token to the grid cell, including offset', () => {
    const rect = tokenRect(token({ x: 2, y: 3, size: 1 }), grid);
    expect(rect).toEqual({ x: 110, y: 170, width: 50, height: 50 });
  });

  it('scales the footprint by token size', () => {
    const rect = tokenRect(token({ x: 1, y: 1, size: 3 }), grid);
    expect(rect.width).toBe(150);
    expect(rect.height).toBe(150);
  });

  it('treats a non-positive size as a single cell', () => {
    const rect = tokenRect(token({ size: 0 }), grid);
    expect(rect.width).toBe(50);
  });
});

describe('worldToCell', () => {
  it('is the inverse of tokenRect placement (snaps a cell corner back to its index)', () => {
    const rect = tokenRect(token({ x: 2, y: 3 }), grid);
    expect(worldToCell(rect.x, rect.y, grid)).toEqual({ x: 2, y: 3 });
  });

  it('rounds a point near a cell to that cell', () => {
    // Cell 2 starts at world 110 (offset 10 + 2*50); +24 still rounds to 2, +26 to 3.
    expect(worldToCell(134, 20, grid)).toEqual({ x: 2, y: 0 });
    expect(worldToCell(136, 20, grid)).toEqual({ x: 3, y: 0 });
  });

  it('clamps negative cells to 0 (server grid lower bound)', () => {
    expect(worldToCell(-200, -200, grid)).toEqual({ x: 0, y: 0 });
  });
});

describe('joinTokens', () => {
  it('joins each token to its character by id', () => {
    const joined = joinTokens([token()], [character()]);
    expect(joined).toHaveLength(1);
    expect(joined[0].character.name).toBe('Aria');
  });

  it('drops tokens whose character is missing', () => {
    const joined = joinTokens([token({ character_id: 'gone' })], [character()]);
    expect(joined).toHaveLength(0);
  });
});

describe('hpFraction', () => {
  it('returns the clamped ratio of current to max', () => {
    expect(hpFraction(10, 20)).toBe(0.5);
    expect(hpFraction(30, 20)).toBe(1);
    expect(hpFraction(-5, 20)).toBe(0);
  });

  it('returns 0 when max HP is non-positive', () => {
    expect(hpFraction(5, 0)).toBe(0);
  });
});

describe('hpBarColor', () => {
  it('moves green -> amber -> red as HP drops', () => {
    expect(hpBarColor(0.8)).toBe('#3fb950');
    expect(hpBarColor(0.4)).toBe('#d29922');
    expect(hpBarColor(0.1)).toBe('#f85149');
  });
});
