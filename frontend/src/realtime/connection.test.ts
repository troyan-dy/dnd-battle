import { afterEach, describe, expect, it, vi } from 'vitest';

import { ACTION_PROTOCOL_VERSION, type Action, type BoardState } from '../api/types';

// A controllable fake Socket: records handlers and emits, lets tests trigger
// lifecycle events and ack callbacks deterministically (no real network).
interface FakeSocket {
  on: ReturnType<typeof vi.fn>;
  emit: ReturnType<typeof vi.fn>;
  disconnect: ReturnType<typeof vi.fn>;
  handlers: Record<string, (...args: unknown[]) => void>;
  fire: (event: string, ...args: unknown[]) => void;
}

function makeFakeSocket(): FakeSocket {
  const handlers: Record<string, (...args: unknown[]) => void> = {};
  return {
    handlers,
    on: vi.fn((event: string, cb: (...args: unknown[]) => void) => {
      handlers[event] = cb;
    }),
    emit: vi.fn(),
    disconnect: vi.fn(),
    fire(event, ...args) {
      handlers[event]?.(...args);
    },
  };
}

const ioMock = vi.fn();

vi.mock('socket.io-client', () => ({
  io: (...args: unknown[]) => ioMock(...args),
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe('createBoardSocket', () => {
  it('connects with the socket.io path and joins with the token on connect', async () => {
    const fake = makeFakeSocket();
    ioMock.mockReturnValue(fake);
    const { createBoardSocket, SOCKETIO_PATH } = await import('./connection');

    const socket = createBoardSocket('secret-token', { url: 'http://api.test' });

    expect(socket).toBe(fake);
    const [url, opts] = ioMock.mock.calls[0] as [string, { path: string }];
    expect(url).toBe('http://api.test');
    expect(opts.path).toBe(SOCKETIO_PATH);

    // No join emitted until the socket actually connects...
    expect(fake.emit).not.toHaveBeenCalled();

    // ...then the connect handler emits the token-authenticated join intent.
    fake.fire('connect');
    expect(fake.emit).toHaveBeenCalledTimes(1);
    const [event, payload] = fake.emit.mock.calls[0] as [string, { token: string }];
    expect(event).toBe('join');
    expect(payload).toEqual({ token: 'secret-token' });
  });

  it('re-joins on every reconnect (reconnect-safe)', async () => {
    const fake = makeFakeSocket();
    ioMock.mockReturnValue(fake);
    const { createBoardSocket } = await import('./connection');

    createBoardSocket('secret-token', { url: 'http://api.test' });

    fake.fire('connect');
    fake.fire('connect');
    expect(fake.emit).toHaveBeenCalledTimes(2);
  });

  it('reports connection status across the lifecycle', async () => {
    const fake = makeFakeSocket();
    fake.emit.mockImplementation((_event: string, _payload: unknown, ack: (a: unknown) => void) => {
      ack({ ok: true, roomId: 'room-1', role: 'player' });
    });
    ioMock.mockReturnValue(fake);
    const { createBoardSocket } = await import('./connection');

    const statuses: string[] = [];
    createBoardSocket('secret-token', {
      url: 'http://api.test',
      onStatusChange: (status) => statuses.push(status),
    });

    // Reported "connecting" synchronously on creation.
    expect(statuses).toEqual(['connecting']);

    // A successful join ack flips to "connected".
    fake.fire('connect');
    await Promise.resolve();
    expect(statuses).toEqual(['connecting', 'connected']);

    // A drop and a failed retry both surface as "reconnecting".
    fake.fire('disconnect', 'transport close');
    fake.fire('connect_error', new Error('boom'));
    expect(statuses).toEqual(['connecting', 'connected', 'reconnecting', 'reconnecting']);
  });

  it('surfaces a join rejection via onError without flipping to connected', async () => {
    const fake = makeFakeSocket();
    fake.emit.mockImplementation((_event: string, _payload: unknown, ack: (a: unknown) => void) => {
      ack({ ok: false, error: 'Invalid or expired invite link.' });
    });
    ioMock.mockReturnValue(fake);
    const { createBoardSocket } = await import('./connection');

    const statuses: string[] = [];
    const errors: string[] = [];
    createBoardSocket('bad-token', {
      url: 'http://api.test',
      onStatusChange: (status) => statuses.push(status),
      onError: (message) => errors.push(message),
    });

    fake.fire('connect');
    await Promise.resolve();

    expect(errors).toEqual(['Invalid or expired invite link.']);
    expect(statuses).toEqual(['connecting']);
  });

  it('surfaces the full BoardState pushed by the server', async () => {
    const fake = makeFakeSocket();
    ioMock.mockReturnValue(fake);
    const { createBoardSocket } = await import('./connection');

    const received: BoardState[] = [];
    createBoardSocket('secret-token', {
      url: 'http://api.test',
      onBoardState: (state) => received.push(state),
    });

    const snapshot: BoardState = {
      room_id: 'room-1',
      tokens: [{ id: 't1', room_id: 'room-1', character_id: 'c1', x: 3, y: 4, size: 1 }],
      characters: [],
      initiative: { active_index: null, round: 1, entries: [] },
    };
    fake.fire('boardState', snapshot);

    expect(received).toEqual([snapshot]);
  });

  it('surfaces each broadcast Action from the server', async () => {
    const fake = makeFakeSocket();
    ioMock.mockReturnValue(fake);
    const { createBoardSocket } = await import('./connection');

    const received: Action[] = [];
    createBoardSocket('secret-token', {
      url: 'http://api.test',
      onAction: (action) => received.push(action),
    });

    const action: Action = {
      version: ACTION_PROTOCOL_VERSION,
      id: 'a1',
      room_id: 'room-1',
      actor_participant_id: 'p1',
      seq: 0,
      payload: { type: 'move', token_id: 't1', x: 7, y: 8 },
    };
    fake.fire('action', action);

    expect(received).toEqual([action]);
  });
});

describe('emitAction', () => {
  it('emits a versioned intent and resolves with the server ack', async () => {
    const fake = makeFakeSocket();
    fake.emit.mockImplementation((_event: string, _intent: unknown, ack: (a: unknown) => void) => {
      ack({ ok: true, actionId: 'a1', seq: 0 });
    });
    const { emitAction } = await import('./connection');

    const ack = await emitAction(fake as never, { type: 'move', token_id: 't1', x: 7, y: 8 });

    expect(ack).toEqual({ ok: true, actionId: 'a1', seq: 0 });
    const [event, intent] = fake.emit.mock.calls[0] as [
      string,
      { version: number; payload: unknown },
    ];
    expect(event).toBe('action');
    expect(intent.version).toBe(ACTION_PROTOCOL_VERSION);
    expect(intent.payload).toEqual({ type: 'move', token_id: 't1', x: 7, y: 8 });
  });
});

describe('joinRoom', () => {
  it('emits a token join intent and resolves with the server ack', async () => {
    const fake = makeFakeSocket();
    fake.emit.mockImplementation((_event: string, _payload: unknown, ack: (a: unknown) => void) => {
      ack({ ok: true, roomId: 'room-3', role: 'player', characterId: 'c1' });
    });
    const { joinRoom } = await import('./connection');

    const ack = await joinRoom(fake as never, 'secret-token');

    expect(ack).toEqual({ ok: true, roomId: 'room-3', role: 'player', characterId: 'c1' });
    const [event, payload] = fake.emit.mock.calls[0] as [string, { token: string }];
    expect(event).toBe('join');
    expect(payload).toEqual({ token: 'secret-token' });
  });
});
