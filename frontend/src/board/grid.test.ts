import { describe, expect, it } from 'vitest';
import {
  buildGridLines,
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
