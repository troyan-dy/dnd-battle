import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { GridConfig } from './grid';
import type { BoardMark } from './marks';

// react-konva needs a real canvas; swap its primitives for DOM stand-ins so we
// can assert MarkLayer's output without a canvas.
vi.mock('react-konva', () => ({
  Group: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="mark-group">{children}</div>
  ),
  Circle: () => <div data-testid="circle" />,
  Text: (props: { text?: string }) => <div data-testid="mark-label">{props.text}</div>,
}));

import MarkLayer from './MarkLayer';

const GRID: GridConfig = { cellSize: 70, offsetX: 0, offsetY: 0 };

function mark(overrides: Partial<BoardMark> = {}): BoardMark {
  return { id: 'm', x: 0, y: 0, expiresAt: 9999, ...overrides };
}

describe('MarkLayer', () => {
  it('renders one group per mark', () => {
    render(<MarkLayer marks={[mark({ id: 'a' }), mark({ id: 'b' })]} config={GRID} scale={1} />);
    expect(screen.getAllByTestId('mark-group')).toHaveLength(2);
  });

  it('renders a label when present and omits it otherwise', () => {
    render(
      <>
        <MarkLayer marks={[mark({ id: 'a', label: 'flank' })]} config={GRID} scale={1} />
      </>,
    );
    expect(screen.getByTestId('mark-label')).toHaveTextContent('flank');
  });

  it('omits the label text node when the mark has no label', () => {
    render(<MarkLayer marks={[mark({ id: 'a' })]} config={GRID} scale={1} />);
    expect(screen.queryByTestId('mark-label')).toBeNull();
  });

  it('renders nothing for an empty mark list', () => {
    const { container } = render(<MarkLayer marks={[]} config={GRID} scale={1} />);
    expect(container.querySelector('[data-testid="mark-group"]')).toBeNull();
  });
});
