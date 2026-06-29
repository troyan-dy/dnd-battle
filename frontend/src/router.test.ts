import { describe, expect, it } from 'vitest';
import { parseInviteToken, parseRoomCharactersRoomId } from './router';

describe('parseInviteToken', () => {
  it('extracts the token from a /join/:token path', () => {
    expect(parseInviteToken('/join/abc123')).toBe('abc123');
  });

  it('tolerates a trailing slash', () => {
    expect(parseInviteToken('/join/abc123/')).toBe('abc123');
  });

  it('decodes percent-encoded tokens', () => {
    expect(parseInviteToken('/join/a%2Fb')).toBe('a/b');
  });

  it('returns null for the root path', () => {
    expect(parseInviteToken('/')).toBeNull();
  });

  it('returns null for unrelated paths', () => {
    expect(parseInviteToken('/rooms/123')).toBeNull();
  });

  it('returns null for /join with no token', () => {
    expect(parseInviteToken('/join/')).toBeNull();
  });
});

describe('parseRoomCharactersRoomId', () => {
  it('extracts the room id from a /rooms/:roomId/characters path', () => {
    expect(parseRoomCharactersRoomId('/rooms/room-1/characters')).toBe('room-1');
  });

  it('tolerates a trailing slash', () => {
    expect(parseRoomCharactersRoomId('/rooms/room-1/characters/')).toBe('room-1');
  });

  it('returns null for a bare /rooms/:id path', () => {
    expect(parseRoomCharactersRoomId('/rooms/room-1')).toBeNull();
  });

  it('returns null for the root path', () => {
    expect(parseRoomCharactersRoomId('/')).toBeNull();
  });
});
