// Thin fetch wrapper around the backend room/invite API.
//
// The server is authoritative (CLAUDE.md): the client only sends intents and
// renders what the server returns. Base URL is configurable so the SPA can talk
// to a backend on a different origin/port in dev or prod.

import type { CreateRoomRequest, CreateRoomResponse, ResolveInviteResponse } from './types';

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

/** Resolve an invite token to its room/participant/character binding. */
export function resolveInvite(token: string): Promise<ResolveInviteResponse> {
  return request<ResolveInviteResponse>('/invites/' + encodeURIComponent(token));
}
