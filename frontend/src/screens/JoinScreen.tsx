// Join screen — reached by opening an invite link ("/join/:token").
//
// On mount it resolves the token against GET /invites/{token}. The server returns
// a uniform 404 for unknown / revoked / expired links (no enumeration oracle), so
// we render a single friendly "invalid or expired" message for any 404. Resolution
// is a pure read and is reconnect-safe: reloading the link always re-resolves.

import { useEffect, useState } from 'react';
import { ApiError, resolveInvite } from '../api/client';
import type { ResolveInviteResponse } from '../api/types';
import MapBoard from '../board/MapBoard';
import CharacterPanel from './CharacterPanel';

type State =
  | { status: 'loading' }
  | { status: 'resolved'; data: ResolveInviteResponse }
  | { status: 'invalid' }
  | { status: 'error'; message: string };

export default function JoinScreen({ token }: { token: string }) {
  const [state, setState] = useState<State>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });

    resolveInvite(token)
      .then((data) => {
        if (!cancelled) {
          setState({ status: 'resolved', data });
        }
      })
      .catch((err: unknown) => {
        if (cancelled) {
          return;
        }
        if (err instanceof ApiError && err.status === 404) {
          setState({ status: 'invalid' });
        } else {
          const message =
            err instanceof ApiError ? err.message : 'Could not resolve this invite link.';
          setState({ status: 'error', message });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  if (state.status === 'loading') {
    return (
      <main className="screen">
        <p role="status">Resolving your invite…</p>
      </main>
    );
  }

  if (state.status === 'invalid') {
    return (
      <main className="screen">
        <h1>Invite not valid</h1>
        <p role="alert">This invite link is invalid or has expired. Ask your DM for a new one.</p>
      </main>
    );
  }

  if (state.status === 'error') {
    return (
      <main className="screen">
        <h1>Something went wrong</h1>
        <p role="alert">{state.message}</p>
      </main>
    );
  }

  // Resolved: render the shared board. A player additionally sees ONLY their own
  // character panel (the server resolves the link to a single character_id); a
  // host sees the board without a single-character panel (the DM controls all
  // tokens, not one slot).
  const { role, room_id, character_id } = state.data;
  const isPlayer = role === 'player' && character_id !== null;

  return (
    <main className="board-view" data-role={role}>
      <div className="board-view__board">
        <MapBoard roomId={room_id} />
      </div>
      {isPlayer ? (
        <CharacterPanel roomId={room_id} characterId={character_id} />
      ) : (
        <aside className="character-panel character-panel--host">
          <h2>Dungeon Master</h2>
          <p className="hint">You control the encounter and every token in this room.</p>
        </aside>
      )}
    </main>
  );
}
