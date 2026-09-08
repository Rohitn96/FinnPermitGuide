'use client';

import ReactMarkdown from 'react-markdown';

/**
 * Renders an answer's Markdown.
 *
 * The model is instructed to produce a narrow subset — paragraphs, bulleted and
 * numbered lists, bold for the values that matter — so the styling below covers
 * that subset deliberately rather than trying to be a general Markdown theme.
 * Headings and code blocks are mapped down to ordinary text: the prompt forbids
 * them, and if one slips through it should look like a stray sentence rather
 * than break the visual rhythm of the chat.
 */
export default function AnswerBody({ children }: { children: string }) {
  return (
    <div className="text-sm leading-relaxed text-gray-800 space-y-2.5">
      <ReactMarkdown
        components={{
          p: ({ children }) => <p className="leading-relaxed">{children}</p>,

          ul: ({ children }) => (
            <ul className="list-disc pl-5 space-y-1.5 marker:text-gray-400">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal pl-5 space-y-1.5 marker:text-gray-400">{children}</ol>
          ),
          li: ({ children }) => <li className="leading-relaxed pl-0.5">{children}</li>,

          // Bold carries the thresholds, deadlines and language levels — the
          // things people scroll back to find.
          strong: ({ children }) => (
            <strong className="font-semibold text-gray-900">{children}</strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,

          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#003399] underline underline-offset-2 hover:text-[#002277] break-words"
            >
              {children}
            </a>
          ),

          h1: ({ children }) => <p className="font-semibold text-gray-900">{children}</p>,
          h2: ({ children }) => <p className="font-semibold text-gray-900">{children}</p>,
          h3: ({ children }) => <p className="font-semibold text-gray-900">{children}</p>,

          code: ({ children }) => <span className="font-medium">{children}</span>,
          pre: ({ children }) => <div className="whitespace-pre-wrap">{children}</div>,

          hr: () => <hr className="border-gray-100" />,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-gray-200 pl-3 text-gray-600">
              {children}
            </blockquote>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
