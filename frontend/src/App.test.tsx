import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

// JoinScreen renders MapBoard (react-konva), which needs a real canvas jsdom lacks.
// Stub it so App routing can be tested without pulling in konva's node build.
vi.mock('./board/MapBoard', () => ({
  default: ({ roomId }: { roomId: string }) => <div data-testid="map-board">board:{roomId}</div>,
}));

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

  it('renders the character-config screen on a "/host/:roomId/characters" path', () => {
    render(<App pathname="/host/room-1/characters" />);
    expect(screen.getByRole('heading', { name: /configure a character/i })).toBeInTheDocument();
  });
});
