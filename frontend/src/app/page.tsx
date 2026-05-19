'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useChat } from '@/hooks/useChat';
import ChatBubble from '@/components/ChatBubble';

const STARTER_QUESTIONS = [
  'What are the requirements for permanent residence in Finland?',
  'What Kela benefits can I get on a work permit?',
  'How do I apply for Finnish citizenship?',
];

const CATEGORY_STARTERS: Record<string, string> = {
  'Residence Permits': 'What types of residence permits are available in Finland?',
  'Citizenship': 'What are the requirements to apply for Finnish citizenship?',
  'Kela Benefits': 'What Kela benefits can I get while on a residence permit?',
  'Work Permit': 'How do I get a work-based residence permit in Finland?',
  'Family Reunification': 'How do I apply to bring my family to Finland?',
  'Study': 'Can I work in Finland while studying on a student permit?',
  'Permanent Residence': 'When and how can I apply for permanent residence in Finland?',
  'DVV Registration': 'How do I register my address and identity with DVV?',
};


export default function Home() {
  const { messages, isLoading, sendMessage, submitFeedback, clearConversation } = useChat();
  const [input, setInput] = useState('');
  const [bannerVisible, setBannerVisible] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (sessionStorage.getItem('disclaimerAcknowledged')) {
      setBannerVisible(false);
    }
  }, []);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [input]);

  const handleSubmit = useCallback(
    (e?: React.FormEvent) => {
      e?.preventDefault();
      const q = input.trim();
      if (!q || isLoading) return;
      setInput('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
      sendMessage(q);
    },
    [input, isLoading, sendMessage],
  );

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function handleClear() {
    clearConversation();
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }

  return (
    <div className="flex flex-col h-full">

      {/* ── Header ─────────────────────────────────────────── */}
      <header className="bg-[#003399] text-white px-4 py-3 flex items-center gap-3 shrink-0 shadow-md z-10">
        <button
          onClick={handleClear}
          aria-label="Home — clear conversation"
          className="min-w-0 text-left hover:opacity-80 transition-opacity"
        >
          <h1 className="font-black text-lg leading-tight tracking-tight">FinnPermit Guide</h1>
          <p className="text-blue-200 text-xs font-medium">AI Assistant for Finnish Immigration</p>
        </button>

        <div className="ml-auto flex items-center gap-3 shrink-0">
          <Link
            href="/about"
            className="text-blue-200 hover:text-white text-xs font-medium transition-colors"
          >
            About
          </Link>
          <span className="bg-white text-[#003399] text-sm font-black px-3 py-1 rounded-full select-none tracking-tight shadow-sm">
            Unofficial · Beta
          </span>
          {messages.length > 0 && (
            <button
              onClick={handleClear}
              aria-label="Clear conversation"
              title="Clear conversation"
              className="p-1.5 rounded-md text-blue-200 hover:text-white hover:bg-[#002277] transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round"
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          )}
        </div>
      </header>

      {/* ── Disclaimer banner ──────────────────────────────── */}
      {bannerVisible && (
        <div className="shrink-0 bg-amber-50 border-b-2 border-amber-300 px-4 py-3 flex items-start gap-3">
          <svg className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd"
              d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
              clipRule="evenodd" />
          </svg>
          <div className="flex-1 min-w-0">
            <p className="text-amber-900 text-xs leading-snug">
              <strong className="font-bold">FinnPermit Guide is an independent tool and is not affiliated with, endorsed by, or connected to the Finnish Immigration Service (Migri), Kela, DVV, or any other Finnish government authority.</strong>{' '}
              Always verify information at official government websites.
            </p>
            <button
              onClick={() => {
                sessionStorage.setItem('disclaimerAcknowledged', '1');
                setBannerVisible(false);
              }}
              className="mt-2 text-xs font-semibold bg-amber-600 text-white rounded px-3 py-1 hover:bg-amber-700 transition-colors"
            >
              I understand
            </button>
          </div>
        </div>
      )}

      {/* ── Chat area ──────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="max-w-3xl mx-auto px-4 h-full flex flex-col items-center justify-center text-center gap-5 pb-8">
            {/* Large Finnish flag logo */}
            <div>
              <p className="font-semibold text-gray-800 text-lg">Ask about Finnish immigration</p>
              <p className="text-sm mt-1 text-gray-500 max-w-sm">
                Permits, Kela benefits, residency, citizenship — answered from official Finnish sources only.
              </p>
            </div>

            {/* Category chips */}
            <div className="flex flex-wrap gap-2 justify-center max-w-lg">
              {Object.entries(CATEGORY_STARTERS).map(([label, question]) => (
                <button
                  key={label}
                  onClick={() => {
                    setInput(question);
                    textareaRef.current?.focus();
                  }}
                  disabled={isLoading}
                  className="text-xs bg-blue-50 text-[#003399] border border-blue-200 rounded-full px-3 py-1.5 hover:bg-[#003399] hover:text-white transition-colors disabled:opacity-50"
                >
                  {label}
                </button>
              ))}
            </div>

            {/* Starter example questions */}
            <div className="flex flex-wrap gap-2 justify-center max-w-lg">
              {STARTER_QUESTIONS.map(q => (
                <button
                  key={q}
                  onClick={() => sendMessage(q)}
                  disabled={isLoading}
                  className="text-sm bg-white border border-gray-200 rounded-full px-4 py-2 text-gray-700 hover:border-[#003399] hover:text-[#003399] transition-colors shadow-sm disabled:opacity-50"
                >
                  {q}
                </button>
              ))}
            </div>

            {/* Language support signal */}
            <p className="text-xs text-gray-400">
              🌐 Ask in any language — Finnish, Arabic, Somali, русский, हिंदी, or any other
            </p>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
            {messages.map((msg, i) => (
              <ChatBubble
                key={msg.id}
                message={msg}
                onFeedback={submitFeedback}
                showFollowUps={
                  msg.role === 'assistant' && i === messages.length - 1 && !isLoading
                }
                onFollowUp={sendMessage}
              />
            ))}

            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-white border border-gray-100 rounded-2xl rounded-tl-none px-4 py-3 shadow-sm">
                  <div className="flex gap-1 items-center h-5">
                    {[0, 150, 300].map(delay => (
                      <div
                        key={delay}
                        className="w-2 h-2 bg-gray-300 rounded-full animate-bounce"
                        style={{ animationDelay: `${delay}ms` }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* ── Input bar ──────────────────────────────────────── */}
      <div className="shrink-0 border-t border-gray-200 bg-white px-4 py-3">
        <div className="max-w-3xl mx-auto">
          <form onSubmit={handleSubmit} className="flex items-end gap-2">
            <div className="flex-1 min-w-0 relative">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about permits, benefits, citizenship... (Enter to send, Shift+Enter for new line)"
                disabled={isLoading}
                rows={1}
                className="w-full resize-none border border-gray-300 rounded-2xl px-4 py-2.5 text-sm focus:outline-none focus:border-[#003399] focus:ring-2 focus:ring-[#003399]/20 disabled:opacity-50 transition leading-relaxed overflow-hidden"
                style={{ minHeight: '44px', maxHeight: '200px' }}
              />
            </div>
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              aria-label="Send"
              className="bg-[#003399] text-white rounded-full w-10 h-10 flex items-center justify-center hover:bg-[#002277] disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </form>
          <div className="mt-2 flex justify-center">
            <p className="text-[10px] font-bold text-[#003399] bg-blue-50 border border-blue-200 rounded-full px-3 py-1">
              Unofficial tool · Not legal advice · Always verify at{' '}
              <a href="https://migri.fi" target="_blank" rel="noopener noreferrer" className="underline">
                migri.fi
              </a>
            </p>
          </div>
        </div>
      </div>

      {/* ── Attribution footer ─────────────────────────────── */}
      <footer className="shrink-0 bg-white pb-2 pt-1 text-center border-t border-gray-100">
        <p className="text-[10px] text-gray-400 leading-relaxed">
          Built by{' '}
          <a
            href="https://linkedin.com/in/rohitn96"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-gray-600 transition-colors"
          >
            Rohit Nair
          </a>
          {' · '}
          <a
            href="https://github.com/Rohitn96"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-gray-600 transition-colors inline-flex items-center gap-0.5"
          >
            <svg className="w-2.5 h-2.5 inline" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
            </svg>
            {' '}GitHub
          </a>
          {' · '}
          <Link href="/about" className="underline hover:text-gray-600 transition-colors">
            About
          </Link>
          {' · '}
          FinnPermit Guide is an independent tool, not affiliated with the Finnish Immigration Service (Migri)
        </p>
      </footer>

      {/* ── Data freshness badge (fixed) ────────────────────── */}
      <div className="fixed bottom-36 right-3 z-20 pointer-events-none">
        <span className="text-[10px] text-gray-500 bg-white/90 border border-gray-200 rounded-full px-2.5 py-1 shadow-sm">
          📅 Data: May 2026
        </span>
      </div>

    </div>
  );
}
