// Thin fetch wrapper around the backend room/invite API.
//
// The server is authoritative (CLAUDE.md): the client only sends intents and
// renders what the server returns. Base URL is configurable so the SPA can talk
// to a backend on a different origin/port in dev or prod.

import type {
  AddPlayerRequest,
  AddPlayerResponse,
  CharacterResponse,
  CreateRoomRequest,
  CreateRoomResponse,
  PlaceTokenRequest,
  ResolveInviteResponse,
  TokenResponse,
  UpdateTokenRequest,
} from './types';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(
  /\/+$/,
  '',
);

const JSON_HEADERS: Record<string, string> = {
  'Content-Type': 'application/json',
};

/** Error carrying the HTTP status so callers can branch (e.g. 404 to invalid link). */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(API_BASE_URL + path, {
      headers: JSON_HEADERS,
      ...init,
    });
  } catch {
    throw new ApiError(0, 'Could not reach the server. Check your connection.');
  }

  if (!response.ok) {
    const detail = await extractDetail(response);
    throw new ApiError(response.status, detail);
  }

  return (await response.json()) as T;
}

async function extractDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') {
      return body.detail;
    }
  } catch {
    // fall through to a generic message
  }
  return 'Request failed (' + String(response.status) + ').';
}

/** Host action: create a room and receive the host invite link. */
export function createRoom(payload: CreateRoomRequest): Promise<CreateRoomResponse> {
  return request<CreateRoomResponse>('/rooms', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Host action: configure a character in a room and mint that player's invite link.
 *
 * The server creates the character slot (name, max HP, ability scores, portrait),
 * a player participant bound to it, and a fresh invite link returned exactly once.
 */
export function addPlayer(roomId: string, payload: AddPlayerRequest): Promise<AddPlayerResponse> {
  return request<AddPlayerResponse>('/rooms/' + encodeURIComponent(roomId) + '/participants', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/** Resolve an invite token to its room/participant/character binding. */
export function resolveInvite(token: string): Promise<ResolveInviteResponse> {
  return request<ResolveInviteResponse>('/invites/' + encodeURIComponent(token));
}

/**
 * Read a single character's stat block (GET /rooms/{id}/characters/{cid}).
 *
 * Used by the player view to render the player's own character panel after the
 * invite resolves to a character id. An idempotent, reconnect-safe read.
 */
export function getCharacter(roomId: string, characterId: string): Promise<CharacterResponse> {
  return request<CharacterResponse>(
    '/rooms/' + encodeURIComponent(roomId) + '/characters/' + encodeURIComponent(characterId),
  );
}

/**
 * Absolute URL that streams a room's stored map image (GET /rooms/{id}/map).
 *
 * Returned as a plain URL (not fetched here) so it can be used directly as an
 * <img>/Konva image source. The read is idempotent and reconnect-safe.
 */
export function mapImageUrl(roomId: string): string {
  return API_BASE_URL + '/rooms/' + encodeURIComponent(roomId) + '/map';
}

/** Host action: place a token bound to a character on the board grid. */
export function placeToken(roomId: string, payload: PlaceTokenRequest): Promise<TokenResponse> {
  return request<TokenResponse>('/rooms/' + encodeURIComponent(roomId) + '/tokens', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * List every token currently placed in a room.
 *
 * This is what a (re)connecting client uses to draw the current board placement
 * before realtime sync takes over — an idempotent, reconnect-safe read.
 */
export function listTokens(roomId: string): Promise<TokenResponse[]> {
  return request<TokenResponse[]>('/rooms/' + encodeURIComponent(roomId) + '/tokens');
}

/** Host action: reposition/resize an existing token. */
export function updateToken(
  roomId: string,
  tokenId: string,
  payload: UpdateTokenRequest,
): Promise<TokenResponse> {
  return request<TokenResponse>(
    '/rooms/' + encodeURIComponent(roomId) + '/tokens/' + encodeURIComponent(tokenId),
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}
