import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import CharacterConfigScreen from './CharacterConfigScreen';
import type { AddPlayerResponse } from '../api/types';

const okResponse: AddPlayerResponse = {
  participant_id: 'p-1',
  character_id: 'char-1',
  role: 'player',
  invite_link: { token: 'secret', url: 'http://localhost:5173/join/secret' },
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

describe('CharacterConfigScreen', () => {
  it('disables submit until a character name and valid HP are present', () => {
    render(<CharacterConfigScreen roomId="room-1" />);
    const button = screen.getByRole('button', { name: /add character/i });
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/character name/i), { target: { value: 'Aria' } });
    expect(button).toBeEnabled();

    // A non-positive HP disables submit again.
    fireEvent.change(screen.getByLabelText(/max hp/i), { target: { value: '0' } });
    expect(button).toBeDisabled();
  });

  it('POSTs name, HP, ability scores and portrait, then shows the invite link', async () => {
    const fetchMock = mockFetch(() => jsonResponse(okResponse, 201));
    render(<CharacterConfigScreen roomId="room-42" />);

    fireEvent.change(screen.getByLabelText(/character name/i), { target: { value: 'Aria' } });
    fireEvent.change(screen.getByLabelText(/max hp/i), { target: { value: '24' } });
    fireEvent.change(screen.getByLabelText('STR'), { target: { value: '16' } });
    fireEvent.change(screen.getByLabelText(/portrait url/i), {
      target: { value: 'https://cdn.example.com/aria.png' },
    });
    fireEvent.click(screen.getByRole('button', { name: /add character/i }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /character added/i })).toBeInTheDocument();
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/rooms\/room-42\/participants$/);
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      character_name: 'Aria',
      max_hp: 24,
      ability_scores: {
        strength: 16,
        dexterity: 10,
        constitution: 10,
        intelligence: 10,
        wisdom: 10,
        charisma: 10,
      },
      portrait_url: 'https://cdn.example.com/aria.png',
      display_name: null,
    });

    const linkField = screen.getByLabelText(/invite link/i) as HTMLInputElement;
    expect(linkField.value).toBe(okResponse.invite_link.url);
  });

  it('shows the server error message on failure and keeps the form usable', async () => {
    mockFetch(() =>
      jsonResponse({ detail: 'portrait_url must be an http:// or https:// URL.' }, 422),
    );
    render(<CharacterConfigScreen roomId="room-1" />);

    fireEvent.change(screen.getByLabelText(/character name/i), { target: { value: 'Aria' } });
    fireEvent.click(screen.getByRole('button', { name: /add character/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/must be an http/i);
    });
    expect(screen.getByRole('button', { name: /add character/i })).toBeEnabled();
  });
});
