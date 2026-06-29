// Affordance to make an attack (Phase 5): pick an attacker token you control, a
// target, a to-hit bonus and damage dice, then "Attack". We only emit the intent —
// the server is authoritative (CLAUDE.md rule 1): it rolls the d20 + damage, applies
// the result, and broadcasts an `attack` Action that updates HP and the combat log
// for everyone. Available to the host (any token) and to a player for their own
// token(s); the server still enforces who may attack with which token.

import { useState } from 'react';
import type { PlacedToken } from './tokens';

export interface AttackControlsProps {
  /** Tokens currently on the board (joined with their character display data). */
  tokens: PlacedToken[];
  /** Token ids this client may attack WITH (host: all; player: its own token). */
  controllableTokenIds: string[];
  /** Emit an attack intent. */
  onAttack: (attackerId: string, targetId: string, bonus: number, damage: string) => void;
}

const DEFAULT_DAMAGE = '1d6';

export default function AttackControls({
  tokens,
  controllableTokenIds,
  onAttack,
}: AttackControlsProps) {
  const [attackerId, setAttackerId] = useState('');
  const [targetId, setTargetId] = useState('');
  const [bonus, setBonus] = useState(0);
  const [damage, setDamage] = useState(DEFAULT_DAMAGE);

  const attackers = tokens.filter((t) => controllableTokenIds.includes(t.token.id));
  // Need at least one attacker we control and a different token to target.
  if (attackers.length === 0 || tokens.length < 2) {
    return null;
  }

  const attacker = attackers.find((t) => t.token.id === attackerId) ?? attackers[0];
  const targets = tokens.filter((t) => t.token.id !== attacker.token.id);
  const target = targets.find((t) => t.token.id === targetId) ?? targets[0];
  const valid = target != null && damage.trim().length > 0;

  return (
    <div className="map-board__attack-controls" role="group" aria-label="Make an attack">
      <label>
        Attacker
        <select
          value={attacker.token.id}
          onChange={(e) => setAttackerId(e.target.value)}
          aria-label="Attacker token"
        >
          {attackers.map(({ token, character }) => (
            <option key={token.id} value={token.id}>
              {character.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Target
        <select
          value={target?.token.id ?? ''}
          onChange={(e) => setTargetId(e.target.value)}
          aria-label="Target token"
        >
          {targets.map(({ token, character }) => (
            <option key={token.id} value={token.id}>
              {character.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Hit
        <input
          type="number"
          step={1}
          value={bonus}
          aria-label="Attack bonus"
          onChange={(e) => setBonus(Math.trunc(Number(e.target.value) || 0))}
        />
      </label>
      <label>
        Damage
        <input
          type="text"
          value={damage}
          aria-label="Damage dice"
          onChange={(e) => setDamage(e.target.value)}
        />
      </label>
      <button
        type="button"
        className="map-board__attack-button"
        disabled={!valid}
        onClick={() => {
          if (target) {
            onAttack(attacker.token.id, target.token.id, bonus, damage.trim());
          }
        }}
      >
        Attack
      </button>
    </div>
  );
}
