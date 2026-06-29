import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { CharacterResponse, TokenResponse } from '../api/types';
import type { PlacedToken } from './tokens';
import HpControls from './HpControls';

function placed(id: string, characterName: string): PlacedToken {
  const token: TokenResponse = {
    id,
    room_id: 'r1',
    character_id: 'char-' + id,
    x: 0,
    y: 0,
    size: 1,
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
    conditions: [],
  };
  return { token, character };
}

describe('HpControls', () => {
  it('renders nothing when there are no tokens', () => {
    const { container } = render(<HpControls tokens={[]} onDamage={vi.fn()} onHeal={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('emits a damage intent for the selected token + amount', () => {
    const onDamage = vi.fn();
    render(<HpControls tokens={[placed('t1', 'Aria')]} onDamage={onDamage} onHeal={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/HP amount/i), { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: 'Damage' }));
    expect(onDamage).toHaveBeenCalledWith('t1', 7);
  });

  it('emits a heal intent for the chosen target', () => {
    const onHeal = vi.fn();
    render(
      <HpControls
        tokens={[placed('t1', 'Aria'), placed('t2', 'Borin')]}
        onDamage={vi.fn()}
        onHeal={onHeal}
      />,
    );
    fireEvent.change(screen.getByLabelText(/target token/i), { target: { value: 't2' } });
    fireEvent.change(screen.getByLabelText(/HP amount/i), { target: { value: '4' } });
    fireEvent.click(screen.getByRole('button', { name: 'Heal' }));
    expect(onHeal).toHaveBeenCalledWith('t2', 4);
  });
});
