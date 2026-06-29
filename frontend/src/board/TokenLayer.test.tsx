import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PlacedToken } from './tokens';
import type { CharacterResponse, TokenResponse } from '../api/types';

// react-konva needs a real canvas; stand in plain DOM so we can read text/props.
vi.mock('react-konva', () => ({
  Group: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="token-group">{children}</div>
  ),
  Rect: (props: { width?: number; fill?: string }) => (
    <div data-testid="rect" data-width={props.width} data-fill={props.fill} />
  ),
  Text: (props: { text?: string }) => <div data-testid="text">{props.text}</div>,
}));

import TokenLayer from './TokenLayer';

const grid = { cellSize: 50, offsetX: 0, offsetY: 0 };

function placed(
  over: Partial<CharacterResponse> = {},
  tokenOver: Partial<TokenResponse> = {},
): PlacedToken {
  const character: CharacterResponse = {
    id: 'c1',
    room_id: 'r1',
    name: 'Goblin',
    max_hp: 12,
    current_hp: 9,
    portrait_url: null,
    ability_scores: {
      strength: 10,
      dexterity: 10,
      constitution: 10,
      intelligence: 10,
      wisdom: 10,
      charisma: 10,
    },
    conditions: [],
    ...over,
  };
  const token: TokenResponse = {
    id: 't1',
    room_id: 'r1',
    character_id: 'c1',
    x: 0,
    y: 0,
    size: 1,
    ...tokenOver,
  };
  return { token, character };
}

describe('TokenLayer', () => {
  it('renders one group per token with name and HP text', () => {
    render(<TokenLayer tokens={[placed()]} config={grid} />);
    expect(screen.getAllByTestId('token-group')).toHaveLength(1);
    const texts = screen.getAllByTestId('text').map((t) => t.textContent);
    expect(texts).toContain('Goblin');
    expect(texts).toContain('9/12');
  });

  it('renders condition names when present', () => {
    render(<TokenLayer tokens={[placed({ conditions: ['Prone', 'Poisoned'] })]} config={grid} />);
    const texts = screen.getAllByTestId('text').map((t) => t.textContent);
    expect(texts).toContain('Prone, Poisoned');
  });

  it('omits the conditions line when there are none', () => {
    render(<TokenLayer tokens={[placed({ conditions: [] })]} config={grid} />);
    const texts = screen.getAllByTestId('text').map((t) => t.textContent);
    // Only name + HP text, no empty conditions line.
    expect(texts).toEqual(['Goblin', '9/12']);
  });

  it('renders nothing when there are no tokens', () => {
    render(<TokenLayer tokens={[]} config={grid} />);
    expect(screen.queryByTestId('token-group')).toBeNull();
  });
});
