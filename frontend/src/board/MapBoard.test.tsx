import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
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
  Rect: () => <div data-testid="rect" />,
  Text: (props: { text?: string }) => <div data-testid="text">{props.text}</div>,
}));

// Keep MapBoard's board-hydrate effect offline: no tokens by default.
vi.mock('../api/client', () => ({
  mapImageUrl: (roomId: string) => 'http://test/rooms/' + roomId + '/map',
  listTokens: vi.fn(() => Promise.resolve([])),
  listCharacters: vi.fn(() => Promise.resolve([])),
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
});

// Let the board-hydrate effect's resolved fetches settle so their state update
// stays inside act() (the mocks resolve to empty arrays).
async function flushHydrate() {
  await act(async () => {});
}

describe('MapBoard', () => {
  it('shows a loading message while the map is loading', async () => {
    imageState.current = { image: null, status: 'loading' };
    render(<MapBoard roomId="room-1" />);
    expect(screen.getByRole('status')).toHaveTextContent(/loading map/i);
    expect(screen.queryByTestId('stage')).toBeNull();
    await flushHydrate();
  });

  it('shows a no-map message on error', async () => {
    imageState.current = { image: null, status: 'error' };
    render(<MapBoard roomId="room-1" />);
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

    render(<MapBoard roomId="room-1" />);

    expect(screen.getByTestId('stage')).toBeInTheDocument();
    const konvaImage = screen.getByTestId('konva-image');
    expect(konvaImage).toHaveAttribute('data-width', '640');
    expect(konvaImage).toHaveAttribute('data-height', '480');
    await flushHydrate();
  });
});
