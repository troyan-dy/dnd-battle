import { describe, expect, it } from 'vitest';
import { parseInviteToken } from './router';

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
