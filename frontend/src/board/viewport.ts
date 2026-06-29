// Pure pan/zoom math for the board's Konva stage.
//
// Kept free of React/Konva so it can be unit-tested in isolation. A Viewport is
// the stage transform: a uniform `scale` plus a top-left offset `{ x, y }` in
// screen pixels. World (image) coordinates relate to screen coordinates by
//   screen = world * scale + offset
// so the inverse is  world = (screen - offset) / scale.

export interface Viewport {
  /** Uniform zoom factor (1 = 100%). */
  scale: number;
  /** Stage x offset in screen pixels. */
  x: number;
  /** Stage y offset in screen pixels. */
  y: number;
}

export interface Point {
  x: number;
  y: number;
}

/** Smallest / largest zoom we allow, and the per-wheel-notch multiplier. */
export const MIN_SCALE = 0.1;
export const MAX_SCALE = 8;
export const ZOOM_STEP = 1.05;

/** Identity-ish starting viewport: 100% zoom, no offset. */
export const IDENTITY_VIEWPORT: Viewport = { scale: 1, x: 0, y: 0 };

/** Clamp a scale into the allowed [MIN_SCALE, MAX_SCALE] range. */
export function clampScale(scale: number): number {
  if (Number.isNaN(scale)) {
    return MIN_SCALE;
  }
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
}

/** Convert a screen-space point to world (image) space under a viewport. */
export function screenToWorld(viewport: Viewport, screen: Point): Point {
  return {
    x: (screen.x - viewport.x) / viewport.scale,
    y: (screen.y - viewport.y) / viewport.scale,
  };
}

/**
 * Compute the viewport after a wheel zoom centred on `pointer` (screen space).
 *
 * A negative `deltaY` (scroll up / pinch out) zooms in; positive zooms out. The
 * world point under the cursor stays fixed on screen, which is the natural
 * "zoom where I'm pointing" behaviour. Scale is clamped, so zooming past a limit
 * is a no-op on scale but still returns a stable viewport.
 */
export function zoomAtPoint(viewport: Viewport, pointer: Point, deltaY: number): Viewport {
  const factor = deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
  const newScale = clampScale(viewport.scale * factor);

  // World point currently under the pointer must remain under the pointer.
  const world = screenToWorld(viewport, pointer);
  return {
    scale: newScale,
    x: pointer.x - world.x * newScale,
    y: pointer.y - world.y * newScale,
  };
}

/**
 * Viewport that centres an image of the given size inside a viewport box,
 * scaled down (never up) to fit. Used as the initial framing of a freshly
 * loaded map.
 */
export function fitViewport(
  imageWidth: number,
  imageHeight: number,
  boxWidth: number,
  boxHeight: number,
): Viewport {
  if (imageWidth <= 0 || imageHeight <= 0 || boxWidth <= 0 || boxHeight <= 0) {
    return IDENTITY_VIEWPORT;
  }
  const scale = clampScale(Math.min(boxWidth / imageWidth, boxHeight / imageHeight, 1));
  return {
    scale,
    x: (boxWidth - imageWidth * scale) / 2,
    y: (boxHeight - imageHeight * scale) / 2,
  };
}
