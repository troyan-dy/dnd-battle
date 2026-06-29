// Pure transient-mark (ping) management for the board.
//
// Marks / pings are EPHEMERAL by design (architect decision): the server
// validates and broadcasts a `mark` Action to everyone in the room but stores
// NOTHING durable — there is no Mark row and no BoardState.marks field, so the
// `mark` branch of the server's apply_action is a deliberate no-op. A client that
// reconnects therefore won't see pings dropped before it joined: CLAUDE.md rule 2
// (reconnect-safe) governs the DURABLE board state, and a ping is transient by
// definition. Each mark auto-expires after MARK_TTL_MS.
//
// The server echoes a placed mark back to the sender too (it broadcasts to the
// whole room), so no optimistic overlay is needed — every client, including the
// one that placed it, renders the mark when the authoritative Action arrives.
//
// This module is kept free of React/Konva so the list + expiry logic is
// unit-testable in isolation; rendering lives in MarkLayer.

import type { Action, MarkPayload } from '../api/types';

/** A live mark/ping on the board: a grid cell + cosmetics + an expiry deadline. */
export interface BoardMark {
  /** Unique key — the broadcast Action's id. */
  id: string;
  /** Grid cell column / row. */
  x: number;
  y: number;
  /** Optional display colour (CSS string) and short label. */
  color?: string | null;
  label?: string | null;
  /** Epoch milliseconds after which the mark is removed. */
  expiresAt: number;
}

/** How long a ping stays on the board before it fades out. */
export const MARK_TTL_MS = 4000;

/** Hard cap on simultaneous marks so a flood can never grow memory unbounded. */
export const MAX_MARKS = 50;

/** Fallback ping colour when an Action carries none. */
export const DEFAULT_MARK_COLOR = '#ffd33d';

/**
 * Build a {@link BoardMark} from a broadcast `mark` Action, expiring `ttl` ms
 * from `now`. Returns null for any non-mark Action so callers can filter in one
 * step.
 */
export function markFromAction(
  action: Action,
  now: number,
  ttl: number = MARK_TTL_MS,
): BoardMark | null {
  if (action.payload.type !== 'mark') {
    return null;
  }
  const payload: MarkPayload = action.payload;
  return {
    id: action.id,
    x: payload.x,
    y: payload.y,
    color: payload.color ?? null,
    label: payload.label ?? null,
    expiresAt: now + ttl,
  };
}

/**
 * Append a mark, replacing any existing one with the same id, capped to `max`
 * (oldest dropped). Returns a new array.
 */
export function addMark(
  marks: readonly BoardMark[],
  mark: BoardMark,
  max: number = MAX_MARKS,
): BoardMark[] {
  const next = marks.filter((m) => m.id !== mark.id);
  next.push(mark);
  if (next.length > max) {
    next.splice(0, next.length - max);
  }
  return next;
}

/**
 * Remove marks whose expiry has passed. Returns the SAME array reference when
 * nothing changed, so a React state setter can bail out and skip a re-render.
 */
export function pruneExpired(marks: readonly BoardMark[], now: number): BoardMark[] {
  const kept = marks.filter((m) => m.expiresAt > now);
  return kept.length === marks.length ? (marks as BoardMark[]) : kept;
}
