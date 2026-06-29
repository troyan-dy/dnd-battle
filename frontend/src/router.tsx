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
