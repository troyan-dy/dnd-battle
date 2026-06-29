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
const uploadMapMock = vi.hoisted(() => vi.fn(() => Promise.resolve({ url: 'x' })));
vi.mock('../api/client', () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  mapImageUrl: (roomId: string) => 'http://test/rooms/' + roomId + '/map',
  listTokens: vi.fn(() => Promise.resolve([])),
  listCharacters: vi.fn(() => Promise.resolve([])),
  uploadMap: uploadMapMock,
}));

// Don't open a real Socket.IO connection in jsdom; hand back a fake socket and
// capture the options so tests can drive the onBoardState/onAction callbacks.
const socketHarness = vi.hoisted(() => ({
  socket: { disconnect: vi.fn() },
  options: undefined as
    | undefined
    | {
        onAction?: (a: Action) => void;
        onBoardState?: (s: unknown) => void;
        onStatusChange?: (status: 'connecting' | 'connected' | 'reconnecting') => void;
        onError?: (message: string) => void;
      },
  emitAction: vi.fn(
    () => Promise.resolve({ ok: true }) as Promise<{ ok: boolean; error?: string }>,
  ),
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
  // Reset to the default "accepted" ack so a per-test mockResolvedValueOnce never
  // leaks into the next test.
  socketHarness.emitAction.mockReset();
  socketHarness.emitAction.mockResolvedValue({ ok: true });
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
    expect(screen.getByText(/no map/i)).toBeInTheDocument();
    expect(screen.queryByTestId('stage')).toBeNull();
    await flushHydrate();
  });

  it('lets the host upload a map when none exists yet', async () => {
    uploadMapMock.mockClear();
    imageState.current = { image: null, status: 'error' };
    render(<MapBoard roomId="room-1" token="tok-1" isHost />);

    const input = screen.getByLabelText(/upload a map/i) as HTMLInputElement;
    const file = new File(['x'], 'map.png', { type: 'image/png' });
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });

    expect(uploadMapMock).toHaveBeenCalledWith('room-1', file);
    await flushHydrate();
  });

  it('does not offer map upload to a player', async () => {
    imageState.current = { image: null, status: 'error' };
    render(<MapBoard roomId="room-1" token="tok-1" />);
    expect(screen.queryByLabelText(/upload a map/i)).toBeNull();
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
            armor_class: 10,
            resistances: {},
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
            armor_class: 10,
            resistances: {},
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

  it('applies attack damage live and logs it when an attack is broadcast', async () => {
    renderLoadedBoard();
    await flushHydrate();

    act(() => {
      socketHarness.options?.onBoardState?.({
        room_id: 'room-1',
        tokens: [
          { id: 't1', room_id: 'room-1', character_id: 'c1', x: 1, y: 1, size: 1 },
          { id: 't2', room_id: 'room-1', character_id: 'c2', x: 2, y: 2, size: 1 },
        ],
        characters: [
          {
            id: 'c1',
            room_id: 'room-1',
            name: 'Goblin',
            max_hp: 15,
            current_hp: 15,
            portrait_url: null,
            ability_scores: {
              strength: 10,
              dexterity: 10,
              constitution: 10,
              intelligence: 10,
              wisdom: 10,
              charisma: 10,
            },
            armor_class: 10,
            resistances: {},
            conditions: [],
          },
          {
            id: 'c2',
            room_id: 'room-1',
            name: 'Aria',
            max_hp: 25,
            current_hp: 25,
            portrait_url: null,
            ability_scores: {
              strength: 10,
              dexterity: 10,
              constitution: 10,
              intelligence: 10,
              wisdom: 10,
              charisma: 10,
            },
            armor_class: 10,
            resistances: {},
            conditions: [],
          },
        ],
        initiative: { active_index: null, round: 1, entries: [] },
      });
    });

    expect(screen.getByText('25/25')).toBeInTheDocument();

    const attack: Action = {
      version: 1,
      id: 'act-atk-1',
      room_id: 'room-1',
      actor_participant_id: 'p-1',
      seq: 3,
      payload: {
        type: 'attack',
        attacker_token_id: 't1',
        target_token_id: 't2',
        attack_roll: 14,
        attack_bonus: 2,
        attack_total: 16,
        advantage: 'normal',
        armor_class: 12,
        is_hit: true,
        is_critical_hit: false,
        is_critical_miss: false,
        damage: '1d6',
        damage_type: 'slashing',
        defense: 'normal',
        damage_rolls: [5],
        damage_total: 7,
      },
    };
    act(() => {
      socketHarness.options?.onAction?.(attack);
    });

    // Target HP dropped by the rolled damage and the log shows the line.
    expect(screen.getByText('18/25')).toBeInTheDocument();
    expect(screen.getByRole('log')).toHaveTextContent(
      'Goblin attacks Aria: d20 (14) +2 = 16 vs AC 12 — hit; 1d6 → 7 damage',
    );
  });

  it('host can launch an attack via the attack controls', async () => {
    const img = { width: 640, height: 480 } as HTMLImageElement;
    imageState.current = { image: img, status: 'loaded' };
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(800);
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(600);
    render(<MapBoard roomId="room-1" token="tok-1" isHost />);
    await flushHydrate();

    act(() => {
      socketHarness.options?.onBoardState?.({
        room_id: 'room-1',
        tokens: [
          { id: 't1', room_id: 'room-1', character_id: 'c1', x: 1, y: 1, size: 1 },
          { id: 't2', room_id: 'room-1', character_id: 'c2', x: 2, y: 2, size: 1 },
        ],
        characters: [
          {
            id: 'c1',
            room_id: 'room-1',
            name: 'Goblin',
            max_hp: 15,
            current_hp: 15,
            portrait_url: null,
            ability_scores: {
              strength: 10,
              dexterity: 10,
              constitution: 10,
              intelligence: 10,
              wisdom: 10,
              charisma: 10,
            },
            armor_class: 10,
            resistances: {},
            conditions: [],
          },
          {
            id: 'c2',
            room_id: 'room-1',
            name: 'Aria',
            max_hp: 25,
            current_hp: 25,
            portrait_url: null,
            ability_scores: {
              strength: 10,
              dexterity: 10,
              constitution: 10,
              intelligence: 10,
              wisdom: 10,
              charisma: 10,
            },
            armor_class: 10,
            resistances: {},
            conditions: [],
          },
        ],
        initiative: { active_index: null, round: 1, entries: [] },
      });
    });

    fireEvent.click(screen.getByRole('button', { name: 'Attack' }));
    expect(socketHarness.emitAction).toHaveBeenCalledWith(socketHarness.socket, {
      type: 'attack',
      attacker_token_id: 't1',
      target_token_id: 't2',
      attack_bonus: 0,
      damage: '1d6',
    });
  });

  it('shows a reconnecting banner when the connection drops and clears it on reconnect', async () => {
    renderLoadedBoard();
    await flushHydrate();

    // Healthy on first render: no banner.
    expect(screen.queryByText(/trying to reconnect/i)).toBeNull();

    act(() => {
      socketHarness.options?.onStatusChange?.('reconnecting');
    });
    expect(screen.getByText(/trying to reconnect/i)).toBeInTheDocument();

    act(() => {
      socketHarness.options?.onStatusChange?.('connected');
    });
    expect(screen.queryByText(/trying to reconnect/i)).toBeNull();
  });

  it('surfaces a rejected action as a dismissible notice', async () => {
    socketHarness.emitAction.mockResolvedValueOnce({ ok: false, error: 'It is not your turn.' });

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
            armor_class: 10,
            resistances: {},
            conditions: [],
          },
        ],
        initiative: { active_index: null, round: 1, entries: [] },
      });
    });

    // Apply damage; the server rejects it, so the human-readable reason appears.
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Damage' }));
    });
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('It is not your turn.');

    // The notice is dismissible.
    fireEvent.click(screen.getByRole('button', { name: /dismiss message/i }));
    expect(screen.queryByText('It is not your turn.')).toBeNull();
  });

  it('surfaces a join rejection error from the transport', async () => {
    renderLoadedBoard();
    await flushHydrate();

    act(() => {
      socketHarness.options?.onError?.('Invalid or expired invite link.');
    });
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid or expired invite link.');
  });
});
