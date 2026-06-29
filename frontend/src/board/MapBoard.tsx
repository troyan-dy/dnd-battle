// Renders a room's encounter map on a Konva stage with pan + zoom, plus the
// live tokens and transient marks/pings — synced in real time over Socket.IO.
//
// Realtime (Phase 4/5): the board opens a Socket.IO connection authenticated by
// this client's invite token, receives the full BoardState on (re)join, and
// applies each broadcast Action. A client may drag its own token(s): the move is
// applied OPTIMISTICALLY for instant feedback, then reconciled against the
// server's authoritative broadcast (CLAUDE.md rule 5) — the token snaps to the
// server position on mismatch, and a rejected intent rolls the move back.
// Reconciliation logic is isolated in `./reconcile` (pure, unit-tested).
//
// Marks/pings (Phase 5): any participant may drop a temporary ping that the
// server broadcasts to everyone in the room; pings are EPHEMERAL (no durable
// storage) and auto-expire client-side. Logic is isolated in `./marks`.
//
// Interaction:
//   - drag anywhere on empty board to pan (the stage itself is draggable)
//   - mouse wheel / trackpad scroll to zoom toward the cursor
//   - drag your own token to move it (grid-snapped)
//   - toggle "Ping" mode, then click the board to drop a temporary mark

import { useCallback, useEffect, useRef, useState } from 'react';
import { Image as KonvaImage, Layer, Stage } from 'react-konva';
import type Konva from 'konva';
import type { Socket } from 'socket.io-client';
import { ApiError, listCharacters, listTokens, mapImageUrl, uploadMap } from '../api/client';
import type { CharacterResponse, InitiativeState, TokenResponse } from '../api/types';
import { createBoardSocket, emitAction } from '../realtime/connection';
import {
  appendNotice,
  connectionBanner,
  dismissNotice,
  type ConnectionStatus,
  type Notice,
} from '../realtime/status';
import GridLayer from './GridLayer';
import { DEFAULT_GRID, MIN_CELL_SIZE, type GridConfig } from './grid';
import TokenLayer from './TokenLayer';
import MarkLayer from './MarkLayer';
import HpControls from './HpControls';
import AttackControls from './AttackControls';
import VisibilityControls from './VisibilityControls';
import CombatLogPanel from './CombatLogPanel';
import InitiativeTracker from './InitiativeTracker';
import { applyHpAction } from './hp';
import { appendLogEntry, logEntry, type CombatLogEntry } from './combatLog';
import { advanceInitiative, EMPTY_INITIATIVE } from './initiative';
import { addMark, markFromAction, pruneExpired, type BoardMark } from './marks';
import { joinTokens, worldToCell } from './tokens';
import {
  applyAction,
  beginOptimisticMove,
  displayTokens,
  EMPTY_BOARD,
  fromBoardState,
  fromTokens,
  rollbackMove,
  type ReconcilableBoard,
} from './reconcile';
import { useImageElement } from './useImageElement';
import {
  fitViewport,
  IDENTITY_VIEWPORT,
  screenToWorld,
  zoomAtPoint,
  type Viewport,
} from './viewport';

export interface MapBoardProps {
  /** Room whose board to render. */
  roomId: string;
  /** This client's invite token — the credential used to join the realtime room. */
  token: string;
  /** Host controls every token; a player controls only its bound character's token. */
  isHost?: boolean;
  /** The character this (player) client may move; null/undefined for none. */
  controllableCharacterId?: string | null;
}

/** Track a DOM element's content-box size, updating on resize. */
function useElementSize(): [
  React.RefObject<HTMLDivElement | null>,
  { width: number; height: number },
] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = ref.current;
    if (!el) {
      return;
    }
    const update = () => setSize({ width: el.clientWidth, height: el.clientHeight });
    update();

    if (typeof ResizeObserver === 'undefined') {
      return;
    }
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return [ref, size];
}

export default function MapBoard({
  roomId,
  token,
  isHost = false,
  controllableCharacterId = null,
}: MapBoardProps) {
  const [containerRef, size] = useElementSize();
  // Bumped after a host (re)uploads the map; appended to the image URL as a
  // cache-buster so the browser re-fetches GET /rooms/{id}/map (same URL).
  const [mapVersion, setMapVersion] = useState(0);
  const mapUrl = mapVersion > 0 ? `${mapImageUrl(roomId)}?v=${mapVersion}` : mapImageUrl(roomId);
  const { image, status } = useImageElement(mapUrl);
  const [uploadingMap, setUploadingMap] = useState(false);
  const [mapUploadError, setMapUploadError] = useState<string | null>(null);
  const [viewport, setViewport] = useState<Viewport>(IDENTITY_VIEWPORT);
  const [grid, setGrid] = useState<GridConfig>(DEFAULT_GRID);
  const [showGrid, setShowGrid] = useState(true);
  const [board, setBoard] = useState<ReconcilableBoard>(EMPTY_BOARD);
  const [characters, setCharacters] = useState<CharacterResponse[]>([]);
  const [marks, setMarks] = useState<BoardMark[]>([]);
  const [log, setLog] = useState<CombatLogEntry[]>([]);
  const [initiative, setInitiative] = useState<InitiativeState>(EMPTY_INITIATIVE);
  const [pingMode, setPingMode] = useState(false);
  const [connection, setConnection] = useState<ConnectionStatus>('connecting');
  const [notices, setNotices] = useState<Notice[]>([]);
  const socketRef = useRef<Socket | null>(null);
  // Monotonic source of notice ids (ref so it survives re-renders without state).
  const noticeIdRef = useRef(0);

  // Surface a server-rejected intent (or any user-facing error) as a dismissible
  // notice. Memoised so it is stable across renders and safe in effect deps.
  const pushNotice = useCallback((message: string) => {
    noticeIdRef.current += 1;
    const notice: Notice = { id: noticeIdRef.current, message };
    setNotices((current) => appendNotice(current, notice));
  }, []);

  const dismiss = useCallback((id: number) => {
    setNotices((current) => dismissNotice(current, id));
  }, []);

  // Reconcile an action ack: a rejection becomes a user-facing notice. Returns
  // whether the intent succeeded so callers can also roll back optimistic state.
  const reportAck = useCallback(
    (ack: { ok: boolean; error?: string }): boolean => {
      if (!ack.ok) {
        pushNotice(ack.error ?? 'That action was rejected by the server.');
      }
      return ack.ok;
    },
    [pushNotice],
  );
  // Always-fresh board ref so the once-registered onAction handler can resolve a
  // damaged/healed token's character without capturing a stale `board` closure.
  const boardRef = useRef(board);
  boardRef.current = board;

  const updateGrid = (patch: Partial<GridConfig>) => setGrid((g) => ({ ...g, ...patch }));

  // Initial REST hydrate of tokens (+ character display data). A plain idempotent
  // read so the board paints immediately; the realtime `boardState` push below
  // then takes over as the authoritative source. Stale results are ignored.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [placed, chars] = await Promise.all([listTokens(roomId), listCharacters(roomId)]);
        if (!cancelled) {
          setCharacters(chars);
          setBoard(fromTokens(placed));
        }
      } catch {
        if (!cancelled) {
          setCharacters([]);
          setBoard(EMPTY_BOARD);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [roomId]);

  // Open the realtime board connection. On (re)join the server pushes the FULL
  // BoardState (reconnect-safe); each broadcast Action is applied authoritatively.
  useEffect(() => {
    const socket = createBoardSocket(token, {
      onStatusChange: setConnection,
      onError: pushNotice,
      onBoardState: (state) => {
        setCharacters(state.characters);
        setBoard(fromBoardState(state));
        setInitiative(state.initiative);
      },
      onAction: (action) => {
        // Every broadcast action becomes a shared combat-log line (same order for
        // everyone). The type-specific board state updates follow below.
        setLog((entries) => appendLogEntry(entries, logEntry(action)));
        if (action.payload.type === 'mark') {
          const now = Date.now();
          const mark = markFromAction(action, now);
          if (mark) {
            setMarks((m) => addMark(pruneExpired(m, now), mark));
          }
          return;
        }
        if (action.payload.type === 'endTurn') {
          // The server broadcasts only the intent; advance the local pointer the
          // same way it does. The next boardState push reconciles any drift.
          setInitiative((i) => advanceInitiative(i));
          return;
        }
        if (action.payload.type === 'damage' || action.payload.type === 'heal') {
          // Reflect the authoritative HP change live: resolve the targeted token's
          // character and clamp-apply the delta (mirrors the server).
          const payload = action.payload;
          const target = boardRef.current.authoritative.get(payload.token_id);
          if (target) {
            setCharacters((cs) => applyHpAction(cs, target.character_id, payload));
          }
          return;
        }
        if (action.payload.type === 'attack') {
          // The server already rolled + applied the damage; reflect the HP drop on
          // the target live and append the roll to the shared combat log.
          const payload = action.payload;
          const target = boardRef.current.authoritative.get(payload.target_token_id);
          if (target) {
            setCharacters((cs) =>
              applyHpAction(cs, target.character_id, {
                type: 'damage',
                token_id: payload.target_token_id,
                amount: payload.damage_total,
              }),
            );
          }
          return;
        }
        setBoard((b) => applyAction(b, action));
      },
    });
    socketRef.current = socket;
    return () => {
      socketRef.current = null;
      socket.disconnect();
    };
  }, [token, pushNotice]);

  // Periodically drop expired marks so pings fade on their own. pruneExpired
  // returns the same array when nothing changed, so this re-renders only when a
  // mark actually expires.
  useEffect(() => {
    const id = setInterval(() => {
      setMarks((m) => pruneExpired(m, Date.now()));
    }, 500);
    return () => clearInterval(id);
  }, []);

  // Whether this client may drag a given token (server still enforces this; the
  // UI just avoids offering moves it knows will be rejected).
  const canDrag = useCallback(
    (t: TokenResponse) =>
      isHost || (controllableCharacterId != null && t.character_id === controllableCharacterId),
    [isHost, controllableCharacterId],
  );

  // A token was dropped on a new cell: apply optimistically, emit the intent, and
  // reconcile — roll back if the server rejects it; a successful broadcast arrives
  // via onAction and replaces the optimistic position (CLAUDE.md rule 5).
  const handleTokenMove = useCallback(
    (tokenId: string, cell: { x: number; y: number }) => {
      setBoard((b) => beginOptimisticMove(b, tokenId, cell.x, cell.y));
      const socket = socketRef.current;
      if (!socket) {
        return;
      }
      void emitAction(socket, { type: 'move', token_id: tokenId, x: cell.x, y: cell.y }).then(
        (ack) => {
          if (!reportAck(ack)) {
            setBoard((b) => rollbackMove(b, tokenId));
          }
        },
      );
    },
    [reportAck],
  );

  // In ping mode, a click anywhere on the board drops a temporary mark at the
  // clicked cell. We only emit the intent; the server broadcasts the resulting
  // Action back to everyone (including us), which is what renders the mark.
  const handleStageClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
      if (!pingMode) {
        return;
      }
      const stage = e.target.getStage();
      const pointer = stage?.getPointerPosition();
      const socket = socketRef.current;
      if (!pointer || !socket) {
        return;
      }
      const world = screenToWorld(viewport, pointer);
      const cell = worldToCell(world.x, world.y, grid);
      void emitAction(socket, { type: 'mark', x: cell.x, y: cell.y }).then(reportAck);
    },
    [pingMode, viewport, grid, reportAck],
  );

  // End the current turn: emit the intent and let the server's broadcast advance
  // the order for everyone (including us, via onAction above). The server enforces
  // whose turn it is; the tracker button is only enabled when we are allowed.
  const handleEndTurn = useCallback(() => {
    const socket = socketRef.current;
    if (!socket) {
      return;
    }
    void emitAction(socket, { type: 'endTurn' }).then(reportAck);
  }, [reportAck]);

  // Host applies damage / healing to a token. We only emit the intent; the
  // server validates + applies the durable HP change and broadcasts it back,
  // which updates the rendered HP for everyone (including us) via onAction.
  const handleDamage = useCallback(
    (tokenId: string, amount: number) => {
      const socket = socketRef.current;
      if (!socket) {
        return;
      }
      void emitAction(socket, { type: 'damage', token_id: tokenId, amount }).then(reportAck);
    },
    [reportAck],
  );

  const handleHeal = useCallback(
    (tokenId: string, amount: number) => {
      const socket = socketRef.current;
      if (!socket) {
        return;
      }
      void emitAction(socket, { type: 'heal', token_id: tokenId, amount }).then(reportAck);
    },
    [reportAck],
  );

  // Host hides / reveals a token (fog of war). We only emit the intent; the server
  // (HOST-ONLY, CLAUDE.md rule 3) flips the durable flag and pushes a fresh,
  // role-filtered BoardState to each side, which updates our view via onBoardState.
  const handleSetVisibility = useCallback(
    (tokenId: string, hidden: boolean) => {
      const socket = socketRef.current;
      if (!socket) {
        return;
      }
      void emitAction(socket, { type: 'setVisibility', token_id: tokenId, hidden }).then(reportAck);
    },
    [reportAck],
  );

  // Make an attack: emit the intent and let the server roll + apply + broadcast.
  // The resulting `attack` Action (handled in onAction) updates HP and the log.
  const handleAttack = useCallback(
    (attackerId: string, targetId: string, bonus: number, damage: string) => {
      const socket = socketRef.current;
      if (!socket) {
        return;
      }
      void emitAction(socket, {
        type: 'attack',
        attacker_token_id: attackerId,
        target_token_id: targetId,
        attack_bonus: bonus,
        damage,
      }).then(reportAck);
    },
    [reportAck],
  );

  // E2E-only hook: expose the real token-move path + live readiness on `window` so
  // the multi-client Playwright sync test can drive a move deterministically (Konva
  // renders to a <canvas>, so a token cannot be selected/dragged via the DOM). The
  // move goes through the identical optimistic-move + socket emit + server-broadcast
  // + reconcile path the UI drag uses — it does NOT fake the broadcast; `connection`
  // lets the test wait until BOTH clients have joined the room before the move (a
  // broadcast is not replayed to a client that joins after it). Compiled out of
  // normal builds (the branch is dead unless VITE_E2E is set at build time).
  useEffect(() => {
    if (!import.meta.env.VITE_E2E) {
      return;
    }
    const w = window as typeof window & {
      __e2e?: {
        moveToken: (tokenId: string, x: number, y: number) => void;
        connection: ConnectionStatus;
      };
    };
    w.__e2e = {
      moveToken: (tokenId, x, y) => handleTokenMove(tokenId, { x, y }),
      connection,
    };
    return () => {
      delete w.__e2e;
    };
  }, [handleTokenMove, connection]);

  const banner = connectionBanner(connection);
  const tokens = joinTokens(displayTokens(board), characters);
  // Token ids this client may attack WITH (host: all; player: its own token).
  const controllableTokenIds = tokens.filter((t) => canDrag(t.token)).map((t) => t.token.id);

  // Frame the map to fit once it (and the container) are known.
  useEffect(() => {
    if (image && size.width > 0 && size.height > 0) {
      setViewport(fitViewport(image.width, image.height, size.width, size.height));
    }
  }, [image, size.width, size.height]);

  const handleWheel = (e: Konva.KonvaEventObject<WheelEvent>) => {
    e.evt.preventDefault();
    const stage = e.target.getStage();
    const pointer = stage?.getPointerPosition();
    if (!pointer) {
      return;
    }
    setViewport((v) => zoomAtPoint(v, pointer, e.evt.deltaY));
  };

  const handleDragEnd = (e: Konva.KonvaEventObject<DragEvent>) => {
    const stage = e.target.getStage();
    if (!stage || e.target !== stage) {
      return;
    }
    setViewport((v) => ({ ...v, x: stage.x(), y: stage.y() }));
  };

  // Host-only: upload (or replace) the room's map. On success bump mapVersion so
  // useImageElement re-fetches GET /rooms/{id}/map (the URL is otherwise stable).
  const handleMapUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file later
    if (!file) {
      return;
    }
    setUploadingMap(true);
    setMapUploadError(null);
    try {
      await uploadMap(roomId, file);
      setMapVersion((v) => v + 1);
    } catch (err) {
      setMapUploadError(
        err instanceof ApiError ? err.message : 'Could not upload the map. Try again.',
      );
    } finally {
      setUploadingMap(false);
    }
  };

  return (
    <div ref={containerRef} className="map-board" data-status={status}>
      {connection === 'reconnecting' && banner && (
        <p className="map-board__connection-banner" data-tone={banner.tone} aria-live="assertive">
          {banner.message}
        </p>
      )}
      {notices.length > 0 && (
        <ul className="map-board__notices" role="alert" aria-live="assertive">
          {notices.map((notice) => (
            <li key={notice.id} className="map-board__notice">
              <span>{notice.message}</span>
              <button
                type="button"
                className="map-board__notice-dismiss"
                aria-label="Dismiss message"
                onClick={() => dismiss(notice.id)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      {status === 'loading' && (
        <p className="map-board__overlay" role="status">
          Loading map…
        </p>
      )}
      {status === 'error' && (
        <div className="map-board__overlay" role="status">
          <p>No map has been uploaded for this room yet.</p>
          {isHost ? (
            <p className="map-board__map-upload">
              <label className="map-board__upload-button">
                {uploadingMap ? 'Uploading…' : 'Upload a map'}
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  disabled={uploadingMap}
                  onChange={(e) => void handleMapUpload(e)}
                  hidden
                />
              </label>
              {mapUploadError ? (
                <span role="alert" className="error">
                  {mapUploadError}
                </span>
              ) : null}
            </p>
          ) : (
            <p className="hint">Ask your DM to set up the encounter map.</p>
          )}
        </div>
      )}
      {status === 'loaded' && image && size.width > 0 && size.height > 0 && (
        <Stage
          width={size.width}
          height={size.height}
          x={viewport.x}
          y={viewport.y}
          scaleX={viewport.scale}
          scaleY={viewport.scale}
          draggable={!pingMode}
          onWheel={handleWheel}
          onDragEnd={handleDragEnd}
          onClick={handleStageClick}
          onTap={handleStageClick}
        >
          <Layer>
            <KonvaImage image={image} width={image.width} height={image.height} />
            {showGrid && (
              <GridLayer
                config={grid}
                width={image.width}
                height={image.height}
                scale={viewport.scale}
              />
            )}
            <TokenLayer tokens={tokens} config={grid} canDrag={canDrag} onMove={handleTokenMove} />
            <MarkLayer marks={marks} config={grid} scale={viewport.scale} />
          </Layer>
        </Stage>
      )}
      <InitiativeTracker
        state={initiative}
        isHost={isHost}
        controllableCharacterId={controllableCharacterId}
        onEndTurn={handleEndTurn}
      />
      {isHost && <HpControls tokens={tokens} onDamage={handleDamage} onHeal={handleHeal} />}
      {isHost && <VisibilityControls tokens={tokens} onSetVisibility={handleSetVisibility} />}
      {controllableTokenIds.length > 0 && (
        <AttackControls
          tokens={tokens}
          controllableTokenIds={controllableTokenIds}
          onAttack={handleAttack}
        />
      )}
      <CombatLogPanel entries={log} tokens={tokens} />
      {status === 'loaded' && image && (
        <div className="map-board__grid-controls">
          <button
            type="button"
            className={pingMode ? 'map-board__ping-toggle is-active' : 'map-board__ping-toggle'}
            aria-pressed={pingMode}
            onClick={() => setPingMode((p) => !p)}
          >
            Ping
          </button>
          {isHost && (
            <label className="map-board__upload-button">
              {uploadingMap ? 'Uploading…' : 'Replace map'}
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                disabled={uploadingMap}
                onChange={(e) => void handleMapUpload(e)}
                hidden
              />
            </label>
          )}
          <label>
            <input
              type="checkbox"
              checked={showGrid}
              onChange={(e) => setShowGrid(e.target.checked)}
            />
            Grid
          </label>
          <label>
            Cell
            <input
              type="number"
              min={MIN_CELL_SIZE}
              step={1}
              value={grid.cellSize}
              onChange={(e) =>
                updateGrid({ cellSize: Math.max(MIN_CELL_SIZE, Number(e.target.value) || 0) })
              }
            />
          </label>
          <label>
            X
            <input
              type="number"
              step={1}
              value={grid.offsetX}
              onChange={(e) => updateGrid({ offsetX: Number(e.target.value) || 0 })}
            />
          </label>
          <label>
            Y
            <input
              type="number"
              step={1}
              value={grid.offsetY}
              onChange={(e) => updateGrid({ offsetY: Number(e.target.value) || 0 })}
            />
          </label>
        </div>
      )}
    </div>
  );
}
