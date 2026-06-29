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

  it('renders mixed entry types (move / damage / endTurn) in order', () => {
    const tokens = [placed('ta', 'ca', 'Goblin'), placed('tb', 'cb', 'Aria')];
    const entries: CombatLogEntry[] = [
      { id: 'm1', payload: { type: 'move', token_id: 'ta', x: 2, y: 3 } },
      { id: 'd1', payload: { type: 'damage', token_id: 'tb', amount: 6 } },
      { id: 't1', payload: { type: 'endTurn' } },
    ];
    render(<CombatLogPanel entries={entries} tokens={tokens} />);
    const items = screen.getAllByRole('listitem');
    expect(items.map((li) => li.textContent)).toEqual([
      'Goblin moves to (2, 3)',
      'Aria takes 6 damage',
      'Turn ended',
    ]);
    expect(items[0]).toHaveAttribute('data-action-type', 'move');
  });
});
