// Host "create room" screen.
//
// The DM names an encounter and (optionally) themselves, submits to POST /rooms,
// and receives a one-time host invite link to copy and open. The plaintext token
// is only ever shown here (the server stores just its hash), so we surface it
// clearly with a copy affordance.

import { useState } from 'react';
import { ApiError, createRoom } from '../api/client';
import type { CreateRoomResponse } from '../api/types';

type Status = 'idle' | 'submitting';

export default function CreateRoomScreen() {
  const [roomName, setRoomName] = useState('');
  const [hostName, setHostName] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CreateRoomResponse | null>(null);
  const [copied, setCopied] = useState(false);

  const trimmedName = roomName.trim();
  const canSubmit = trimmedName.length > 0 && status === 'idle';

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    setStatus('submitting');
    setError(null);
    try {
      const response = await createRoom({
        name: trimmedName,
        host_display_name: hostName.trim() || null,
      });
      setResult(response);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : 'Something went wrong creating the room.';
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

  if (result) {
    const { room, host_link } = result;
    return (
      <main className="screen">
        <h1>Room created</h1>
        <p>
          <strong>{room.name}</strong> is ready (status: {room.status}).
        </p>
        <label htmlFor="host-link">Your host link — open this to run the encounter:</label>
        <div className="link-row">
          <input id="host-link" type="text" readOnly value={host_link.url} />
          <button type="button" onClick={() => void handleCopy(host_link.url)}>
            {copied ? 'Copied!' : 'Copy'}
          </button>
        </div>
        <p className="hint">
          This link is shown only once — keep it safe. Configure characters and invite players next.
        </p>
        <p>
          <a href={`/rooms/${room.id}/characters`}>Configure characters &rarr;</a>
        </p>
      </main>
    );
  }

  return (
    <main className="screen">
      <h1>Create a room</h1>
      <p>Start a new D&amp;D encounter and invite your players with a link.</p>
      <form onSubmit={(event) => void handleSubmit(event)} noValidate>
        <label htmlFor="room-name">Room name</label>
        <input
          id="room-name"
          type="text"
          value={roomName}
          maxLength={120}
          required
          autoFocus
          onChange={(event) => setRoomName(event.target.value)}
          placeholder="The Sunless Citadel"
        />

        <label htmlFor="host-name">Your name (optional)</label>
        <input
          id="host-name"
          type="text"
          value={hostName}
          maxLength={120}
          onChange={(event) => setHostName(event.target.value)}
          placeholder="Dungeon Master"
        />

        {error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : null}

        <button type="submit" disabled={!canSubmit}>
          {status === 'submitting' ? 'Creating…' : 'Create room'}
        </button>
      </form>
    </main>
  );
}
