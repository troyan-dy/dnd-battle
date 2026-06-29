import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('App routing', () => {
  it('renders the create-room screen on the default path', () => {
    render(<App pathname="/" />);
    expect(screen.getByRole('heading', { name: /create a room/i })).toBeInTheDocument();
  });

  it('renders the join screen on a "/join/:token" path', () => {
    // JoinScreen fires a fetch on mount; stub it so the test stays offline.
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise(() => {})),
    );
    render(<App pathname="/join/abc123" />);
    expect(screen.getByRole('status')).toHaveTextContent(/resolving your invite/i);
  });

  it('renders the character-config screen on a "/rooms/:roomId/characters" path', () => {
    render(<App pathname="/rooms/room-1/characters" />);
    expect(screen.getByRole('heading', { name: /configure a character/i })).toBeInTheDocument();
  });
});
