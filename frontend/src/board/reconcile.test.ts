import { describe, expect, it } from 'vitest';
import {
  applyAction,
  beginOptimisticMove,
  displayTokens,
  EMPTY_BOARD,
  fromBoardState,
  fromTokens,
  rollbackMove,
} from './reconcile';
import type { Action, BoardState, TokenResponse } from '../api/types';

function token(over: Partial<TokenResponse> = {}): TokenResponse {
  return { id: 't1', room_id: 'r1', character_id: 'c1', x: 0, y: 0, size: 1, ...over };
}

function moveAction(tokenId: string, x: number, y: number): Action {
  return {
    version: 1,
    id: 'a1',
    room_id: 'r1',
    actor_participant_id: 'p1',
    seq: 0,
    payload: { type: 'move', token_id: tokenId, x, y },
  };
}

function pos(tokens: TokenResponse[], id: string): { x: number; y: number } {
  const t = tokens.find((tk) => tk.id === id)!;
  return { x: t.x, y: t.y };
}

describe('reconcile', () => {
  it('builds authoritative tokens from a BoardState and renders them', () => {
    const state: BoardState = {
      room_id: 'r1',
      tokens: [token({ x: 2, y: 3 })],
      characters: [],
      initiative: { active_index: null, round: 1, entries: [] },
    };
    const board = fromBoardState(state);
    expect(pos(displayTokens(board), 't1')).toEqual({ x: 2, y: 3 });
  });

  it('builds from a plain token list (REST hydrate)', () => {
    const board = fromTokens([token({ x: 1, y: 1 })]);
    expect(displayTokens(board)).toHaveLength(1);
  });

  it('shows an optimistic move immediately', () => {
    const board = beginOptimisticMove(fromTokens([token({ x: 0, y: 0 })]), 't1', 5, 6);
    expect(pos(displayTokens(board), 't1')).toEqual({ x: 5, y: 6 });
  });

  it('ignores an optimistic move for an unknown token', () => {
    const start = fromTokens([token()]);
    const board = beginOptimisticMove(start, 'ghost', 9, 9);
    expect(board).toBe(start);
  });

  it('reconciles a matching broadcast seamlessly (drops the pending overlay)', () => {
    let board = beginOptimisticMove(fromTokens([token()]), 't1', 4, 4);
    board = applyAction(board, moveAction('t1', 4, 4));
    expect(pos(displayTokens(board), 't1')).toEqual({ x: 4, y: 4 });
    expect(rollbackMove(board, 't1')).toBe(board);
  });

  it('snaps to the authoritative position on a mismatch (server wins / rollback)', () => {
    let board = beginOptimisticMove(fromTokens([token({ x: 0, y: 0 })]), 't1', 4, 4);
    board = applyAction(board, moveAction('t1', 1, 1));
    expect(pos(displayTokens(board), 't1')).toEqual({ x: 1, y: 1 });
  });

  it('rolls a rejected optimistic move back to the authoritative position', () => {
    let board = beginOptimisticMove(fromTokens([token({ x: 0, y: 0 })]), 't1', 7, 7);
    board = rollbackMove(board, 't1');
    expect(pos(displayTokens(board), 't1')).toEqual({ x: 0, y: 0 });
  });

  it('leaves token positions unchanged for non-move actions', () => {
    const board = fromTokens([token({ x: 2, y: 2 })]);
    const damage: Action = {
      ...moveAction('t1', 9, 9),
      payload: { type: 'damage', token_id: 't1', amount: 5 },
    };
    expect(applyAction(board, damage)).toBe(board);
  });

  it('ignores a move for a token not on the board', () => {
    const board = fromTokens([token()]);
    expect(applyAction(board, moveAction('ghost', 1, 1))).toBe(board);
  });

  it('starts empty', () => {
    expect(displayTokens(EMPTY_BOARD)).toEqual([]);
  });
});
