import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useImageElement } from './useImageElement';

// Capture each constructed image so the test can drive its load lifecycle.
class FakeImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  width = 0;
  height = 0;
  private _src = '';

  set src(value: string) {
    this._src = value;
    instances.push(this);
  }
  get src(): string {
    return this._src;
  }
}

let instances: FakeImage[] = [];
const OriginalImage = globalThis.Image;

beforeEach(() => {
  instances = [];
  vi.stubGlobal('Image', FakeImage);
});

afterEach(() => {
  vi.stubGlobal('Image', OriginalImage);
});

describe('useImageElement', () => {
  it('starts in the loading state for a url', () => {
    const { result } = renderHook(() => useImageElement('/rooms/r1/map'));
    expect(result.current.status).toBe('loading');
    expect(result.current.image).toBeNull();
  });

  it('transitions to loaded once the image fires onload', async () => {
    const { result } = renderHook(() => useImageElement('/rooms/r1/map'));
    expect(instances).toHaveLength(1);
    act(() => {
      instances[0].width = 800;
      instances[0].height = 600;
      instances[0].onload?.();
    });
    await waitFor(() => expect(result.current.status).toBe('loaded'));
    expect(result.current.image?.width).toBe(800);
  });

  it('transitions to error when the image fails to load', async () => {
    const { result } = renderHook(() => useImageElement('/rooms/r1/map'));
    act(() => instances[0].onerror?.());
    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.image).toBeNull();
  });

  it('reports error immediately for a null url', () => {
    const { result } = renderHook(() => useImageElement(null));
    expect(result.current.status).toBe('error');
    expect(instances).toHaveLength(0);
  });
});
