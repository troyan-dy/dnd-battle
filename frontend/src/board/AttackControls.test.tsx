import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { CharacterResponse, TokenResponse } from '../api/types';
import AttackControls from './AttackControls';
import type { PlacedToken } from './tokens';

function placed(tokenId: string, characterId: string, name: string): PlacedToken {
  const token = {
    id: tokenId,
    room_id: 'r',
    character_id: characterId,
    x: 0,
    y: 0,
    size: 1,
  } as TokenResponse;
  const character = {
    id: characterId,
    room_id: 'r',
    name,
    max_hp: 10,
    current_hp: 10,
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
  } as CharacterResponse;
  return { token, character };
}

const two = [placed('ta', 'ca', 'Goblin'), placed('tb', 'cb', 'Aria')];

describe('AttackControls', () => {
  it('renders nothing without a controllable attacker', () => {
    const { container } = render(
      <AttackControls tokens={two} controllableTokenIds={[]} onAttack={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing with fewer than two tokens', () => {
    const { container } = render(
      <AttackControls tokens={[two[0]]} controllableTokenIds={['ta']} onAttack={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('emits an attack with the chosen attacker, target, bonus and damage', () => {
    const onAttack = vi.fn();
    render(<AttackControls tokens={two} controllableTokenIds={['ta']} onAttack={onAttack} />);

    fireEvent.change(screen.getByLabelText('Attack bonus'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText('Damage dice'), { target: { value: '1d8' } });
    fireEvent.click(screen.getByRole('button', { name: 'Attack' }));

    // Attacker defaults to the sole controllable token, target to the other token.
    expect(onAttack).toHaveBeenCalledWith('ta', 'tb', 3, '1d8');
  });
});
