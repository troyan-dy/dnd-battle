// Realtime board transport (client side) over Socket.IO.
//
// Scope (Phase 4): open a connection to the backend Socket.IO server and join the
// board room by presenting this client's invite TOKEN (the credential it already
// holds from its /join/{token} URL). The server authenticates the token, places
// the client in the room, and pushes the FULL current BoardState (the `boardState`
// event). The server is authoritative (CLAUDE.md); this layer only opens the
// channel, authenticates, and surfaces the snapshot. The versioned Action protocol
// and optimistic moves are later Phase 4 tasks and are not implemented here.

import { io, type Socket } from 'socket.io-client';

import type { BoardState } from '../api/types';

// The realtime server is mounted on the same origin/port as the REST API, so the
// connection URL mirrors the API base. The Socket.IO handshake path is the
// default ('/socket.io'); the backend mounts it there too.
export const SOCKET_BASE_URL = (
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'
).replace(/\/+$/, '');

export const SOCKETIO_PATH = '/socket.io';

/** Server acknowledgement to a "join" intent (mirrors the backend join ack). */
export interface JoinAck {
  ok: boolean;
  roomId?: string;
  participantId?: string;
  role?: 'host' | 'player';
  characterId?: string | null;
  error?: string;
}

/**
 * Emit a "join" intent authenticated by {@link token} and resolve with the ack.
 *
 * Socket.IO delivers the server handler's return value to this callback.
 */
export function joinRoom(socket: Socket, token: string): Promise<JoinAck> {
  return new Promise<JoinAck>((resolve) => {
    socket.emit('join', { token }, (ack: JoinAck) => {
      resolve(ack);
    });
  });
}

/** Options for {@link createBoardSocket}. */
export interface BoardSocketOptions {
  /** Base URL of the realtime server (defaults to {@link SOCKET_BASE_URL}). */
  url?: string;
  /** Called with the full snapshot every time the server pushes `boardState`. */
  onBoardState?: (state: BoardState) => void;
}

/**
 * Open a realtime board connection and (re)join using {@link token} on every connect.
 *
 * Reconnect-safe (CLAUDE.md rule 2): Socket.IO auto-reconnects, and the 'connect'
 * handler re-emits join so a client that drops re-authenticates and the server
 * re-pushes the full BoardState. The caller owns the returned socket and must call
 * `socket.disconnect()` on teardown.
 */
export function createBoardSocket(token: string, options: BoardSocketOptions = {}): Socket {
  const { url = SOCKET_BASE_URL, onBoardState } = options;

  const socket = io(url, {
    path: SOCKETIO_PATH,
    transports: ['websocket', 'polling'],
    autoConnect: true,
  });

  socket.on('connect', () => {
    void joinRoom(socket, token);
  });

  if (onBoardState) {
    socket.on('boardState', (state: BoardState) => {
      onBoardState(state);
    });
  }

  return socket;
}
