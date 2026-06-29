// Renders a room's encounter map on a Konva stage with pan + zoom.
//
// Phase 2 scope: this is PURELY LOCAL rendering — the viewport syncs nothing to
// the server yet (see ROADMAP "Board viewport syncs nothing yet"). The map image
// is the only thing on the board for now; grid and tokens land in later tasks.
//
// Interaction:
//   - drag anywhere to pan (the stage itself is draggable)
//   - mouse wheel / trackpad scroll to zoom toward the cursor
// The stage carries the transform (scale + offset); the image is drawn at its
// natural size at world origin.

import { useEffect, useRef, useState } from 'react';
import { Image as KonvaImage, Layer, Stage } from 'react-konva';
import type Konva from 'konva';
import { mapImageUrl } from '../api/client';
import GridLayer from './GridLayer';
import { DEFAULT_GRID, MIN_CELL_SIZE, type GridConfig } from './grid';
import { useImageElement } from './useImageElement';
import { fitViewport, IDENTITY_VIEWPORT, zoomAtPoint, type Viewport } from './viewport';

export interface MapBoardProps {
  roomId: string;
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

export default function MapBoard({ roomId }: MapBoardProps) {
  const [containerRef, size] = useElementSize();
  const { image, status } = useImageElement(mapImageUrl(roomId));
  const [viewport, setViewport] = useState<Viewport>(IDENTITY_VIEWPORT);
  const [grid, setGrid] = useState<GridConfig>(DEFAULT_GRID);
  const [showGrid, setShowGrid] = useState(true);

  const updateGrid = (patch: Partial<GridConfig>) => setGrid((g) => ({ ...g, ...patch }));

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
          draggable
          onWheel={handleWheel}
          onDragEnd={handleDragEnd}
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
          </Layer>
        </Stage>
      )}
      {status === 'loaded' && image && (
        <div className="map-board__grid-controls">
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
