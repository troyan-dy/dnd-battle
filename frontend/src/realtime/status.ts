// Pure helpers for surfacing realtime connection health and server errors to the
// user. React/Konva-free so they unit-test in isolation (mirrors the marks.ts /
// combatLog.ts convention). The transport (connection.ts) reports raw socket
// lifecycle transitions; these helpers map them to user-facing UI state. The
// server stays authoritative (CLAUDE.md rule 1) — this layer only reflects what
// the transport observes (connection state, rejection messages), never inventing
// board state.

/** Health of the realtime board connection, as the user should perceive it. */
export type ConnectionStatus = 'connecting' | 'connected' | 'reconnecting';

/** A banner describing a non-connected state; null while healthy. */
export interface ConnectionBanner {
  message: string;
  tone: 'info' | 'warning';
}

const BANNERS: Record<ConnectionStatus, ConnectionBanner | null> = {
  connected: null,
  connecting: { message: 'Connecting to the board…', tone: 'info' },
  reconnecting: { message: 'Connection lost — trying to reconnect…', tone: 'warning' },
};

/**
 * Banner to show for a connection status, or null when connected (no banner).
 */
export function connectionBanner(status: ConnectionStatus): ConnectionBanner | null {
  return BANNERS[status];
}

/** A transient, dismissible message shown to the user (e.g. a rejected action). */
export interface Notice {
  id: number;
  message: string;
}

/** Cap on simultaneously-shown notices; the oldest is dropped past this. */
export const MAX_NOTICES = 4;

/**
 * Append a notice, keeping at most MAX_NOTICES (oldest dropped).
 *
 * Returns a new array; the input is never mutated.
 */
export function appendNotice(notices: readonly Notice[], notice: Notice): Notice[] {
  const next = [...notices, notice];
  return next.length > MAX_NOTICES ? next.slice(next.length - MAX_NOTICES) : next;
}

/** Remove the notice with the given id; returns an equivalent array otherwise. */
export function dismissNotice(notices: readonly Notice[], id: number): Notice[] {
  return notices.filter((notice) => notice.id !== id);
}
