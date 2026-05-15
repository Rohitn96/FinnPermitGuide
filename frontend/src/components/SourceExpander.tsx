'use client';

import { useState } from 'react';
import { Source } from '@/types/chat';

const DOMAIN_STYLES: Record<string, string> = {
  MIGRI:         'bg-blue-100 text-blue-800 border-blue-200',
  KELA:          'bg-green-100 text-green-800 border-green-200',
  DVV:           'bg-orange-100 text-orange-800 border-orange-200',
  VERO:          'bg-indigo-100 text-indigo-800 border-indigo-200',
  INFOFINLAND:   'bg-teal-100 text-teal-800 border-teal-200',
  IHH:           'bg-purple-100 text-purple-800 border-purple-200',
  WORKFINLAND:   'bg-amber-100 text-amber-800 border-amber-200',
  WORKINFINLAND: 'bg-amber-100 text-amber-800 border-amber-200',
  TE:            'bg-cyan-100 text-cyan-800 border-cyan-200',
};

function domainKey(domain: string): string {
  return domain.toUpperCase().replace(/[^A-Z]/g, '');
}

function domainStyle(domain: string): string {
  return DOMAIN_STYLES[domainKey(domain)] ?? 'bg-gray-100 text-gray-600 border-gray-200';
}

function shortLabel(domain: string): string {
  const key = domainKey(domain);
  if (key === 'INFOFINLAND') return 'INFO';
  if (key === 'WORKFINLAND' || key === 'WORKINFINLAND') return 'WORK';
  return key || domain.toUpperCase();
}

export default function SourceExpander({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-3 pt-2 border-t border-gray-100">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 transition-colors"
      >
        <svg
          className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-90' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        <span>
          {sources.length} official source{sources.length > 1 ? 's' : ''}
        </span>
      </button>

      {open && (
        <ul className="mt-2 space-y-1.5">
          {sources.map(src => (
            <li key={src.url} className="flex items-start gap-2">
              <span
                className={`shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded border ${domainStyle(src.domain)}`}
              >
                {shortLabel(src.domain)}
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
          ))}
        </ul>
      )}
    </div>
  );
}
