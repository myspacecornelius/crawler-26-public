'use client';

/**
 * SkipLink — accessibility component that lets keyboard users skip to main content.
 * Should be the first focusable element in the page layout.
 */
export default function SkipLink({ targetId = 'main-content' }: { targetId?: string }) {
  return (
    <a
      href={`#${targetId}`}
      className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[200] focus:px-4 focus:py-2 focus:bg-brand-600 focus:text-white focus:rounded-lg focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-brand-400 focus:ring-offset-2 focus:ring-offset-gray-900 text-sm font-medium"
    >
      Skip to main content
    </a>
  );
}
