// Renders a square grid overlay inside the board's Konva stage.
//
// Drawn in world coordinates over the map image, so the parent stage transform
// (pan/zoom) applies automatically. Stroke width is given in screen pixels and
// divided by `scale` so the lines stay hairline-thin at any zoom level.

import { Line } from 'react-konva';
import { buildGridLines, type GridConfig, type GridLine } from './grid';

export interface GridLayerProps {
  config: GridConfig;
  /** World extent to cover — normally the map image's natural size. */
  width: number;
  height: number;
  /** Current viewport scale, so we can keep lines a constant screen thickness. */
  scale: number;
  /** Line colour (CSS string). */
  stroke?: string;
}

const DEFAULT_STROKE = 'rgba(255, 255, 255, 0.35)';

export default function GridLayer({
  config,
  width,
  height,
  scale,
  stroke = DEFAULT_STROKE,
}: GridLayerProps) {
  const lines: GridLine[] = buildGridLines(config, width, height);
  // Keep ~1px on screen regardless of zoom; guard against a zero/NaN scale.
  const strokeWidth = scale > 0 ? 1 / scale : 1;

  return (
    <>
      {lines.map((points, i) => (
        <Line
          key={i}
          points={points}
          stroke={stroke}
          strokeWidth={strokeWidth}
          listening={false}
          perfectDrawEnabled={false}
        />
      ))}
    </>
  );
}
