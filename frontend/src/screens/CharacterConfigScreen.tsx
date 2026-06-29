// Host "configure character" screen.
//
// The DM fills in a character's name, the six D&D 2024 ability scores, max HP and
// an optional portrait URL, then submits to POST /rooms/{roomId}/participants. The
// server creates the character slot + a player participant and returns that
// player's one-time invite link, which we surface with a copy affordance. The DM
// can keep adding characters one after another.

import { useState } from 'react';
import { ApiError, addPlayer } from '../api/client';
import type { AbilityScores, AddPlayerResponse } from '../api/types';

type Status = 'idle' | 'submitting';

const ABILITIES: { key: keyof AbilityScores; label: string }[] = [
  { key: 'strength', label: 'STR' },
  { key: 'dexterity', label: 'DEX' },
  { key: 'constitution', label: 'CON' },
  { key: 'intelligence', label: 'INT' },
  { key: 'wisdom', label: 'WIS' },
  { key: 'charisma', label: 'CHA' },
];

const ABILITY_MIN = 1;
const ABILITY_MAX = 30;
const DEFAULT_ABILITY = 10;

function abilityInputId(key: keyof AbilityScores): string {
  return 'ability-' + key;
}

function defaultAbilityScores(): AbilityScores {
  return {
    strength: DEFAULT_ABILITY,
    dexterity: DEFAULT_ABILITY,
    constitution: DEFAULT_ABILITY,
    intelligence: DEFAULT_ABILITY,
    wisdom: DEFAULT_ABILITY,
    charisma: DEFAULT_ABILITY,
  };
}

export default function CharacterConfigScreen({ roomId }: { roomId: string }) {
  const [name, setName] = useState('');
  const [maxHp, setMaxHp] = useState('10');
  const [abilities, setAbilities] = useState<AbilityScores>(defaultAbilityScores);
  const [portraitUrl, setPortraitUrl] = useState('');
  const [playerName, setPlayerName] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AddPlayerResponse | null>(null);
  const [copied, setCopied] = useState(false);

  const trimmedName = name.trim();
  const hp = Number(maxHp);
  const hpValid = Number.isInteger(hp) && hp > 0 && hp <= 1000;
  const canSubmit = trimmedName.length > 0 && hpValid && status === 'idle';

  function setAbility(key: keyof AbilityScores, value: string) {
    setAbilities((prev) => ({ ...prev, [key]: Number(value) }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    setStatus('submitting');
    setError(null);
    setCopied(false);
    try {
      const response = await addPlayer(roomId, {
        character_name: trimmedName,
        max_hp: hp,
        ability_scores: abilities,
        portrait_url: portraitUrl.trim() || null,
        display_name: playerName.trim() || null,
      });
      setResult(response);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : 'Something went wrong adding the character.';
      setError(message);
    } finally {
      setStatus('idle');
    }
  }

  async function handleCopy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  function addAnother() {
    setResult(null);
    setName('');
    setMaxHp('10');
    setAbilities(defaultAbilityScores());
    setPortraitUrl('');
    setPlayerName('');
    setError(null);
    setCopied(false);
  }

  if (result) {
    const inviteUrl = result.invite_link.url;
    return (
      <main className="screen">
        <h1>Character added</h1>
        <p>Share this one-time invite link with the player — it binds them to this character:</p>
        <div className="link-row">
          <input
            id="player-link"
            type="text"
            readOnly
            aria-label="Player invite link"
            value={inviteUrl}
          />
          <button type="button" onClick={() => void handleCopy(inviteUrl)}>
            {copied ? 'Copied!' : 'Copy'}
          </button>
        </div>
        <p className="hint">This link is shown only once. You can add more characters below.</p>
        <button type="button" onClick={addAnother}>
          Add another character
        </button>
      </main>
    );
  }

  return (
    <main className="screen">
      <h1>Configure a character</h1>
      <p>Set up a character and hand the player their personal invite link.</p>
      <form onSubmit={(event) => void handleSubmit(event)} noValidate>
        <label htmlFor="char-name">Character name</label>
        <input
          id="char-name"
          type="text"
          value={name}
          maxLength={120}
          required
          autoFocus
          onChange={(event) => setName(event.target.value)}
          placeholder="Aria Brightwood"
        />

        <label htmlFor="max-hp">Max HP</label>
        <input
          id="max-hp"
          type="number"
          min={1}
          max={1000}
          value={maxHp}
          required
          onChange={(event) => setMaxHp(event.target.value)}
        />

        <fieldset className="ability-grid">
          <legend>Ability scores</legend>
          {ABILITIES.map((ability) => (
            <label key={ability.key} htmlFor={abilityInputId(ability.key)}>
              {ability.label}
              <input
                id={abilityInputId(ability.key)}
                type="number"
                min={ABILITY_MIN}
                max={ABILITY_MAX}
                value={abilities[ability.key]}
                onChange={(event) => setAbility(ability.key, event.target.value)}
              />
            </label>
          ))}
        </fieldset>

        <label htmlFor="portrait-url">Portrait URL (optional)</label>
        <input
          id="portrait-url"
          type="url"
          value={portraitUrl}
          maxLength={2048}
          onChange={(event) => setPortraitUrl(event.target.value)}
          placeholder="https://example.com/portrait.png"
        />

        <label htmlFor="player-name">Player name (optional)</label>
        <input
          id="player-name"
          type="text"
          value={playerName}
          maxLength={120}
          onChange={(event) => setPlayerName(event.target.value)}
          placeholder="Jordan"
        />

        {error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : null}

        <button type="submit" disabled={!canSubmit}>
          {status === 'submitting' ? 'Adding…' : 'Add character'}
        </button>
      </form>
    </main>
  );
}
