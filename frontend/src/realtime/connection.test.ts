import { afterEach, describe, expect, it, vi } from 'vitest';

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
  it('connects with the socket.io path and joins on connect', async () => {
    const fake = makeFakeSocket();
    ioMock.mockReturnValue(fake);
    const { createBoardSocket, SOCKETIO_PATH } = await import('./connection');

    const socket = createBoardSocket('room-9', 'http://api.test');

    expect(socket).toBe(fake);
    const [url, opts] = ioMock.mock.calls[0] as [string, { path: string }];
    expect(url).toBe('http://api.test');
    expect(opts.path).toBe(SOCKETIO_PATH);

    // No join emitted until the socket actually connects...
    expect(fake.emit).not.toHaveBeenCalled();

    // ...then the connect handler emits the join intent for this room.
    fake.fire('connect');
    expect(fake.emit).toHaveBeenCalledTimes(1);
    const [event, payload] = fake.emit.mock.calls[0] as [string, { roomId: string }];
    expect(event).toBe('join');
    expect(payload).toEqual({ roomId: 'room-9' });
  });

  it('re-joins on every reconnect (reconnect-safe)', async () => {
    const fake = makeFakeSocket();
    ioMock.mockReturnValue(fake);
    const { createBoardSocket } = await import('./connection');

    createBoardSocket('room-9', 'http://api.test');

    fake.fire('connect');
    fake.fire('connect');
    expect(fake.emit).toHaveBeenCalledTimes(2);
  });
});

describe('joinRoom', () => {
  it('emits a join intent and resolves with the server ack', async () => {
    const fake = makeFakeSocket();
    fake.emit.mockImplementation((_event: string, _payload: unknown, ack: (a: unknown) => void) => {
      ack({ ok: true, roomId: 'room-3' });
    });
    const { joinRoom } = await import('./connection');

    const ack = await joinRoom(fake as never, 'room-3');

    expect(ack).toEqual({ ok: true, roomId: 'room-3' });
    const [event, payload] = fake.emit.mock.calls[0] as [string, { roomId: string }];
    expect(event).toBe('join');
    expect(payload).toEqual({ roomId: 'room-3' });
  });
});
