import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import JoinScreen from './JoinScreen';
import type { ResolveInviteResponse } from '../api/types';

// Stub the heavy board (Konva) and the self-fetching panel so these tests focus
// on JoinScreen's composition: which children it renders for each role.
vi.mock('../board/MapBoard', () => ({
  default: ({ roomId }: { roomId: string }) => <div data-testid="map-board">board:{roomId}</div>,
}));
vi.mock('./CharacterPanel', () => ({
  default: ({ roomId, characterId }: { roomId: string; characterId: string }) => (
    <div data-testid="character-panel">
      panel:{roomId}:{characterId}
    </div>
  ),
}));

function mockFetch(impl: () => Response | Promise<Response>) {
  const fn = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) => Promise.resolve(impl()));
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

describe('JoinScreen', () => {
  it('shows the board and ONLY the player character panel for a player link', async () => {
    const data: ResolveInviteResponse = {
      room_id: 'room-1',
      participant_id: 'p-1',
      role: 'player',
      character_id: 'char-1',
    };
    const fetchMock = mockFetch(() => jsonResponse(data, 200));
    render(<JoinScreen token="abc" />);

    await waitFor(() => {
      expect(screen.getByTestId('character-panel')).toBeInTheDocument();
    });
    // Board hydrated for the resolved room; panel bound to the resolved character.
    expect(screen.getByTestId('map-board')).toHaveTextContent('board:room-1');
    expect(screen.getByTestId('character-panel')).toHaveTextContent('panel:room-1:char-1');
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/invites\/abc$/);
  });

  it('shows the board + DM panel (no single-character panel) for a host link', async () => {
    const data: ResolveInviteResponse = {
      room_id: 'room-1',
      participant_id: 'host-1',
      role: 'host',
      character_id: null,
    };
    mockFetch(() => jsonResponse(data, 200));
    render(<JoinScreen token="abc" />);

    await waitFor(() => {
      expect(screen.getByText(/dungeon master/i)).toBeInTheDocument();
    });
    expect(screen.getByTestId('map-board')).toHaveTextContent('board:room-1');
    expect(screen.queryByTestId('character-panel')).not.toBeInTheDocument();
  });

  it('shows a friendly invalid message on a 404', async () => {
    mockFetch(() => jsonResponse({ detail: 'Invalid or expired invite link.' }, 404));
    render(<JoinScreen token="bad" />);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/invalid or has expired/i);
    });
  });

  it('shows a generic error on a network failure', async () => {
    mockFetch(() => Promise.reject(new Error('boom')));
    render(<JoinScreen token="abc" />);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/could not reach the server/i);
    });
  });
});
