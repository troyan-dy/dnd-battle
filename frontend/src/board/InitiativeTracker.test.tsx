import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import InitiativeTracker from './InitiativeTracker';
import type { InitiativeState } from '../api/types';

function makeState(activeIndex: number | null): InitiativeState {
  return {
    active_index: activeIndex,
    round: 2,
    entries: [
      { id: 'e0', character_id: 'c0', name: 'Aria', initiative: 18, order_index: 0 },
      { id: 'e1', character_id: null, name: 'Goblin', initiative: 10, order_index: 1 },
    ],
  };
}

describe('InitiativeTracker', () => {
  it('renders nothing when there are no combatants', () => {
    const { container } = render(
      <InitiativeTracker
        state={{ active_index: null, round: 1, entries: [] }}
        onEndTurn={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('shows the round, the combatants, and marks the active one', () => {
    render(<InitiativeTracker state={makeState(0)} isHost onEndTurn={() => {}} />);
    expect(screen.getByText('Round 2')).toBeInTheDocument();
    expect(screen.getByText('Aria')).toBeInTheDocument();
    expect(screen.getByText('Goblin')).toBeInTheDocument();
    const active = screen.getByText('Aria').closest('li');
    expect(active).toHaveAttribute('aria-current', 'true');
  });

  it('lets the host end the turn', () => {
    const onEndTurn = vi.fn();
    render(<InitiativeTracker state={makeState(1)} isHost onEndTurn={onEndTurn} />);
    const btn = screen.getByRole('button', { name: 'End turn' });
    expect(btn).toBeEnabled();
    fireEvent.click(btn);
    expect(onEndTurn).toHaveBeenCalledTimes(1);
  });

  it('enables End turn for the player only on their own active turn', () => {
    const { rerender } = render(
      <InitiativeTracker state={makeState(0)} controllableCharacterId="c0" onEndTurn={() => {}} />,
    );
    expect(screen.getByRole('button', { name: 'End turn' })).toBeEnabled();

    // Not this player's turn (seat 1 is the NPC Goblin) -> disabled.
    rerender(
      <InitiativeTracker state={makeState(1)} controllableCharacterId="c0" onEndTurn={() => {}} />,
    );
    expect(screen.getByRole('button', { name: 'End turn' })).toBeDisabled();
  });
});
