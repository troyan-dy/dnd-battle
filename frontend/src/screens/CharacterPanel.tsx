// The player's own character panel, shown beside the board in the player view.
//
// Given the resolved (roomId, characterId) it fetches the character's stat block
// (GET /rooms/{id}/characters/{cid}) and renders name, portrait, HP, the six
// D&D 2024 ability scores with modifiers, and any active conditions. This is the
// ONLY character a player sees - the server returns just their bound character.
// The read is idempotent and reconnect-safe: reloading the link re-fetches.

import { useEffect, useState } from 'react';
import { ApiError, getCharacter } from '../api/client';
import type { AbilityScores, CharacterResponse } from '../api/types';
import { abilityModifier } from './abilityModifier';

type State =
  | { status: 'loading' }
  | { status: 'loaded'; character: CharacterResponse }
  | { status: 'error'; message: string };

const ABILITY_ORDER: { key: keyof AbilityScores; label: string }[] = [
  { key: 'strength', label: 'STR' },
  { key: 'dexterity', label: 'DEX' },
  { key: 'constitution', label: 'CON' },
  { key: 'intelligence', label: 'INT' },
  { key: 'wisdom', label: 'WIS' },
  { key: 'charisma', label: 'CHA' },
];

export default function CharacterPanel({
  roomId,
  characterId,
}: {
  roomId: string;
  characterId: string;
}) {
  const [state, setState] = useState<State>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });

    getCharacter(roomId, characterId)
      .then((character) => {
        if (!cancelled) {
          setState({ status: 'loaded', character });
        }
      })
      .catch((err: unknown) => {
        if (cancelled) {
          return;
        }
        const message = err instanceof ApiError ? err.message : 'Could not load your character.';
        setState({ status: 'error', message });
      });

    return () => {
      cancelled = true;
    };
  }, [roomId, characterId]);

  if (state.status === 'loading') {
    return (
      <aside className="character-panel">
        <p role="status">Loading your character…</p>
      </aside>
    );
  }

  if (state.status === 'error') {
    return (
      <aside className="character-panel">
        <p role="alert">{state.message}</p>
      </aside>
    );
  }

  const c = state.character;
  const hpPct = c.max_hp > 0 ? Math.max(0, Math.min(100, (c.current_hp / c.max_hp) * 100)) : 0;

  return (
    <aside className="character-panel">
      {c.portrait_url && (
        <img
          className="character-panel__portrait"
          src={c.portrait_url}
          alt={c.name + ' portrait'}
        />
      )}
      <h2 className="character-panel__name">{c.name}</h2>

      <div className="character-panel__hp">
        <span className="character-panel__hp-label">
          HP {c.current_hp} / {c.max_hp}
        </span>
        <div
          className="character-panel__hp-bar"
          role="progressbar"
          aria-valuenow={c.current_hp}
          aria-valuemin={0}
          aria-valuemax={c.max_hp}
        >
          <div className="character-panel__hp-fill" style={{ width: hpPct + '%' }} />
        </div>
      </div>

      <ul className="character-panel__abilities">
        {ABILITY_ORDER.map(({ key, label }) => (
          <li key={key} className="character-panel__ability">
            <span className="character-panel__ability-label">{label}</span>
            <span className="character-panel__ability-score">{c.ability_scores[key]}</span>
            <span className="character-panel__ability-mod">
              {abilityModifier(c.ability_scores[key])}
            </span>
          </li>
        ))}
      </ul>

      <div className="character-panel__conditions">
        <h3>Conditions</h3>
        {c.conditions.length === 0 ? (
          <p className="hint">None</p>
        ) : (
          <ul>
            {c.conditions.map((cond) => (
              <li key={cond}>{cond}</li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
