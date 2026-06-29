import { describe, expect, it } from 'vitest';

import {
  ACTION_PROTOCOL_VERSION,
  type Action,
  type ActionIntent,
  type ActionPayload,
} from './types';

// These are compile-time contract checks first (tsc must accept the literal
// shapes), plus a couple of runtime assertions so the suite has live tests that
// exercise the discriminated union narrowing.

describe('Action protocol types', () => {
  it('exposes the protocol version constant', () => {
    expect(ACTION_PROTOCOL_VERSION).toBe(1);
  });

  it('narrows a payload by its discriminator', () => {
    const payload: ActionPayload = { type: 'move', token_id: 't1', x: 2, y: 3 };
    if (payload.type === 'move') {
      expect(payload.x).toBe(2);
      expect(payload.y).toBe(3);
    } else {
      throw new Error('expected a move payload');
    }
  });

  it('narrows the heal payload by its discriminator', () => {
    const payload: ActionPayload = { type: 'heal', token_id: 't1', amount: 4 };
    if (payload.type === 'heal') {
      expect(payload.amount).toBe(4);
      expect(payload.token_id).toBe('t1');
    } else {
      throw new Error('expected a heal payload');
    }
  });

  it('accepts a minimal intent and a full server broadcast', () => {
    const intent: ActionIntent = { payload: { type: 'endTurn' } };
    expect(intent.payload.type).toBe('endTurn');

    const action: Action = {
      version: ACTION_PROTOCOL_VERSION,
      id: 'a1',
      room_id: 'r1',
      actor_participant_id: 'p1',
      seq: 0,
      payload: { type: 'damage', token_id: 't1', amount: 5 },
    };
    expect(action.payload.type).toBe('damage');
    expect(action.seq).toBe(0);
  });
});
