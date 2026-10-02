"use client";

import { useEffect, useState, useCallback } from "react";

/**
 * Hook that enforces fullscreen mode during the interview.
 * Shows a warning modal when the user tries to exit fullscreen.
 */
export function useFullscreen() {
  const [showWarning, setShowWarning] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const enterFullscreen = useCallback(async () => {
    try {
      const el = document.documentElement;
      if (el.requestFullscreen) {
        await el.requestFullscreen();
      } else if ((el as any).webkitRequestFullscreen) {
        await (el as any).webkitRequestFullscreen();
      } else if ((el as any).msRequestFullscreen) {
        await (el as any).msRequestFullscreen();
      }
    } catch (err) {
      console.warn("Fullscreen request failed:", err);
    }
  }, []);

  const exitFullscreen = useCallback(async () => {
    try {
      if (document.exitFullscreen) {
        await document.exitFullscreen();
      } else if ((document as any).webkitExitFullscreen) {
        await (document as any).webkitExitFullscreen();
      } else if ((document as any).msExitFullscreen) {
        await (document as any).msExitFullscreen();
      }
    } catch (err) {
      console.warn("Exit fullscreen failed:", err);
    }
  }, []);

  useEffect(() => {
    const handleFullscreenChange = () => {
      const currentlyFullscreen = !!(
        document.fullscreenElement ||
        (document as any).webkitFullscreenElement ||
        (document as any).msFullscreenElement
      );
      setIsFullscreen(currentlyFullscreen);

      // If user exited fullscreen and interview is active, show warning
      if (!currentlyFullscreen && sessionStorage.getItem("interview_active") === "true") {
        setShowWarning(true);
      }
    };

    const handleVisibilityChange = () => {
      // If user switches tabs (document hidden) and interview is active, show warning
      if (document.hidden && sessionStorage.getItem("interview_active") === "true") {
        setShowWarning(true);
      }
    };

    document.addEventListener("fullscreenchange", handleFullscreenChange);
    document.addEventListener("webkitfullscreenchange", handleFullscreenChange);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    // Check initial state
    const currentlyFullscreen = !!(
      document.fullscreenElement ||
      (document as any).webkitFullscreenElement
    );
    setIsFullscreen(currentlyFullscreen);

    // If interview is active but not fullscreen, re-enter
    if (!currentlyFullscreen && sessionStorage.getItem("interview_active") === "true") {
      enterFullscreen();
    }

    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
      document.removeEventListener("webkitfullscreenchange", handleFullscreenChange);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [enterFullscreen]);

  const dismissWarning = useCallback(() => {
    setShowWarning(false);
    enterFullscreen();
  }, [enterFullscreen]);

  return { isFullscreen, showWarning, dismissWarning, enterFullscreen, exitFullscreen };
}
