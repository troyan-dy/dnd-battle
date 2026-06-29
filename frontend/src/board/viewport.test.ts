import { describe, expect, it } from 'vitest';
import {
  clampScale,
  fitViewport,
  MAX_SCALE,
  MIN_SCALE,
  screenToWorld,
  zoomAtPoint,
  ZOOM_STEP,
  type Viewport,
} from './viewport';

describe('clampScale', () => {
  it('keeps in-range values untouched', () => {
    expect(clampScale(1)).toBe(1);
    expect(clampScale(2.5)).toBe(2.5);
  });

  it('clamps to the min and max bounds', () => {
    expect(clampScale(0)).toBe(MIN_SCALE);
    expect(clampScale(-5)).toBe(MIN_SCALE);
    expect(clampScale(1000)).toBe(MAX_SCALE);
  });

  it('falls back to MIN_SCALE for NaN', () => {
    expect(clampScale(NaN)).toBe(MIN_SCALE);
  });
});

describe('screenToWorld', () => {
  it('inverts the stage transform', () => {
    const vp: Viewport = { scale: 2, x: 10, y: 20 };
    expect(screenToWorld(vp, { x: 30, y: 60 })).toEqual({ x: 10, y: 20 });
  });
});

describe('zoomAtPoint', () => {
  const start: Viewport = { scale: 1, x: 0, y: 0 };

  it('zooms in on negative deltaY and out on positive', () => {
    expect(zoomAtPoint(start, { x: 0, y: 0 }, -100).scale).toBeCloseTo(ZOOM_STEP);
    expect(zoomAtPoint(start, { x: 0, y: 0 }, 100).scale).toBeCloseTo(1 / ZOOM_STEP);
  });

  it('keeps the world point under the cursor fixed', () => {
    const pointer = { x: 250, y: 175 };
    const before = screenToWorld(start, pointer);
    const next = zoomAtPoint(start, pointer, -100);
    const after = screenToWorld(next, pointer);
    expect(after.x).toBeCloseTo(before.x);
    expect(after.y).toBeCloseTo(before.y);
  });

  it('does not exceed the max scale', () => {
    let vp: Viewport = { scale: MAX_SCALE, x: 0, y: 0 };
    vp = zoomAtPoint(vp, { x: 5, y: 5 }, -100);
    expect(vp.scale).toBe(MAX_SCALE);
  });

  it('does not drop below the min scale', () => {
    let vp: Viewport = { scale: MIN_SCALE, x: 0, y: 0 };
    vp = zoomAtPoint(vp, { x: 5, y: 5 }, 100);
    expect(vp.scale).toBe(MIN_SCALE);
  });
});

describe('fitViewport', () => {
  it('scales a large image down to fit and centres it', () => {
    const vp = fitViewport(2000, 1000, 800, 600);
    expect(vp.scale).toBeCloseTo(0.4); // 800/2000 is the binding dimension
    expect(vp.x).toBeCloseTo((800 - 2000 * 0.4) / 2);
    expect(vp.y).toBeCloseTo((600 - 1000 * 0.4) / 2);
  });

  it('never upscales a small image past 100%', () => {
    const vp = fitViewport(100, 100, 800, 600);
    expect(vp.scale).toBe(1);
  });

  it('returns identity for degenerate sizes', () => {
    expect(fitViewport(0, 100, 800, 600)).toEqual({ scale: 1, x: 0, y: 0 });
    expect(fitViewport(100, 100, 0, 600)).toEqual({ scale: 1, x: 0, y: 0 });
  });
});
