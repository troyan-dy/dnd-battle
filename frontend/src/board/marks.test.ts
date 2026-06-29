import { describe, expect, it } from 'vitest';
import type { Action } from '../api/types';
import {
  addMark,
  DEFAULT_MARK_COLOR,
  MARK_TTL_MS,
  markFromAction,
  pruneExpired,
  type BoardMark,
} from './marks';

function markAction(overrides: Partial<Action> = {}): Action {
  return {
    version: 1,
    id: 'act-1',
    room_id: 'room-1',
    actor_participant_id: 'p-1',
    seq: 0,
    payload: { type: 'mark', x: 3, y: 4, color: '#ff0000', label: 'here' },
    ...overrides,
  };
}

function mark(overrides: Partial<BoardMark> = {}): BoardMark {
  return { id: 'm', x: 0, y: 0, expiresAt: 1000, ...overrides };
}

describe('markFromAction', () => {
  it('builds a mark from a mark Action, keyed by the action id and expiring after the ttl', () => {
    const result = markFromAction(markAction(), 500);
    expect(result).toEqual({
      id: 'act-1',
      x: 3,
      y: 4,
      color: '#ff0000',
      label: 'here',
      expiresAt: 500 + MARK_TTL_MS,
    });
  });

  it('honours a custom ttl and null colour/label defaults', () => {
    const action = markAction({ payload: { type: 'mark', x: 1, y: 2 } });
    const result = markFromAction(action, 100, 50);
    expect(result).toEqual({ id: 'act-1', x: 1, y: 2, color: null, label: null, expiresAt: 150 });
  });

  it('returns null for a non-mark Action', () => {
    const move = markAction({ payload: { type: 'move', token_id: 't', x: 0, y: 0 } });
    expect(markFromAction(move, 0)).toBeNull();
  });
});

describe('addMark', () => {
  it('appends a new mark', () => {
    const result = addMark([mark({ id: 'a' })], mark({ id: 'b' }));
    expect(result.map((m) => m.id)).toEqual(['a', 'b']);
  });

  it('replaces an existing mark with the same id (re-pinging the same action)', () => {
    const result = addMark([mark({ id: 'a', x: 1 })], mark({ id: 'a', x: 9 }));
    expect(result).toHaveLength(1);
    expect(result[0].x).toBe(9);
  });

  it('caps the list to max, dropping the oldest', () => {
    const result = addMark([mark({ id: 'a' }), mark({ id: 'b' })], mark({ id: 'c' }), 2);
    expect(result.map((m) => m.id)).toEqual(['b', 'c']);
  });
});

describe('pruneExpired', () => {
  it('removes marks whose expiry has passed and keeps live ones', () => {
    const result = pruneExpired(
      [mark({ id: 'old', expiresAt: 100 }), mark({ id: 'live', expiresAt: 5000 })],
      1000,
    );
    expect(result.map((m) => m.id)).toEqual(['live']);
  });

  it('returns the same array reference when nothing expired (lets React bail out)', () => {
    const marks = [mark({ id: 'a', expiresAt: 5000 })];
    expect(pruneExpired(marks, 1000)).toBe(marks);
  });
});

describe('DEFAULT_MARK_COLOR', () => {
  it('is a CSS colour string', () => {
    expect(DEFAULT_MARK_COLOR).toMatch(/^#[0-9a-f]{3,8}$/i);
  });
});
