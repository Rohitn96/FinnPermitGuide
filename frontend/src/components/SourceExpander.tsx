'use client';

import { useState } from 'react';
import { Source } from '@/types/chat';

/**
 * The authorities the knowledge base is built from. Keys are the `domain` tag
 * set by pipeline/process.py — keep this in sync with AUTHORITIES there, or new
 * sources render as unlabelled grey badges.
 */
const AUTHORITIES: Record<string, { label: string; style: string }> = {
  MIGRI:           { label: 'MIGRI',  style: 'bg-blue-100 text-blue-800 border-blue-200' },
  KELA:            { label: 'KELA',   style: 'bg-green-100 text-green-800 border-green-200' },
  DVV:             { label: 'DVV',    style: 'bg-orange-100 text-orange-800 border-orange-200' },
  VERO:            { label: 'VERO',   style: 'bg-indigo-100 text-indigo-800 border-indigo-200' },
  POLIISI:         { label: 'POLICE', style: 'bg-slate-200 text-slate-800 border-slate-300' },
  TULLI:           { label: 'CUSTOMS',style: 'bg-yellow-100 text-yellow-800 border-yellow-200' },
  TYOSUOJELU:      { label: 'WORK',   style: 'bg-rose-100 text-rose-800 border-rose-200' },
  TYOMARKKINATORI: { label: 'JOBS',   style: 'bg-cyan-100 text-cyan-800 border-cyan-200' },
  INFOFINLAND:     { label: 'INFO',   style: 'bg-teal-100 text-teal-800 border-teal-200' },
  IHH:             { label: 'IHH',    style: 'bg-purple-100 text-purple-800 border-purple-200' },
  SUOMI:           { label: 'SUOMI',  style: 'bg-sky-100 text-sky-800 border-sky-200' },
  ENTERFINLAND:    { label: 'ENTER',  style: 'bg-lime-100 text-lime-800 border-lime-200' },
  PDF:             { label: 'LAW',    style: 'bg-stone-200 text-stone-800 border-stone-300' },
};

const FALLBACK = { label: 'GOV', style: 'bg-gray-100 text-gray-600 border-gray-200' };

function badge(domain: string) {
  return AUTHORITIES[domain.toUpperCase().replace(/[^A-Z]/g, '')] ?? FALLBACK;
}

export default function SourceExpander({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-3 pt-2 border-t border-gray-100">
      <button
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 transition-colors"
      >
        <svg
          className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-90' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        <span>
          {sources.length} official source{sources.length > 1 ? 's' : ''}
        </span>
      </button>

      {open && (
        <ul className="mt-2 space-y-1.5">
          {sources.map(src => {
            const { label, style } = badge(src.domain);
            return (
              <li key={src.url} className="flex items-start gap-2">
                <span
                  // The full authority name is the useful bit but too long for a
                  // badge on a phone, so it lives in the tooltip instead.
                  title={src.authority || src.domain}
                  className={`shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded border ${style}`}
                >
                  {label}
                </span>
                <a
                  href={src.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-600 hover:underline leading-tight break-all"
                >
                  {src.title || src.url}
                </a>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
