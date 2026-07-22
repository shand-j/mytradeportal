import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

import { useIsMobile } from './use-mobile';

describe('useIsMobile', () => {
  let listeners: Array<(event: Event) => void> = [];

  beforeEach(() => {
    listeners = [];

    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: window.innerWidth < 768,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: (event: string, cb: EventListener) => {
          if (event === 'change') listeners.push(cb as (event: Event) => void);
        },
        removeEventListener: (event: string, cb: EventListener) => {
          if (event === 'change') {
            listeners = listeners.filter((l) => l !== cb);
          }
        },
        dispatchEvent: (event: Event) => {
          listeners.forEach((l) => l(event));
          return true;
        },
      })),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns true when the viewport is narrower than the mobile breakpoint', () => {
    window.innerWidth = 640;
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(true);
  });

  it('returns false when the viewport is wider than the mobile breakpoint', () => {
    window.innerWidth = 1024;
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);
  });

  it('updates when the media query changes', async () => {
    window.innerWidth = 1024;
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);

    window.innerWidth = 375;
    act(() => {
      window.matchMedia('(max-width: 767px)').dispatchEvent(new Event('change'));
    });

    await waitFor(() => {
      expect(result.current).toBe(true);
    });
  });
});
