import {
  test,
  expect,
  request as playwrightRequest,
  type APIRequestContext,
} from '@playwright/test';

// Core real-time guarantee (CLAUDE.md): two SEPARATE browser clients in the same
// room — one moves a token, the OTHER sees it. The server is authoritative, so the
// proof is that the second client renders the move it never triggered: the move is
// emitted by client A as an intent, the server validates + broadcasts the resulting
// Action to the room, and client B applies that broadcast to its shared combat log.
// We assert on the combat log (a DOM `role="log"` overlay) because tokens render to
// a Konva <canvas> and cannot be queried via the DOM; the log line is driven
// directly by the broadcast Action, so its appearance on B proves the broadcast
// reached the second client.

const BACKEND_URL = 'http://127.0.0.1:8100';

// A minimal valid 1x1 PNG (the board only renders the canvas — hence the move hook
// and on-canvas tokens — once a map image has loaded).
const ONE_PX_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC',
  'base64',
);

interface SeededRoom {
  roomId: string;
  hostToken: string;
  playerToken: string;
  tokenId: string;
}

/** Seed a room + map + a player character with a placed token via the REST API. */
async function seedRoom(api: APIRequestContext): Promise<SeededRoom> {
  const createResp = await api.post(`${BACKEND_URL}/rooms`, {
    data: { name: 'E2E Ambush', host_display_name: 'DM' },
  });
  expect(createResp.ok()).toBeTruthy();
  const created = await createResp.json();
  const roomId: string = created.room.id;
  const hostToken: string = created.host_link.token;

  const mapResp = await api.post(`${BACKEND_URL}/rooms/${roomId}/map`, {
    multipart: {
      file: { name: 'map.png', mimeType: 'image/png', buffer: ONE_PX_PNG },
    },
  });
  expect(mapResp.ok()).toBeTruthy();

  const playerResp = await api.post(`${BACKEND_URL}/rooms/${roomId}/participants`, {
    data: { character_name: 'Aria', max_hp: 24, display_name: 'P1' },
  });
  expect(playerResp.ok()).toBeTruthy();
  const player = await playerResp.json();
  const playerToken: string = player.invite_link.token;
  const characterId: string = player.character_id;

  const tokenResp = await api.post(`${BACKEND_URL}/rooms/${roomId}/tokens`, {
    data: { character_id: characterId, x: 2, y: 2, size: 1 },
  });
  expect(tokenResp.ok()).toBeTruthy();
  const tokenId: string = (await tokenResp.json()).id;

  return { roomId, hostToken, playerToken, tokenId };
}

test('a token move by one client is broadcast to the other client', async ({ browser }) => {
  const api = await playwrightRequest.newContext();
  const { hostToken, playerToken, tokenId } = await seedRoom(api);
  await api.dispose();

  // Two genuinely separate clients: independent browser contexts (own storage +
  // own Socket.IO connection), joining the same room via their own invite links.
  const hostContext = await browser.newContext();
  const playerContext = await browser.newContext();
  const hostPage = await hostContext.newPage();
  const playerPage = await playerContext.newPage();

  try {
    await hostPage.goto(`/join/${hostToken}`);
    await playerPage.goto(`/join/${playerToken}`);

    // Both clients must have JOINED the room before the move: a broadcast Action is
    // not replayed to a client that connects after it, so if the player joined late
    // it would miss the move and the test would be a false negative. The e2e hook
    // surfaces the live socket connection status; wait until both are 'connected'.
    const isConnected = () =>
      (window as typeof window & { __e2e?: { connection: string } }).__e2e?.connection ===
      'connected';
    await hostPage.waitForFunction(isConnected);
    await playerPage.waitForFunction(isConnected);

    // The other client has NOT seen any move yet — no move line in its combat log.
    await expect(playerPage.locator('[data-action-type="move"]')).toHaveCount(0);

    // Client A (host) moves the token. This goes through the real optimistic-move +
    // socket-emit path; the server validates and broadcasts the Action to the room.
    await hostPage.evaluate(
      ([id]) => {
        (
          window as typeof window & {
            __e2e: { moveToken: (tokenId: string, x: number, y: number) => void };
          }
        ).__e2e.moveToken(id, 5, 6);
      },
      [tokenId],
    );

    // The PROOF: client B — which never triggered the move — receives the broadcast
    // and renders the move line in its own combat log.
    const playerMoveLine = playerPage.locator('[data-action-type="move"]');
    await expect(playerMoveLine).toHaveCount(1);
    await expect(playerMoveLine).toHaveText(/moves to \(5, 6\)/);

    // And the mover sees it too (same authoritative broadcast, same shared log).
    await expect(hostPage.locator('[data-action-type="move"]')).toHaveText(/moves to \(5, 6\)/);
  } finally {
    await hostContext.close();
    await playerContext.close();
  }
});
