import { act, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PlacedToken } from './tokens';
import type { CharacterResponse, TokenResponse } from '../api/types';

// Capture the props each <Group> is rendered with so tests can invoke the drag
// handlers (react-konva would otherwise need a real canvas + pointer events).
const { groupProps } = vi.hoisted(() => ({
  groupProps: [] as Array<Record<string, unknown>>,
}));

// react-konva needs a real canvas; stand in plain DOM so we can read text/props.
vi.mock('react-konva', () => ({
  Group: (props: { children?: React.ReactNode } & Record<string, unknown>) => {
    groupProps.push(props);
    return <div data-testid="token-group">{props.children as React.ReactNode}</div>;
  },
  Rect: (props: { width?: number; fill?: string }) => (
    <div data-testid="rect" data-width={props.width} data-fill={props.fill} />
  ),
  Text: (props: { text?: string }) => <div data-testid="text">{props.text}</div>,
}));

import TokenLayer from './TokenLayer';

/** The props of the most recently rendered <Group> (the latest token render). */
function lastGroup(): Record<string, unknown> {
  return groupProps[groupProps.length - 1];
}

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
    armor_class: 10,
    resistances: {},
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

  it('does not offer drag handlers for non-controllable tokens', () => {
    groupProps.length = 0;
    render(<TokenLayer tokens={[placed()]} config={grid} />);
    expect(lastGroup().draggable).toBe(false);
    expect(lastGroup().onDragMove).toBeUndefined();
    expect(lastGroup().onDragEnd).toBeUndefined();
  });

  it('shows a live distance readout in feet while a controllable token is dragged', () => {
    groupProps.length = 0;
    // Token at cell (0,0), 50px cells → dragging its top-left to world x=150
    // snaps to cell (3,0): 3 squares × 5 ft = 15 ft (D&D 2024 grid scale).
    render(<TokenLayer tokens={[placed()]} config={grid} canDrag={() => true} onMove={() => {}} />);
    const onDragMove = lastGroup().onDragMove as (e: unknown) => void;
    expect(onDragMove).toBeTypeOf('function');
    act(() => onDragMove({ target: { x: () => 150, y: () => 0 } }));
    const texts = screen.getAllByTestId('text').map((t) => t.textContent);
    expect(texts).toContain('15 ft');
  });

  it('reports the snapped cell and clears the readout on drop', () => {
    groupProps.length = 0;
    const onMove = vi.fn();
    render(<TokenLayer tokens={[placed()]} config={grid} canDrag={() => true} onMove={onMove} />);
    act(() =>
      (lastGroup().onDragMove as (e: unknown) => void)({ target: { x: () => 100, y: () => 50 } }),
    );
    expect(screen.getByText('10 ft')).toBeInTheDocument();

    const node = { x: () => 100, y: () => 50, position: vi.fn() };
    act(() => (lastGroup().onDragEnd as (e: unknown) => void)({ target: node }));
    // Group offset reset, snapped cell reported (Chebyshev of (2,1) = 2 squares).
    expect(node.position).toHaveBeenCalledWith({ x: 0, y: 0 });
    expect(onMove).toHaveBeenCalledWith('t1', { x: 2, y: 1 });
    expect(screen.queryByText('10 ft')).toBeNull();
  });
});
