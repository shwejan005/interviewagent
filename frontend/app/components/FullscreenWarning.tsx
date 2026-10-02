"use client";

interface FullscreenWarningProps {
  show: boolean;
  onDismiss: () => void;
}

export default function FullscreenWarning({ show, onDismiss }: FullscreenWarningProps) {
  if (!show) return null;

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 p-8 max-w-md mx-4 text-center animate-in fade-in zoom-in duration-200">
        {/* Warning icon */}
        <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
          <svg
            className="w-8 h-8 text-red-600 dark:text-red-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
            />
          </svg>
        </div>

        <h3 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-2">
          Fullscreen Required
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-6 leading-relaxed">
          You cannot exit fullscreen during the interview. Exiting fullscreen may be flagged as a violation. Please return to fullscreen to continue.
        </p>

        <button
          onClick={onDismiss}
          className="w-full py-3 px-6 rounded-lg bg-red-600 hover:bg-red-700 text-white font-semibold text-sm transition-colors"
        >
          Return to Fullscreen
        </button>
      </div>
    </div>
  );
}
