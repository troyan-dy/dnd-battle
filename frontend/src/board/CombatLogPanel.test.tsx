import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { AttackResultPayload, CharacterResponse, TokenResponse } from '../api/types';
import CombatLogPanel from './CombatLogPanel';
import type { CombatLogEntry } from './combatLog';
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

function entry(id: string, overrides: Partial<AttackResultPayload> = {}): CombatLogEntry {
  return {
    id,
    payload: {
      type: 'attack',
      attacker_token_id: 'ta',
      target_token_id: 'tb',
      attack_roll: 12,
      attack_bonus: 2,
      attack_total: 14,
      damage: '1d6',
      damage_rolls: [4],
      damage_total: 4,
      ...overrides,
    },
  };
}

describe('CombatLogPanel', () => {
  it('renders nothing when there are no entries', () => {
    const { container } = render(<CombatLogPanel entries={[]} tokens={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders attack lines resolving token names', () => {
    const tokens = [placed('ta', 'ca', 'Goblin'), placed('tb', 'cb', 'Aria')];
    render(<CombatLogPanel entries={[entry('e1')]} tokens={tokens} />);
    expect(screen.getByRole('log')).toHaveTextContent(
      'Goblin attacks Aria: d20 (12) +2 = 14; 1d6 → 4 damage',
    );
  });
});
