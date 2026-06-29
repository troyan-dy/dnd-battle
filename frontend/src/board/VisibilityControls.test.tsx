import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { CharacterResponse, TokenResponse } from '../api/types';
import type { PlacedToken } from './tokens';
import VisibilityControls from './VisibilityControls';

function placed(id: string, characterName: string, hidden = false): PlacedToken {
  const token: TokenResponse = {
    id,
    room_id: 'r1',
    character_id: 'char-' + id,
    x: 0,
    y: 0,
    size: 1,
    hidden,
  };
  const character: CharacterResponse = {
    id: 'char-' + id,
    room_id: 'r1',
    name: characterName,
    max_hp: 30,
    current_hp: 20,
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
  };
  return { token, character };
}

describe('VisibilityControls', () => {
  it('renders nothing when there are no tokens', () => {
    const { container } = render(<VisibilityControls tokens={[]} onSetVisibility={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('hides a visible token: emits setVisibility hidden=true', () => {
    const onSetVisibility = vi.fn();
    render(
      <VisibilityControls tokens={[placed('t1', 'Goblin')]} onSetVisibility={onSetVisibility} />,
    );
    // A visible token offers a "Hide" button.
    fireEvent.click(screen.getByRole('button', { name: 'Hide' }));
    expect(onSetVisibility).toHaveBeenCalledWith('t1', true);
  });

  it('reveals a hidden token: emits setVisibility hidden=false', () => {
    const onSetVisibility = vi.fn();
    render(
      <VisibilityControls
        tokens={[placed('t1', 'Goblin', true)]}
        onSetVisibility={onSetVisibility}
      />,
    );
    const toggle = screen.getByRole('button', { name: 'Reveal' });
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(toggle);
    expect(onSetVisibility).toHaveBeenCalledWith('t1', false);
  });

  it('targets the chosen token', () => {
    const onSetVisibility = vi.fn();
    render(
      <VisibilityControls
        tokens={[placed('t1', 'Aria'), placed('t2', 'Goblin')]}
        onSetVisibility={onSetVisibility}
      />,
    );
    fireEvent.change(screen.getByLabelText(/token to hide or reveal/i), {
      target: { value: 't2' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Hide' }));
    expect(onSetVisibility).toHaveBeenCalledWith('t2', true);
  });
});
