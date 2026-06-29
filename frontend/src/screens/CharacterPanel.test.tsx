import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import CharacterPanel from './CharacterPanel';
import { abilityModifier } from './abilityModifier';
import type { CharacterResponse } from '../api/types';

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

const CHARACTER: CharacterResponse = {
  id: 'char-1',
  room_id: 'room-1',
  name: 'Aria',
  max_hp: 24,
  current_hp: 18,
  portrait_url: 'https://example.com/aria.png',
  ability_scores: {
    strength: 8,
    dexterity: 16,
    constitution: 14,
    intelligence: 12,
    wisdom: 10,
    charisma: 18,
  },
  conditions: ['poisoned'],
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe('abilityModifier', () => {
  it('computes signed D&D 2024 modifiers', () => {
    expect(abilityModifier(10)).toBe('+0');
    expect(abilityModifier(16)).toBe('+3');
    expect(abilityModifier(8)).toBe('-1');
    expect(abilityModifier(1)).toBe('-5');
  });
});

describe('CharacterPanel', () => {
  it('fetches and renders the character stat block', async () => {
    const fetchMock = mockFetch(() => jsonResponse(CHARACTER, 200));
    render(<CharacterPanel roomId="room-1" characterId="char-1" />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Aria' })).toBeInTheDocument();
    });

    // Requests the player's own character only.
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/rooms\/room-1\/characters\/char-1$/);

    // HP and its progress bar.
    expect(screen.getByText('HP 18 / 24')).toBeInTheDocument();
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '18');
    expect(bar).toHaveAttribute('aria-valuemax', '24');

    // Ability scores with computed modifiers.
    expect(screen.getByText('DEX')).toBeInTheDocument();
    expect(screen.getByText('16')).toBeInTheDocument();
    expect(screen.getByText('+3')).toBeInTheDocument();
    expect(screen.getByText('-1')).toBeInTheDocument(); // STR 8

    // Active condition.
    expect(screen.getByText('poisoned')).toBeInTheDocument();

    // Portrait uses the provided URL.
    expect(screen.getByRole('img', { name: /aria portrait/i })).toHaveAttribute(
      'src',
      'https://example.com/aria.png',
    );
  });

  it('shows "None" when there are no conditions', async () => {
    mockFetch(() => jsonResponse({ ...CHARACTER, conditions: [] }, 200));
    render(<CharacterPanel roomId="room-1" characterId="char-1" />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Aria' })).toBeInTheDocument();
    });
    expect(screen.getByText('None')).toBeInTheDocument();
  });

  it('shows an error message when the character cannot be loaded', async () => {
    mockFetch(() => jsonResponse({ detail: 'Character not found.' }, 404));
    render(<CharacterPanel roomId="room-1" characterId="missing" />);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/character not found/i);
    });
  });
});
