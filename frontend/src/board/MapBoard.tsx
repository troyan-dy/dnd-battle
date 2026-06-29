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
import { listCharacters, listTokens, mapImageUrl } from '../api/client';
import type { CharacterResponse, InitiativeState, TokenResponse } from '../api/types';
import { createBoardSocket, emitAction } from '../realtime/connection';
import GridLayer from './GridLayer';
import { DEFAULT_GRID, MIN_CELL_SIZE, type GridConfig } from './grid';
import TokenLayer from './TokenLayer';
import MarkLayer from './MarkLayer';
import HpControls from './HpControls';
import InitiativeTracker from './InitiativeTracker';
import { applyHpAction } from './hp';
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
  const { image, status } = useImageElement(mapImageUrl(roomId));
  const [viewport, setViewport] = useState<Viewport>(IDENTITY_VIEWPORT);
  const [grid, setGrid] = useState<GridConfig>(DEFAULT_GRID);
  const [showGrid, setShowGrid] = useState(true);
  const [board, setBoard] = useState<ReconcilableBoard>(EMPTY_BOARD);
  const [characters, setCharacters] = useState<CharacterResponse[]>([]);
  const [marks, setMarks] = useState<BoardMark[]>([]);
  const [initiative, setInitiative] = useState<InitiativeState>(EMPTY_INITIATIVE);
  const [pingMode, setPingMode] = useState(false);
  const socketRef = useRef<Socket | null>(null);
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
      onBoardState: (state) => {
        setCharacters(state.characters);
        setBoard(fromBoardState(state));
        setInitiative(state.initiative);
      },
      onAction: (action) => {
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
        setBoard((b) => applyAction(b, action));
      },
    });
    socketRef.current = socket;
    return () => {
      socketRef.current = null;
      socket.disconnect();
    };
  }, [token]);

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
  const handleTokenMove = useCallback((tokenId: string, cell: { x: number; y: number }) => {
    setBoard((b) => beginOptimisticMove(b, tokenId, cell.x, cell.y));
    const socket = socketRef.current;
    if (!socket) {
      return;
    }
    void emitAction(socket, { type: 'move', token_id: tokenId, x: cell.x, y: cell.y }).then(
      (ack) => {
        if (!ack.ok) {
          setBoard((b) => rollbackMove(b, tokenId));
        }
      },
    );
  }, []);

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
      void emitAction(socket, { type: 'mark', x: cell.x, y: cell.y });
    },
    [pingMode, viewport, grid],
  );

  // End the current turn: emit the intent and let the server's broadcast advance
  // the order for everyone (including us, via onAction above). The server enforces
  // whose turn it is; the tracker button is only enabled when we are allowed.
  const handleEndTurn = useCallback(() => {
    const socket = socketRef.current;
    if (!socket) {
      return;
    }
    void emitAction(socket, { type: 'endTurn' });
  }, []);

  // Host applies damage / healing to a token. We only emit the intent; the
  // server validates + applies the durable HP change and broadcasts it back,
  // which updates the rendered HP for everyone (including us) via onAction.
  const handleDamage = useCallback((tokenId: string, amount: number) => {
    const socket = socketRef.current;
    if (!socket) {
      return;
    }
    void emitAction(socket, { type: 'damage', token_id: tokenId, amount });
  }, []);

  const handleHeal = useCallback((tokenId: string, amount: number) => {
    const socket = socketRef.current;
    if (!socket) {
      return;
    }
    void emitAction(socket, { type: 'heal', token_id: tokenId, amount });
  }, []);

  const tokens = joinTokens(displayTokens(board), characters);

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

  return (
    <div ref={containerRef} className="map-board" data-status={status}>
      {status === 'loading' && (
        <p className="map-board__overlay" role="status">
          Loading map…
        </p>
      )}
      {status === 'error' && (
        <p className="map-board__overlay" role="alert">
          No map has been uploaded for this room yet.
        </p>
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
