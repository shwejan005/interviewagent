import { toast } from "sonner";

/**
 * Single entry point for transient feedback. Every page should call these
 * instead of rendering its own inline alert banner — the visual treatment
 * (bottom-right, dark glass, auto-dismiss) lives once in layout.tsx.
 */
export const notify = {
  success: (message: string, description?: string) => toast.success(message, { description }),
  error: (message: string, description?: string) => toast.error(message, { description }),
  info: (message: string, description?: string) => toast(message, { description }),
  warning: (message: string, description?: string) => toast.warning(message, { description }),
};
