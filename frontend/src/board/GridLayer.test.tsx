import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// react-konva needs a real canvas; stand in plain DOM so we can count lines.
vi.mock('react-konva', () => ({
  Line: (props: { points: number[]; strokeWidth: number }) => (
    <div
      data-testid="grid-line"
      data-points={props.points.join(',')}
      data-stroke-width={props.strokeWidth}
    />
  ),
}));

import GridLayer from './GridLayer';
import { DEFAULT_GRID } from './grid';

describe('GridLayer', () => {
  it('renders one Konva Line per grid line', () => {
    render(
      <GridLayer
        config={{ cellSize: 50, offsetX: 0, offsetY: 0 }}
        width={100}
        height={100}
        scale={1}
      />,
    );
    // 3 verticals + 3 horizontals.
    expect(screen.getAllByTestId('grid-line')).toHaveLength(6);
  });

  it('keeps stroke width ~1px on screen by dividing by scale', () => {
    render(
      <GridLayer
        config={{ cellSize: 50, offsetX: 0, offsetY: 0 }}
        width={50}
        height={50}
        scale={2}
      />,
    );
    const line = screen.getAllByTestId('grid-line')[0];
    expect(line).toHaveAttribute('data-stroke-width', '0.5');
  });

  it('renders nothing for a degenerate box', () => {
    const { container } = render(
      <GridLayer config={DEFAULT_GRID} width={0} height={0} scale={1} />,
    );
    expect(container.querySelectorAll('[data-testid="grid-line"]')).toHaveLength(0);
  });
});
