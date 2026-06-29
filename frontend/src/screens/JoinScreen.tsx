// Join screen — reached by opening an invite link ("/join/:token").
//
// On mount it resolves the token against GET /invites/{token}. The server returns
// a uniform 404 for unknown / revoked / expired links (no enumeration oracle), so
// we render a single friendly "invalid or expired" message for any 404. Resolution
// is a pure read and is reconnect-safe: reloading the link always re-resolves.

import { useEffect, useState } from 'react';
import { ApiError, resolveInvite } from '../api/client';
import type { ResolveInviteResponse } from '../api/types';

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

  const { role, room_id, character_id } = state.data;
  return (
    <main className="screen">
      <h1>You&apos;re in</h1>
      <p>
        Joined room <code>{room_id}</code> as <strong>{role}</strong>.
      </p>
      {role === 'player' && character_id ? (
        <p>
          You control character <code>{character_id}</code>.
        </p>
      ) : (
        <p>You are the Dungeon Master for this room.</p>
      )}
      <p className="hint">The board will appear here once it is built (Phase 2+).</p>
    </main>
  );
}
