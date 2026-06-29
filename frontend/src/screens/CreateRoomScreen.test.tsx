import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import CreateRoomScreen from './CreateRoomScreen';
import type { CreateRoomResponse } from '../api/types';

const okResponse: CreateRoomResponse = {
  room: { id: 'room-1', name: 'The Sunless Citadel', status: 'lobby' },
  host_participant_id: 'host-1',
  host_role: 'host',
  host_link: { token: 'secret', url: 'http://localhost:5173/join/secret' },
};

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

describe('CreateRoomScreen', () => {
  it('disables submit until a room name is entered', () => {
    render(<CreateRoomScreen />);
    const button = screen.getByRole('button', { name: /create room/i });
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/room name/i), { target: { value: 'Goblins' } });
    expect(button).toBeEnabled();
  });

  it('POSTs to /rooms and shows the host link on success', async () => {
    const fetchMock = mockFetch(() => jsonResponse(okResponse, 201));
    render(<CreateRoomScreen />);

    fireEvent.change(screen.getByLabelText(/room name/i), {
      target: { value: 'The Sunless Citadel' },
    });
    fireEvent.change(screen.getByLabelText(/your name/i), { target: { value: 'DM Bob' } });
    fireEvent.click(screen.getByRole('button', { name: /create room/i }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /room created/i })).toBeInTheDocument();
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/rooms$/);
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      name: 'The Sunless Citadel',
      host_display_name: 'DM Bob',
    });

    const linkField = screen.getByLabelText(/your host link/i) as HTMLInputElement;
    expect(linkField.value).toBe(okResponse.host_link.url);
  });

  it('shows the server error message on failure', async () => {
    mockFetch(() => jsonResponse({ detail: 'Name too long.' }, 422));
    render(<CreateRoomScreen />);

    fireEvent.change(screen.getByLabelText(/room name/i), { target: { value: 'X' } });
    fireEvent.click(screen.getByRole('button', { name: /create room/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/name too long/i);
    });
    // form is still visible / usable
    expect(screen.getByRole('button', { name: /create room/i })).toBeEnabled();
  });
});
