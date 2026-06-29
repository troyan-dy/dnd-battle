import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, getCharacter, listTokens, placeToken, updateToken } from './client';
import type { CharacterResponse, TokenResponse } from './types';

const token: TokenResponse = {
  id: 'tok-1',
  room_id: 'room-1',
  character_id: 'char-1',
  x: 3,
  y: 5,
  size: 2,
};

function mockFetch(impl: (input: RequestInfo | URL, init?: RequestInit) => Response) {
  const fn = vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
    Promise.resolve(impl(input, init)),
  );
  vi.stubGlobal('fetch', fn);
  return fn;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('token client', () => {
  it('placeToken POSTs the binding + coords to the room tokens endpoint', async () => {
    const fetchMock = mockFetch(() => jsonResponse(token, 201));

    const result = await placeToken('room-1', { character_id: 'char-1', x: 3, y: 5, size: 2 });

    expect(result).toEqual(token);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/rooms\/room-1\/tokens$/);
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      character_id: 'char-1',
      x: 3,
      y: 5,
      size: 2,
    });
  });

  it('listTokens GETs the room tokens (reconnect-safe board hydrate)', async () => {
    const fetchMock = mockFetch(() => jsonResponse([token]));

    const result = await listTokens('room-1');

    expect(result).toEqual([token]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/rooms\/room-1\/tokens$/);
    // A GET has no explicit method override.
    expect(init?.method).toBeUndefined();
  });

  it('updateToken PATCHes only the supplied fields to the token endpoint', async () => {
    const fetchMock = mockFetch(() => jsonResponse({ ...token, x: 4, size: 3 }));

    const result = await updateToken('room-1', 'tok-1', { x: 4, size: 3 });

    expect(result.x).toBe(4);
    expect(result.size).toBe(3);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/rooms\/room-1\/tokens\/tok-1$/);
    expect(init?.method).toBe('PATCH');
    expect(JSON.parse(String(init?.body))).toEqual({ x: 4, size: 3 });
  });

  it('surfaces a 409 conflict as an ApiError carrying the status', async () => {
    mockFetch(() => jsonResponse({ detail: 'Character already has a token.' }, 409));

    await expect(placeToken('room-1', { character_id: 'char-1' })).rejects.toMatchObject({
      status: 409,
    });
    await expect(placeToken('room-1', { character_id: 'char-1' })).rejects.toBeInstanceOf(ApiError);
  });
});

describe('getCharacter', () => {
  const character: CharacterResponse = {
    id: 'char-1',
    room_id: 'room-1',
    name: 'Aria',
    max_hp: 24,
    current_hp: 18,
    portrait_url: null,
    ability_scores: {
      strength: 10,
      dexterity: 16,
      constitution: 14,
      intelligence: 12,
      wisdom: 10,
      charisma: 18,
    },
    conditions: [],
  };

  it('GETs the player character (reconnect-safe read)', async () => {
    const fetchMock = mockFetch(() => jsonResponse(character));

    const result = await getCharacter('room-1', 'char-1');

    expect(result).toEqual(character);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/rooms\/room-1\/characters\/char-1$/);
    expect(init?.method).toBeUndefined();
  });

  it('surfaces a 404 as an ApiError carrying the status', async () => {
    mockFetch(() => jsonResponse({ detail: 'Character not found.' }, 404));

    await expect(getCharacter('room-1', 'missing')).rejects.toMatchObject({ status: 404 });
    await expect(getCharacter('room-1', 'missing')).rejects.toBeInstanceOf(ApiError);
  });
});
