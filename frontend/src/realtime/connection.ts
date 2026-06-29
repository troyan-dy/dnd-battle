// Realtime board transport (client side) over Socket.IO.
//
// Scope (Phase 4, first task): open a connection to the backend Socket.IO server
// and (re)join the board room. The server is authoritative (CLAUDE.md): this
// layer only opens the channel and announces "I'm viewing room X". Receiving the
// full BoardState on join, the versioned Action protocol and optimistic moves are
// later Phase 4 tasks and are intentionally not implemented here.

import { io, type Socket } from 'socket.io-client';

// The realtime server is mounted on the same origin/port as the REST API, so the
// connection URL mirrors the API base. The Socket.IO handshake path is the
// default ('/socket.io'); the backend mounts it there too.
export const SOCKET_BASE_URL = (
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'
).replace(/\/+$/, '');

export const SOCKETIO_PATH = '/socket.io';

/** Server acknowledgement to a "join" intent. */
export interface JoinAck {
  ok: boolean;
  roomId?: string;
  error?: string;
}

/**
 * Emit a "join" intent for {@link roomId} and resolve with the server's ack.
 *
 * Socket.IO delivers the server handler's return value to this callback.
 */
export function joinRoom(socket: Socket, roomId: string): Promise<JoinAck> {
  return new Promise<JoinAck>((resolve) => {
    socket.emit('join', { roomId }, (ack: JoinAck) => {
      resolve(ack);
    });
  });
}

/**
 * Open a realtime board connection and (re)join {@link roomId} on every connect.
 *
 * Reconnect-safe (CLAUDE.md rule 2): Socket.IO auto-reconnects, and the 'connect'
 * handler re-emits join so a client that drops lands back in its room. The caller
 * owns the returned socket and must call `socket.disconnect()` on teardown.
 */
export function createBoardSocket(roomId: string, url: string = SOCKET_BASE_URL): Socket {
  const socket = io(url, {
    path: SOCKETIO_PATH,
    transports: ['websocket', 'polling'],
    autoConnect: true,
  });

  socket.on('connect', () => {
    void joinRoom(socket, roomId);
  });

  return socket;
}
