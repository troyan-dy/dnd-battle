import { afterEach, describe, expect, it, vi } from 'vitest';

import type { BoardState } from '../api/types';

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
    };
    fake.fire('boardState', snapshot);

    expect(received).toEqual([snapshot]);
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
