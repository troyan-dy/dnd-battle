// Host-only fog-of-war affordance: hide or reveal a token (Phase 7).
//
// The host picks a token (by its character's name) and toggles its visibility.
// We only emit the intent — the server is authoritative (CLAUDE.md rule 1) and
// HOST-ONLY (rule 3): it flips the durable `Token.hidden` flag and pushes a fresh
// role-filtered BoardState to each side (players never receive a hidden token).
// No optimistic local change is made; the host's view reconciles to the server's
// next BoardState push.

import { useState } from 'react';
import type { PlacedToken } from './tokens';

export interface VisibilityControlsProps {
  /** Tokens currently on the board (joined with their character display data). */
  tokens: PlacedToken[];
  /** Emit a setVisibility intent for the given token. */
  onSetVisibility: (tokenId: string, hidden: boolean) => void;
}

export default function VisibilityControls({ tokens, onSetVisibility }: VisibilityControlsProps) {
  const [targetId, setTargetId] = useState('');

  if (tokens.length === 0) {
    return null;
  }

  // Resolve the selected token: fall back to the first when none chosen yet or
  // the previous selection has left the board.
  const selected = tokens.find((t) => t.token.id === targetId) ?? tokens[0];
  const isHidden = selected.token.hidden ?? false;

  return (
    <div
      className="map-board__visibility-controls"
      role="group"
      aria-label="Hide or reveal a token"
    >
      <label>
        Token
        <select
          value={selected.token.id}
          onChange={(e) => setTargetId(e.target.value)}
          aria-label="Token to hide or reveal"
        >
          {tokens.map(({ token, character }) => (
            <option key={token.id} value={token.id}>
              {character.name}
              {(token.hidden ?? false) ? ' (hidden)' : ''}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="map-board__visibility-toggle"
        aria-pressed={isHidden}
        onClick={() => onSetVisibility(selected.token.id, !isHidden)}
      >
        {isHidden ? 'Reveal' : 'Hide'}
      </button>
    </div>
  );
}
