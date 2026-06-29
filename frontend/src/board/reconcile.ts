// Optimistic-move reconciliation for the board (CLAUDE.md rule 5).
//
// Kept free of React/Konva so the rule-5 logic is unit-testable in isolation.
// The server is authoritative: a client may move its own token locally for
// instant feedback (an "optimistic" move), but the server's broadcast — or full
// BoardState snapshot — is the source of truth. We model the board as the
// server-authoritative truth plus a thin overlay of optimistic moves this client
// has emitted but not yet seen confirmed. What we DISPLAY is the truth with any
// pending optimistic position applied on top; when the authoritative position
// arrives the overlay is dropped, so a matching broadcast is seamless and a
// mismatching one snaps the token back to the server's position (a rollback).

import type { Action, BoardState, TokenResponse } from '../api/types';

/** Server-authoritative token truth + a per-token optimistic position overlay. */
export interface ReconcilableBoard {
  authoritative: ReadonlyMap<string, TokenResponse>;
  pending: ReadonlyMap<string, { x: number; y: number }>;
}

/** An empty board (no tokens, no pending moves). */
export const EMPTY_BOARD: ReconcilableBoard = {
  authoritative: new Map(),
  pending: new Map(),
};

/** Build an authoritative board from a full server snapshot (clears optimism). */
export function fromBoardState(state: BoardState): ReconcilableBoard {
  return {
    authoritative: new Map(state.tokens.map((t) => [t.id, t])),
    pending: new Map(),
  };
}

/** Build from a plain token list (e.g. the REST hydrate before the socket joins). */
export function fromTokens(tokens: readonly TokenResponse[]): ReconcilableBoard {
  return {
    authoritative: new Map(tokens.map((t) => [t.id, t])),
    pending: new Map(),
  };
}

/**
 * Record an optimistic local move for instant feedback. We never invent a token
 * the server doesn't know about, so a move targeting an unknown token is ignored.
 */
export function beginOptimisticMove(
  board: ReconcilableBoard,
  tokenId: string,
  x: number,
  y: number,
): ReconcilableBoard {
  if (!board.authoritative.has(tokenId)) {
    return board;
  }
  const pending = new Map(board.pending);
  pending.set(tokenId, { x, y });
  return { authoritative: board.authoritative, pending };
}

/** Drop a pending optimistic move (e.g. the server rejected the intent) → roll back. */
export function rollbackMove(board: ReconcilableBoard, tokenId: string): ReconcilableBoard {
  if (!board.pending.has(tokenId)) {
    return board;
  }
  const pending = new Map(board.pending);
  pending.delete(tokenId);
  return { authoritative: board.authoritative, pending };
}

/**
 * Apply a server-broadcast Action to the authoritative truth and reconcile any
 * matching optimistic move. Only `move` actions change token positions; the
 * pending overlay for the moved token is dropped, so the display reflects the
 * server's position (a no-op if it matched, a rollback if it differed).
 */
export function applyAction(board: ReconcilableBoard, action: Action): ReconcilableBoard {
  const { payload } = action;
  if (payload.type !== 'move') {
    return board;
  }
  const existing = board.authoritative.get(payload.token_id);
  if (!existing) {
    return board;
  }
  const authoritative = new Map(board.authoritative);
  authoritative.set(payload.token_id, { ...existing, x: payload.x, y: payload.y });
  const pending = new Map(board.pending);
  pending.delete(payload.token_id);
  return { authoritative, pending };
}

/** Tokens to render: the authoritative truth with any optimistic move applied. */
export function displayTokens(board: ReconcilableBoard): TokenResponse[] {
  const out: TokenResponse[] = [];
  for (const token of board.authoritative.values()) {
    const opt = board.pending.get(token.id);
    out.push(opt ? { ...token, x: opt.x, y: opt.y } : token);
  }
  return out;
}
