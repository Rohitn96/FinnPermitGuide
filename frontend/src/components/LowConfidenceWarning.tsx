import { AnswerQuality } from '@/types/chat';

/**
 * Shown when the knowledge base did not fully cover the question.
 *
 * The wording is deliberately specific to the reason. "This answer may be
 * incomplete" on every uncertain answer trains people to ignore the banner,
 * which defeats the point of having one.
 */
export default function LowConfidenceWarning({ quality }: { quality?: AnswerQuality }) {
  const message =
    quality === 'not_in_sources'
      ? 'My official sources do not cover this question. Please check with the authority named below.'
      : quality === 'partial'
        ? 'My sources only partly cover this question — the answer says what is missing.'
        : 'This answer may be incomplete. Please verify before acting on it.';

  return (
    <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-3 py-2 text-xs mb-2.5">
      <svg className="w-3.5 h-3.5 mt-0.5 shrink-0" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
        <path
          fillRule="evenodd"
          d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
          clipRule="evenodd"
        />
      </svg>
      <span>
        {message}{' '}
        <a
          href="https://migri.fi"
          target="_blank"
          rel="noopener noreferrer"
          className="underline font-medium"
        >
          migri.fi
        </a>{' '}
        · Migri 0295 419 700
      </span>
    </div>
  );
}
