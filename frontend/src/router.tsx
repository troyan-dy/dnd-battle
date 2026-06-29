// Minimal dependency-free path router.
//
// The app only needs two routes for Phase 1, so we avoid pulling in a router
// library: the host create-room screen at "/" and the join screen at
// "/join/:token" (this matches the backend's APP_BASE_URL join URL shape,
// see app/api/rooms.build_invite_url). When more routes appear (Phase 2+),
// swap this for react-router.

/** A parsed invite token from a "/join/:token" path, or null for any other path. */
export function parseInviteToken(pathname: string): string | null {
  const match = /^\/join\/([^/]+)\/?$/.exec(pathname);
  if (!match) {
    return null;
  }
  return decodeURIComponent(match[1]);
}

/**
 * Parse a host "/host/:roomId/characters" path into its room id, or null for any
 * other path. This is where the DM configures characters (name, stats, portrait,
 * max HP) and hands out per-player invite links.
 *
 * NOTE: this lives under "/host", NOT "/rooms". The backend REST API owns the
 * "/rooms/*" namespace (e.g. GET /rooms/:id/characters returns JSON), and the
 * nginx reverse proxy forwards every "/rooms" request to the backend — so a SPA
 * page under "/rooms" would be shadowed by the API and render raw JSON.
 */
export function parseRoomCharactersRoomId(pathname: string): string | null {
  const match = /^\/host\/([^/]+)\/characters\/?$/.exec(pathname);
  if (!match) {
    return null;
  }
  return decodeURIComponent(match[1]);
}
