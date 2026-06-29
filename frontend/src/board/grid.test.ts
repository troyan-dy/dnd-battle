import { describe, expect, it } from 'vitest';
import {
  buildGridLines,
  cellDistanceFeet,
  DEFAULT_FEET_PER_CELL,
  DEFAULT_GRID,
  type GridConfig,
  MIN_CELL_SIZE,
  normalizeOffset,
} from './grid';

describe('normalizeOffset', () => {
  it('wraps offsets into [0, cellSize)', () => {
    expect(normalizeOffset(0, 10)).toBe(0);
    expect(normalizeOffset(10, 10)).toBe(0);
    expect(normalizeOffset(13, 10)).toBe(3);
    expect(normalizeOffset(-3, 10)).toBe(7);
    expect(normalizeOffset(-13, 10)).toBe(7);
  });

  it('returns 0 for a non-positive cell size or non-finite offset', () => {
    expect(normalizeOffset(5, 0)).toBe(0);
    expect(normalizeOffset(NaN, 10)).toBe(0);
    expect(normalizeOffset(Infinity, 10)).toBe(0);
  });
});

describe('buildGridLines', () => {
  it('emits vertical + horizontal lines spanning the box', () => {
    const cfg: GridConfig = { cellSize: 50, offsetX: 0, offsetY: 0 };
    const lines = buildGridLines(cfg, 100, 100);
    // x at 0,50,100 -> 3 verticals; y at 0,50,100 -> 3 horizontals.
    expect(lines).toHaveLength(6);
    // First vertical runs the full height; first horizontal the full width.
    expect(lines).toContainEqual([0, 0, 0, 100]);
    expect(lines).toContainEqual([0, 0, 100, 0]);
    expect(lines).toContainEqual([100, 0, 100, 100]);
  });

  it('applies a wrapped offset to the line positions', () => {
    const cfg: GridConfig = { cellSize: 50, offsetX: 60, offsetY: 0 };
    const lines = buildGridLines(cfg, 100, 50);
    // offsetX 60 wraps to 10 -> verticals at 10, 60 (within [0,100]).
    const verticals = lines.filter((l) => l[0] === l[2]).map((l) => l[0]);
    expect(verticals).toEqual([10, 60]);
  });

  it('returns no lines for cells below the minimum', () => {
    expect(
      buildGridLines({ cellSize: MIN_CELL_SIZE - 1, offsetX: 0, offsetY: 0 }, 100, 100),
    ).toEqual([]);
    expect(buildGridLines({ cellSize: NaN, offsetX: 0, offsetY: 0 }, 100, 100)).toEqual([]);
  });

  it('returns no lines for a degenerate box', () => {
    expect(buildGridLines(DEFAULT_GRID, 0, 100)).toEqual([]);
    expect(buildGridLines(DEFAULT_GRID, 100, 0)).toEqual([]);
    expect(buildGridLines(DEFAULT_GRID, -10, 100)).toEqual([]);
  });
});

describe('cellDistanceFeet', () => {
  it('is 0 for the same cell', () => {
    expect(cellDistanceFeet({ x: 3, y: 3 }, { x: 3, y: 3 })).toBe(0);
  });

  it('counts orthogonal moves at the default 5 ft per square', () => {
    expect(DEFAULT_FEET_PER_CELL).toBe(5);
    expect(cellDistanceFeet({ x: 0, y: 0 }, { x: 4, y: 0 })).toBe(20);
    expect(cellDistanceFeet({ x: 0, y: 0 }, { x: 0, y: 3 })).toBe(15);
  });

  it('counts a diagonal as the Chebyshev distance (D&D 2024: diagonals not penalised)', () => {
    // 3 right + 3 down = 3 squares of movement = 15 ft, not 30.
    expect(cellDistanceFeet({ x: 0, y: 0 }, { x: 3, y: 3 })).toBe(15);
    // Mixed deltas take the larger axis.
    expect(cellDistanceFeet({ x: 1, y: 1 }, { x: 5, y: 3 })).toBe(20);
  });

  it('is symmetric regardless of direction', () => {
    expect(cellDistanceFeet({ x: 5, y: 2 }, { x: 1, y: 0 })).toBe(
      cellDistanceFeet({ x: 1, y: 0 }, { x: 5, y: 2 }),
    );
  });

  it('honours a custom feet-per-cell scale', () => {
    expect(cellDistanceFeet({ x: 0, y: 0 }, { x: 2, y: 0 }, 10)).toBe(20);
  });

  it('returns 0 defensively for non-finite deltas or a non-positive scale', () => {
    expect(cellDistanceFeet({ x: 0, y: 0 }, { x: NaN, y: 0 })).toBe(0);
    expect(cellDistanceFeet({ x: 0, y: 0 }, { x: 3, y: 0 }, 0)).toBe(0);
    expect(cellDistanceFeet({ x: 0, y: 0 }, { x: 3, y: 0 }, -5)).toBe(0);
  });
});
