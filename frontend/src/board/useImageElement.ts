// Loads an HTMLImageElement from a URL for use as a Konva image source.
//
// Konva draws from a real <img> element, so we create one imperatively and track
// its load lifecycle. Re-runs whenever the URL changes and ignores stale loads
// (a slow earlier request can't clobber a newer one). Reconnect-safe: pointing
// at the same idempotent GET /rooms/{id}/map URL again simply reloads it.

import { useEffect, useState } from 'react';

export type ImageStatus = 'loading' | 'loaded' | 'error';

export interface ImageElementState {
  image: HTMLImageElement | null;
  status: ImageStatus;
}

export function useImageElement(url: string | null): ImageElementState {
  const [state, setState] = useState<ImageElementState>({
    image: null,
    status: url ? 'loading' : 'error',
  });

  useEffect(() => {
    if (!url) {
      setState({ image: null, status: 'error' });
      return;
    }

    let cancelled = false;
    setState({ image: null, status: 'loading' });

    const img = new Image();
    img.onload = () => {
      if (!cancelled) {
        setState({ image: img, status: 'loaded' });
      }
    };
    img.onerror = () => {
      if (!cancelled) {
        setState({ image: null, status: 'error' });
      }
    };
    img.src = url;

    return () => {
      cancelled = true;
      img.onload = null;
      img.onerror = null;
    };
  }, [url]);

  return state;
}
