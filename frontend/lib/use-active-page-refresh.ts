"use client";

import { useEffect, useRef } from "react";

/**
 * Revalidate visible page data when the user returns to a cached route or
 * switches back to the browser tab. The callback ref avoids re-registering
 * global listeners every render; callers should keep their current UI visible
 * while the background refresh is in flight.
 */
export function useActivePageRefresh(
  isActive: boolean,
  enabled: boolean,
  refresh: () => void | Promise<void>,
): void {
  const refreshRef = useRef(refresh);
  const activeRef = useRef(isActive && enabled);
  const wasActiveRef = useRef(isActive);
  const lastRefreshAt = useRef(0);

  useEffect(() => {
    refreshRef.current = refresh;
  }, [refresh]);

  useEffect(() => {
    const wasActive = wasActiveRef.current;
    wasActiveRef.current = isActive;
    activeRef.current = isActive && enabled;

    if (!wasActive && isActive && enabled) {
      void refreshRef.current();
    }
  }, [enabled, isActive]);

  useEffect(() => {
    const refreshWhenVisible = () => {
      if (!activeRef.current || document.visibilityState !== "visible") return;
      const now = Date.now();
      if (now - lastRefreshAt.current < 500) return;
      lastRefreshAt.current = now;
      void refreshRef.current();
    };

    window.addEventListener("focus", refreshWhenVisible);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.removeEventListener("focus", refreshWhenVisible);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, []);
}