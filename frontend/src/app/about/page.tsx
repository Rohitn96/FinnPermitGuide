import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'About — FinnPermit Guide',
  description:
    'FinnPermit Guide — A free AI assistant for Finnish immigration questions. Not affiliated with the Finnish Immigration Service (Migri).',
};


export default function AboutPage() {
  return (
    <div className="min-h-full bg-gray-50 flex flex-col">

      {/* ── Header ─────────────────────────────────────────── */}
      <header className="bg-[#003399] text-white px-4 py-3 flex items-center gap-3 shadow-md shrink-0">
        <div className="min-w-0">
          <p className="font-black text-lg leading-tight tracking-tight">FinnPermit Guide</p>
          <p className="text-blue-200 text-xs font-medium">About this tool</p>
        </div>
        <div className="ml-auto shrink-0">
          <Link
            href="/"
            className="text-blue-200 hover:text-white text-xs font-medium transition-colors"
          >
            ← Back to Chat
          </Link>
        </div>
      </header>

      {/* ── Content ────────────────────────────────────────── */}
      <main className="flex-1 max-w-2xl mx-auto w-full px-4 py-8 space-y-8">

        {/* Section 1 — What is FinnPermit Guide? */}
        <section>
          <h2 className="text-base font-bold text-gray-800 mb-2">What is FinnPermit Guide?</h2>
          <p className="text-sm text-gray-600 leading-relaxed">
            FinnPermit Guide is a free AI assistant that answers questions about Finnish immigration, Kela
            benefits, DVV registration, and tax obligations. All answers are sourced exclusively from
            official Finnish government websites:{' '}
            <a href="https://migri.fi" target="_blank" rel="noopener noreferrer" className="text-[#003399] underline">migri.fi</a>,{' '}
            <a href="https://kela.fi" target="_blank" rel="noopener noreferrer" className="text-[#003399] underline">kela.fi</a>,{' '}
            <a href="https://vero.fi" target="_blank" rel="noopener noreferrer" className="text-[#003399] underline">vero.fi</a>,{' '}
            <a href="https://dvv.fi" target="_blank" rel="noopener noreferrer" className="text-[#003399] underline">dvv.fi</a>, and{' '}
            <a href="https://infofinland.fi" target="_blank" rel="noopener noreferrer" className="text-[#003399] underline">infofinland.fi</a>.
          </p>
        </section>

        {/* Section 2 — How does it work? */}
        <section>
          <h2 className="text-base font-bold text-gray-800 mb-2">How does it work?</h2>
          <p className="text-sm text-gray-600 leading-relaxed">
            FinnPermit Guide uses Retrieval-Augmented Generation (RAG). When you ask a question, it searches
            1,543 text chunks scraped from official Finnish government sources, finds the most relevant
            information, and generates a plain-English answer with citations. It does not guess — if it
            cannot find a sourced answer, it says so.
          </p>
        </section>

        {/* Section 3 — What it is not */}
        <section>
          <h2 className="text-base font-bold text-gray-800 mb-2">What it is not</h2>
          <ul className="space-y-2">
            {[
              'Not an official Migri service',
              'Not legal advice',
              'Not a substitute for consulting a licensed immigration lawyer for complex cases',
              'Not always up to date — data was last ingested May 2026',
            ].map(item => (
              <li key={item} className="flex items-start gap-2 text-sm text-gray-600">
                <span className="text-red-400 mt-0.5 shrink-0 font-bold">✕</span>
                {item}
              </li>
            ))}
          </ul>
        </section>

        {/* Section 4 — Privacy */}
        <section>
          <h2 className="text-base font-bold text-gray-800 mb-2">Privacy</h2>
          <p className="text-sm text-gray-600 leading-relaxed">
            FinnPermit Guide logs anonymised conversation sessions to improve answer quality. No personally
            identifiable information is required to use this tool. Do not include your personal case
            numbers, passport numbers, or other sensitive identifiers in your questions.
          </p>
        </section>

        {/* Section 5 — Built by */}
        <section>
          <h2 className="text-base font-bold text-gray-800 mb-2">Built by</h2>
          <p className="text-sm text-gray-600 leading-relaxed">
            FinnPermit Guide was built independently by Rohit Nair, an AI and data professional based in
            Helsinki.
          </p>
          <div className="flex items-center gap-3 mt-3">
            <a
              href="https://linkedin.com/in/rohitn96"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-[#003399] bg-blue-50 border border-blue-200 rounded-full px-3 py-1.5 hover:bg-[#003399] hover:text-white transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
              </svg>
              LinkedIn
            </a>
            <a
              href="https://github.com/Rohitn96"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-gray-700 bg-gray-100 border border-gray-200 rounded-full px-3 py-1.5 hover:bg-gray-800 hover:text-white transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
              </svg>
              GitHub
            </a>
          </div>
        </section>

        {/* Section 6 — Contact */}
        <section>
          <h2 className="text-base font-bold text-gray-800 mb-2">Contact</h2>
          <p className="text-sm text-gray-600 leading-relaxed">
            Have feedback, found an error, or want to collaborate? Email:{' '}
            <a
              href="mailto:rohitnair1111996@gmail.com"
              className="text-[#003399] underline hover:text-[#002277] transition-colors"
            >
              rohitnair1111996@gmail.com
            </a>
          </p>
        </section>

        <div className="pt-4 border-t border-gray-200">
          <p className="text-xs text-gray-400 text-center">
            FinnPermit Guide is an independent tool, not affiliated with the Finnish Immigration Service (Migri), Kela, DVV, or any Finnish government body.
          </p>
        </div>
      </main>

      {/* ── Footer ─────────────────────────────────────────── */}
      <footer className="shrink-0 pb-4 text-center">
        <Link
          href="/"
          className="text-xs text-[#003399] hover:underline transition-colors"
        >
          ← Back to FinnPermit Guide Chat
        </Link>
      </footer>

    </div>
  );
}
