// Pure geometry + display helpers for board tokens.
//
// Kept free of React/Konva so it can be unit-tested in isolation. A token lives
// at integer grid coordinates (x, y) and occupies a `size` x `size` block of
// cells; here we turn that into a WORLD-coordinate rectangle that lines up with
// the grid overlay (same cellSize + offset), so it pans/zooms with the stage.

import type { GridConfig } from './grid';
import type { CharacterResponse, TokenResponse } from '../api/types';

/** A token's world-coordinate footprint: top-left corner + width/height. */
export interface TokenRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** World rectangle a token occupies, aligned to the grid's cell size + offset. */
export function tokenRect(
  token: Pick<TokenResponse, 'x' | 'y' | 'size'>,
  grid: GridConfig,
): TokenRect {
  const cell = grid.cellSize;
  const span = Math.max(1, token.size) * cell;
  return {
    x: grid.offsetX + token.x * cell,
    y: grid.offsetY + token.y * cell,
    width: span,
    height: span,
  };
}

/**
 * Inverse of {@link tokenRect}'s placement: snap a world-coordinate point to the
 * nearest grid cell index. Used when a dragged token is dropped to turn its new
 * world position back into the integer `(x, y)` cell the server stores. Clamped to
 * non-negative indices to match the server's grid bounds (GRID_COORD_MIN = 0).
 */
export function worldToCell(
  worldX: number,
  worldY: number,
  grid: GridConfig,
): { x: number; y: number } {
  const cell = grid.cellSize > 0 ? grid.cellSize : 1;
  return {
    x: Math.max(0, Math.round((worldX - grid.offsetX) / cell)),
    y: Math.max(0, Math.round((worldY - grid.offsetY) / cell)),
  };
}

/** A token joined with the character it is bound to (display data resolved). */
export interface PlacedToken {
  token: TokenResponse;
  character: CharacterResponse;
}

/**
 * Join tokens to their characters by `character_id`.
 *
 * Tokens whose character is missing from `characters` are dropped — the board
 * only renders pieces it has display data for (the server is authoritative; a
 * dangling token would be a transient inconsistency we simply don't draw).
 */
export function joinTokens(
  tokens: readonly TokenResponse[],
  characters: readonly CharacterResponse[],
): PlacedToken[] {
  const byId = new Map(characters.map((c) => [c.id, c]));
  const placed: PlacedToken[] = [];
  for (const token of tokens) {
    const character = byId.get(token.character_id);
    if (character) {
      placed.push({ token, character });
    }
  }
  return placed;
}

/** Fraction of max HP remaining, clamped to [0, 1]. Returns 0 if max_hp <= 0. */
export function hpFraction(currentHp: number, maxHp: number): number {
  if (!(maxHp > 0)) {
    return 0;
  }
  return Math.min(1, Math.max(0, currentHp / maxHp));
}

/** Colour for an HP bar given its remaining fraction (green → amber → red). */
export function hpBarColor(fraction: number): string {
  if (fraction > 0.5) {
    return '#3fb950'; // healthy
  }
  if (fraction > 0.25) {
    return '#d29922'; // bloodied
  }
  return '#f85149'; // critical
}
