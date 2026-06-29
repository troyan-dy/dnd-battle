// Initiative / turn-order tracker — an HTML overlay on the board (not a Konva
// layer, since it is chrome rather than world-space content). Shows the round, the
// ordered combatants with the active one highlighted, and an "End turn" button.
// The button only emits the intent; the server validates whose turn it is
// (CLAUDE.md rule 1 + 3) and broadcasts the resulting `endTurn` Action, which
// advances the order for everyone. The button is enabled only when this client may
// end the current turn (host always; a player only on its own active turn) — a UI
// affordance; the server still enforces it.

import type { InitiativeState } from '../api/types';
import { isActiveCharacter } from './initiative';

export interface InitiativeTrackerProps {
  state: InitiativeState;
  /** Host may always end the turn. */
  isHost?: boolean;
  /** The character this (player) client controls, if any. */
  controllableCharacterId?: string | null;
  /** Called when the user ends the current turn. */
  onEndTurn: () => void;
}

export default function InitiativeTracker({
  state,
  isHost = false,
  controllableCharacterId = null,
  onEndTurn,
}: InitiativeTrackerProps) {
  if (state.entries.length === 0) {
    return null;
  }

  const myTurn = isActiveCharacter(state, controllableCharacterId);
  const canEndTurn = isHost || myTurn;
  const entryClass = (active: boolean) =>
    active ? 'initiative-tracker__entry is-active' : 'initiative-tracker__entry';

  return (
    <div className="initiative-tracker" role="group" aria-label="Initiative order">
      <div className="initiative-tracker__header">
        <span className="initiative-tracker__round">Round {state.round}</span>
        <button
          type="button"
          className="initiative-tracker__end-turn"
          onClick={onEndTurn}
          disabled={!canEndTurn}
        >
          End turn
        </button>
      </div>
      <ol className="initiative-tracker__list">
        {state.entries.map((entry, index) => {
          const active = index === state.active_index;
          return (
            <li
              key={entry.id}
              className={entryClass(active)}
              aria-current={active ? 'true' : undefined}
            >
              <span className="initiative-tracker__initiative">{entry.initiative}</span>
              <span className="initiative-tracker__name">{entry.name}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
