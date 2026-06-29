// Pure geometry for the board's square grid overlay.
//
// Kept free of React/Konva so it can be unit-tested in isolation. The grid is
// drawn in WORLD (image) coordinates and lives inside the same Konva stage as
// the map, so the viewport transform scales/pans it for free.
//
// A GridConfig describes a square grid by its cell size and an offset that
// shifts the lines so they can line up with the map's own squares. Offset is
// applied modulo cellSize, so any value lands the grid in the same place as a
// value within [0, cellSize).

export interface GridConfig {
  /** World pixels per cell (one D&D square). */
  cellSize: number;
  /** World-pixel shift of the grid origin along X. */
  offsetX: number;
  /** World-pixel shift of the grid origin along Y. */
  offsetY: number;
}

/** A single grid line as Konva-style flat points: [x1, y1, x2, y2] (world). */
export type GridLine = [number, number, number, number];

/** Sensible starting grid: 70px cells (~a 5ft square at common map DPI), no offset. */
export const DEFAULT_GRID: GridConfig = { cellSize: 70, offsetX: 0, offsetY: 0 };

/** Smallest cell we allow so we never emit an unbounded number of lines. */
export const MIN_CELL_SIZE = 5;

/**
 * D&D 2024 standard grid scale: each square is 5 feet on a side, and every
 * square entered — orthogonal OR diagonal — costs that same 5 feet (PHB 2024
 * "Moving Around Other Creatures"/grid movement: diagonals are not penalised).
 */
export const DEFAULT_FEET_PER_CELL = 5;

/**
 * Distance in feet between two integer grid cells using the D&D 2024 standard
 * rule: the number of squares moved is the Chebyshev distance (the larger of the
 * two axis deltas, since a diagonal step covers one square of both), multiplied
 * by the feet-per-square scale. Returns 0 for the same cell.
 *
 * Non-finite inputs or a non-positive scale yield 0 (defensive — a measurement
 * is purely informational and must never throw mid-drag).
 */
export function cellDistanceFeet(
  from: { x: number; y: number },
  to: { x: number; y: number },
  feetPerCell: number = DEFAULT_FEET_PER_CELL,
): number {
  const dx = Math.abs(to.x - from.x);
  const dy = Math.abs(to.y - from.y);
  if (!Number.isFinite(dx) || !Number.isFinite(dy) || !(feetPerCell > 0)) {
    return 0;
  }
  return Math.max(dx, dy) * feetPerCell;
}

/** Normalise an offset into the half-open range [0, cellSize). */
export function normalizeOffset(offset: number, cellSize: number): number {
  if (cellSize <= 0 || !Number.isFinite(offset)) {
    return 0;
  }
  // `%` keeps the sign of the dividend in JS, so add cellSize and mod again.
  return ((offset % cellSize) + cellSize) % cellSize;
}

/**
 * Build the vertical + horizontal lines covering the world box
 * [0, width] x [0, height] for the given grid config.
 *
 * Returns an empty array for non-positive box dimensions or a cell size below
 * MIN_CELL_SIZE (which also guards against NaN/Infinity).
 */
export function buildGridLines(config: GridConfig, width: number, height: number): GridLine[] {
  const { cellSize } = config;
  if (
    !(cellSize >= MIN_CELL_SIZE) || // also rejects NaN
    !(width > 0) ||
    !(height > 0)
  ) {
    return [];
  }

  const lines: GridLine[] = [];
  const startX = normalizeOffset(config.offsetX, cellSize);
  const startY = normalizeOffset(config.offsetY, cellSize);

  for (let x = startX; x <= width; x += cellSize) {
    lines.push([x, 0, x, height]);
  }
  for (let y = startY; y <= height; y += cellSize) {
    lines.push([0, y, width, y]);
  }
  return lines;
}
