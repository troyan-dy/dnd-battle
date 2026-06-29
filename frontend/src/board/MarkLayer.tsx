// Renders transient marks / pings inside the board's Konva stage.
//
// Each mark is drawn in WORLD coordinates at the centre of its grid cell, so the
// parent stage transform (pan/zoom) applies automatically. Marks are purely
// informational and never intercept pointer events (listening=false). The live
// mark list + expiry live in `./marks` (pure, unit-tested); this component only
// draws the current set.

import { Circle, Group, Text } from 'react-konva';
import type { GridConfig } from './grid';
import { DEFAULT_MARK_COLOR, type BoardMark } from './marks';

export interface MarkLayerProps {
  /** The currently-live marks to draw. */
  marks: readonly BoardMark[];
  /** Same grid the overlay/tokens use, so marks land on cell centres. */
  config: GridConfig;
  /** Viewport scale, to keep the ring outline a constant screen thickness. */
  scale: number;
}

export default function MarkLayer({ marks, config, scale }: MarkLayerProps) {
  const cell = config.cellSize;
  const radius = Math.max(4, cell * 0.4);
  const strokeWidth = scale > 0 ? 3 / scale : 3;
  const font = Math.max(8, cell * 0.22);

  return (
    <>
      {marks.map((mark) => {
        const cx = config.offsetX + (mark.x + 0.5) * cell;
        const cy = config.offsetY + (mark.y + 0.5) * cell;
        const color = mark.color || DEFAULT_MARK_COLOR;
        return (
          <Group key={mark.id} listening={false}>
            <Circle
              x={cx}
              y={cy}
              radius={radius}
              stroke={color}
              strokeWidth={strokeWidth}
              fill={color}
              opacity={0.85}
              fillEnabled={false}
              perfectDrawEnabled={false}
            />
            <Circle x={cx} y={cy} radius={radius * 0.25} fill={color} perfectDrawEnabled={false} />
            {mark.label && (
              <Text
                x={cx - cell}
                y={cy + radius + font * 0.2}
                width={cell * 2}
                align="center"
                text={mark.label}
                fontSize={font}
                fill={color}
                perfectDrawEnabled={false}
              />
            )}
          </Group>
        );
      })}
    </>
  );
}
