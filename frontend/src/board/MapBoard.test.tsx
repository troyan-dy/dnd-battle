import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Action } from '../api/types';
import type { ImageElementState } from './useImageElement';

// react-konva needs a real canvas, which jsdom lacks. Replace its components
// with plain DOM stand-ins so we can assert MapBoard's wiring without a canvas.
vi.mock('react-konva', () => ({
  Stage: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="stage">{children}</div>
  ),
  Layer: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="layer">{children}</div>
  ),
  Image: (props: { width?: number; height?: number }) => (
    <div data-testid="konva-image" data-width={props.width} data-height={props.height} />
  ),
  Line: () => <div data-testid="grid-line" />,
  Group: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="token-group">{children}</div>
  ),
  Circle: () => <div data-testid="circle" />,
  Rect: () => <div data-testid="rect" />,
  Text: (props: { text?: string }) => <div data-testid="text">{props.text}</div>,
}));

// Keep MapBoard's board-hydrate effect offline: no tokens by default.
vi.mock('../api/client', () => ({
  mapImageUrl: (roomId: string) => 'http://test/rooms/' + roomId + '/map',
  listTokens: vi.fn(() => Promise.resolve([])),
  listCharacters: vi.fn(() => Promise.resolve([])),
}));

// Don't open a real Socket.IO connection in jsdom; hand back a fake socket and
// capture the options so tests can drive the onBoardState/onAction callbacks.
const socketHarness = vi.hoisted(() => ({
  socket: { disconnect: vi.fn() },
  options: undefined as
    undefined | { onAction?: (a: Action) => void; onBoardState?: (s: unknown) => void },
  emitAction: vi.fn(() => Promise.resolve({ ok: true })),
}));
vi.mock('../realtime/connection', () => ({
  createBoardSocket: vi.fn((_token: string, options: unknown) => {
    socketHarness.options = options as typeof socketHarness.options;
    return socketHarness.socket;
  }),
  emitAction: socketHarness.emitAction,
}));

// Drive MapBoard's load state directly.
const imageState = vi.hoisted(() => ({
  current: { image: null, status: 'loading' } as ImageElementState,
}));
vi.mock('./useImageElement', () => ({
  useImageElement: () => imageState.current,
}));

import MapBoard from './MapBoard';

afterEach(() => {
  imageState.current = { image: null, status: 'loading' };
  socketHarness.options = undefined;
  socketHarness.emitAction.mockClear();
});

/** Render a fully loaded board (image + measured container) for interaction tests. */
function renderLoadedBoard() {
  const img = { width: 640, height: 480 } as HTMLImageElement;
  imageState.current = { image: img, status: 'loaded' };
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(800);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(600);
  return render(<MapBoard roomId="room-1" token="tok-1" />);
}

function markAction(): Action {
  return {
    version: 1,
    id: 'act-mark-1',
    room_id: 'room-1',
    actor_participant_id: 'p-1',
    seq: 0,
    payload: { type: 'mark', x: 2, y: 3 },
  };
}

// Let the board-hydrate effect's resolved fetches settle so their state update
// stays inside act() (the mocks resolve to empty arrays).
async function flushHydrate() {
  await act(async () => {});
}

describe('MapBoard', () => {
  it('shows a loading message while the map is loading', async () => {
    imageState.current = { image: null, status: 'loading' };
    render(<MapBoard roomId="room-1" token="tok-1" />);
    expect(screen.getByRole('status')).toHaveTextContent(/loading map/i);
    expect(screen.queryByTestId('stage')).toBeNull();
    await flushHydrate();
  });

  it('shows a no-map message on error', async () => {
    imageState.current = { image: null, status: 'error' };
    render(<MapBoard roomId="room-1" token="tok-1" />);
    expect(screen.getByRole('alert')).toHaveTextContent(/no map/i);
    expect(screen.queryByTestId('stage')).toBeNull();
    await flushHydrate();
  });

  it('renders the konva stage with the image once loaded', async () => {
    const img = { width: 640, height: 480 } as HTMLImageElement;
    imageState.current = { image: img, status: 'loaded' };

    // Container needs a measured size for the stage to render.
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(800);
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(600);

    render(<MapBoard roomId="room-1" token="tok-1" />);

    expect(screen.getByTestId('stage')).toBeInTheDocument();
    const konvaImage = screen.getByTestId('konva-image');
    expect(konvaImage).toHaveAttribute('data-width', '640');
    expect(konvaImage).toHaveAttribute('data-height', '480');
    await flushHydrate();
  });

  it('toggles ping mode via the Ping control', async () => {
    renderLoadedBoard();
    await flushHydrate();

    const ping = screen.getByRole('button', { name: /ping/i });
    expect(ping).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(ping);
    expect(ping).toHaveAttribute('aria-pressed', 'true');
  });

  it('renders a mark when the server broadcasts a mark action', async () => {
    renderLoadedBoard();
    await flushHydrate();

    expect(screen.queryByTestId('circle')).toBeNull();
    act(() => {
      socketHarness.options?.onAction?.(markAction());
    });
    // MarkLayer draws two Circles per mark (ring + dot).
    expect(screen.getAllByTestId('circle').length).toBeGreaterThan(0);
  });

  it('shows the initiative tracker from boardState and emits endTurn', async () => {
    const img = { width: 640, height: 480 } as HTMLImageElement;
    imageState.current = { image: img, status: 'loaded' };
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(800);
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(600);
    render(<MapBoard roomId="room-1" token="tok-1" isHost />);
    await flushHydrate();

    // No tracker until the server pushes an order.
    expect(screen.queryByRole('group', { name: /initiative order/i })).toBeNull();

    act(() => {
      socketHarness.options?.onBoardState?.({
        room_id: 'room-1',
        tokens: [],
        characters: [],
        initiative: {
          active_index: 0,
          round: 1,
          entries: [
            { id: 'e0', character_id: null, name: 'Goblin', initiative: 15, order_index: 0 },
          ],
        },
      });
    });

    expect(screen.getByText('Round 1')).toBeInTheDocument();
    expect(screen.getByText('Goblin')).toBeInTheDocument();

    // Host view (default props) -> End turn enabled and emits the intent.
    fireEvent.click(screen.getByRole('button', { name: 'End turn' }));
    expect(socketHarness.emitAction).toHaveBeenCalledWith(socketHarness.socket, {
      type: 'endTurn',
    });
  });

  it('advances the tracker when an endTurn action is broadcast', async () => {
    renderLoadedBoard();
    await flushHydrate();

    act(() => {
      socketHarness.options?.onBoardState?.({
        room_id: 'room-1',
        tokens: [],
        characters: [],
        initiative: {
          active_index: 0,
          round: 1,
          entries: [
            { id: 'e0', character_id: null, name: 'Goblin', initiative: 15, order_index: 0 },
            { id: 'e1', character_id: null, name: 'Orc', initiative: 8, order_index: 1 },
          ],
        },
      });
    });

    // Goblin is active first.
    expect(screen.getByText('Goblin').closest('li')).toHaveAttribute('aria-current', 'true');

    const endTurn: Action = {
      version: 1,
      id: 'act-end-1',
      room_id: 'room-1',
      actor_participant_id: 'p-1',
      seq: 1,
      payload: { type: 'endTurn' },
    };
    act(() => {
      socketHarness.options?.onAction?.(endTurn);
    });

    // Pointer advanced to Orc.
    expect(screen.getByText('Orc').closest('li')).toHaveAttribute('aria-current', 'true');
  });

  it('updates rendered HP live when a damage action is broadcast', async () => {
    renderLoadedBoard();
    await flushHydrate();

    act(() => {
      socketHarness.options?.onBoardState?.({
        room_id: 'room-1',
        tokens: [{ id: 't1', room_id: 'room-1', character_id: 'c1', x: 1, y: 1, size: 1 }],
        characters: [
          {
            id: 'c1',
            room_id: 'room-1',
            name: 'Aria',
            max_hp: 30,
            current_hp: 20,
            portrait_url: null,
            ability_scores: {
              strength: 10,
              dexterity: 10,
              constitution: 10,
              intelligence: 10,
              wisdom: 10,
              charisma: 10,
            },
            conditions: [],
          },
        ],
        initiative: { active_index: null, round: 1, entries: [] },
      });
    });

    expect(screen.getByText('20/30')).toBeInTheDocument();

    const damage: Action = {
      version: 1,
      id: 'act-dmg-1',
      room_id: 'room-1',
      actor_participant_id: 'p-1',
      seq: 2,
      payload: { type: 'damage', token_id: 't1', amount: 5 },
    };
    act(() => {
      socketHarness.options?.onAction?.(damage);
    });

    expect(screen.getByText('15/30')).toBeInTheDocument();
  });

  it('host can apply damage via the HP controls', async () => {
    const img = { width: 640, height: 480 } as HTMLImageElement;
    imageState.current = { image: img, status: 'loaded' };
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(800);
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(600);
    render(<MapBoard roomId="room-1" token="tok-1" isHost />);
    await flushHydrate();

    act(() => {
      socketHarness.options?.onBoardState?.({
        room_id: 'room-1',
        tokens: [{ id: 't1', room_id: 'room-1', character_id: 'c1', x: 1, y: 1, size: 1 }],
        characters: [
          {
            id: 'c1',
            room_id: 'room-1',
            name: 'Aria',
            max_hp: 30,
            current_hp: 20,
            portrait_url: null,
            ability_scores: {
              strength: 10,
              dexterity: 10,
              constitution: 10,
              intelligence: 10,
              wisdom: 10,
              charisma: 10,
            },
            conditions: [],
          },
        ],
        initiative: { active_index: null, round: 1, entries: [] },
      });
    });

    fireEvent.click(screen.getByRole('button', { name: 'Damage' }));
    expect(socketHarness.emitAction).toHaveBeenCalledWith(socketHarness.socket, {
      type: 'damage',
      token_id: 't1',
      amount: 1,
    });
  });
});
