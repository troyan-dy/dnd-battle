// Host-only affordance to apply damage / healing to a token (Phase 5).
//
// The host picks a target token (by its character's name), enters an amount, and
// clicks Damage or Heal. We only emit the intent — the server is authoritative
// (CLAUDE.md rule 1): it validates, applies the durable HP change (clamped), and
// broadcasts the resulting Action to everyone, which is what updates the rendered
// HP. No optimistic local change is made here (HP is not latency-sensitive like
// movement, and this keeps the client strictly reconciled to the server).

import { useState } from 'react';
import type { PlacedToken } from './tokens';

export interface HpControlsProps {
  /** Tokens currently on the board (joined with their character display data). */
  tokens: PlacedToken[];
  /** Emit a damage intent for the given token. */
  onDamage: (tokenId: string, amount: number) => void;
  /** Emit a heal intent for the given token. */
  onHeal: (tokenId: string, amount: number) => void;
}

const MIN_AMOUNT = 1;

export default function HpControls({ tokens, onDamage, onHeal }: HpControlsProps) {
  const [targetId, setTargetId] = useState('');
  const [amount, setAmount] = useState(1);

  if (tokens.length === 0) {
    return null;
  }

  // Resolve the selected token: fall back to the first when none chosen yet or
  // the previous selection has left the board.
  const selected = tokens.find((t) => t.token.id === targetId) ?? tokens[0];
  const valid = amount >= MIN_AMOUNT;

  return (
    <div className="map-board__hp-controls" role="group" aria-label="Apply damage or healing">
      <label>
        Target
        <select
          value={selected.token.id}
          onChange={(e) => setTargetId(e.target.value)}
          aria-label="Target token"
        >
          {tokens.map(({ token, character }) => (
            <option key={token.id} value={token.id}>
              {character.name} ({character.current_hp}/{character.max_hp})
            </option>
          ))}
        </select>
      </label>
      <label>
        Amount
        <input
          type="number"
          min={MIN_AMOUNT}
          step={1}
          value={amount}
          aria-label="HP amount"
          onChange={(e) => setAmount(Math.max(MIN_AMOUNT, Math.floor(Number(e.target.value) || 0)))}
        />
      </label>
      <button
        type="button"
        className="map-board__hp-damage"
        disabled={!valid}
        onClick={() => onDamage(selected.token.id, amount)}
      >
        Damage
      </button>
      <button
        type="button"
        className="map-board__hp-heal"
        disabled={!valid}
        onClick={() => onHeal(selected.token.id, amount)}
      >
        Heal
      </button>
    </div>
  );
}
