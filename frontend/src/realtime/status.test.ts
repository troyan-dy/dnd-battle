import { describe, expect, it } from 'vitest';

import { appendNotice, connectionBanner, dismissNotice, MAX_NOTICES, type Notice } from './status';

describe('connectionBanner', () => {
  it('shows no banner while connected', () => {
    expect(connectionBanner('connected')).toBeNull();
  });

  it('shows an info banner while connecting', () => {
    expect(connectionBanner('connecting')).toEqual({
      message: 'Connecting to the board…',
      tone: 'info',
    });
  });

  it('shows a warning banner while reconnecting', () => {
    const banner = connectionBanner('reconnecting');
    expect(banner?.tone).toBe('warning');
    expect(banner?.message).toMatch(/reconnect/i);
  });
});

describe('appendNotice', () => {
  it('appends without mutating the input', () => {
    const before: Notice[] = [{ id: 1, message: 'a' }];
    const after = appendNotice(before, { id: 2, message: 'b' });
    expect(after).toEqual([
      { id: 1, message: 'a' },
      { id: 2, message: 'b' },
    ]);
    expect(before).toEqual([{ id: 1, message: 'a' }]);
  });

  it('caps at MAX_NOTICES, dropping the oldest', () => {
    let notices: Notice[] = [];
    for (let i = 0; i < MAX_NOTICES + 2; i += 1) {
      notices = appendNotice(notices, { id: i, message: 'm' + i });
    }
    expect(notices).toHaveLength(MAX_NOTICES);
    // Oldest two (ids 0,1) were dropped; newest kept.
    expect(notices[0]?.id).toBe(2);
    expect(notices[notices.length - 1]?.id).toBe(MAX_NOTICES + 1);
  });
});

describe('dismissNotice', () => {
  it('removes only the matching notice', () => {
    const notices: Notice[] = [
      { id: 1, message: 'a' },
      { id: 2, message: 'b' },
      { id: 3, message: 'c' },
    ];
    expect(dismissNotice(notices, 2)).toEqual([
      { id: 1, message: 'a' },
      { id: 3, message: 'c' },
    ]);
  });

  it('is a no-op when the id is absent', () => {
    const notices: Notice[] = [{ id: 1, message: 'a' }];
    expect(dismissNotice(notices, 99)).toEqual(notices);
  });
});
