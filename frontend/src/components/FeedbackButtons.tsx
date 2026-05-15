'use client';

interface Props {
  messageId: string;
  feedback: 'up' | 'down' | null;
  onFeedback: (id: string, vote: 'up' | 'down') => void;
}

export default function FeedbackButtons({ messageId, feedback, onFeedback }: Props) {
  return (
    <div className="flex items-center gap-1.5 mt-3 pt-2 border-t border-gray-100">
      <span className="text-xs text-gray-400 mr-0.5">Helpful?</span>
      <button
        onClick={() => onFeedback(messageId, 'up')}
        aria-label="Thumbs up"
        className={`p-1.5 rounded transition-colors ${
          feedback === 'up'
            ? 'text-emerald-600 bg-emerald-50'
            : 'text-gray-400 hover:text-emerald-600 hover:bg-emerald-50'
        }`}
      >
        <svg
          className="w-4 h-4"
          fill={feedback === 'up' ? 'currentColor' : 'none'}
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M6.633 10.5c.806 0 1.533-.446 2.031-1.08a9.041 9.041 0 012.861-2.4c.723-.384 1.35-.956 1.653-1.715a4.498 4.498 0 00.322-1.672V3a.75.75 0 01.75-.75A2.25 2.25 0 0116.5 4.5c0 1.152-.26 2.243-.723 3.218-.266.558.107 1.282.725 1.282h3.126c1.026 0 1.945.694 2.054 1.715.045.422.068.85.068 1.285a11.95 11.95 0 01-2.649 7.521c-.388.482-.987.729-1.605.729H13.48c-.483 0-.964-.078-1.423-.23l-3.114-1.04a4.501 4.501 0 00-1.423-.23H5.904"
          />
        </svg>
      </button>
      <button
        onClick={() => onFeedback(messageId, 'down')}
        aria-label="Thumbs down"
        className={`p-1.5 rounded transition-colors ${
          feedback === 'down'
            ? 'text-red-500 bg-red-50'
            : 'text-gray-400 hover:text-red-500 hover:bg-red-50'
        }`}
      >
        <svg
          className="w-4 h-4"
          fill={feedback === 'down' ? 'currentColor' : 'none'}
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M7.5 15h2.25m8.024-9.75c.011.05.028.1.052.148.591 1.2.924 2.55.924 3.977a8.96 8.96 0 01-.999 4.125m.023-8.25c-.076-.365.183-.75.575-.75h.908c.889 0 1.713.518 1.972 1.368.339 1.11.521 2.287.521 3.507 0 1.553-.295 3.036-.831 4.398C20.613 14.547 19.833 15 19 15h-1.053c-.472 0-.745-.556-.5-.96a8.95 8.95 0 00.303-.54m.023-8.25H16.48a4.5 4.5 0 01-1.423-.23l-3.114-1.04a4.5 4.5 0 00-1.423-.23H6.504c-.618 0-1.217.247-1.605.729A11.95 11.95 0 002.25 12c0 .139.007.278.02.416.052.636.556 1.136 1.199 1.2.23.022.461.034.695.034a.75.75 0 010 1.5"
          />
        </svg>
      </button>
    </div>
  );
}
