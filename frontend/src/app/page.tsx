'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import { useChat } from '@/hooks/useChat';
import ChatBubble from '@/components/ChatBubble';

const STARTER_QUESTIONS = [
  'What are the requirements for permanent residence in Finland?',
  'What Kela benefits can I get on a work permit?',
  'How do I apply for Finnish citizenship?',
];

export default function Home() {
  const { messages, isLoading, sendMessage, submitFeedback, clearConversation } = useChat();
  const [input, setInput] = useState('');
  const [bannerVisible, setBannerVisible] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // Auto-resize textarea as user types
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
      // Reset textarea height after clearing
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
        {/* Logo — click to return to home / clear conversation */}
        <button
          onClick={handleClear}
          aria-label="Home — clear conversation"
          className="w-9 h-9 bg-white rounded-full flex items-center justify-center shrink-0 hover:bg-blue-100 transition-colors"
        >
          <span className="text-[#003399] font-bold text-sm select-none">MG</span>
        </button>

        <div className="min-w-0">
          <h1 className="font-semibold text-base leading-tight">MigriGuide</h1>
          <p className="text-blue-200 text-xs">Finnish Immigration Assistant</p>
        </div>

        <div className="ml-auto flex items-center gap-2 shrink-0">
          <span className="bg-[#002277] text-blue-200 text-xs px-2 py-0.5 rounded select-none">
            Unofficial · Beta
          </span>

          {/* Clear conversation button */}
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
        <div className="shrink-0 bg-amber-50 border-b border-amber-200 px-4 py-2.5 flex items-start gap-3">
          <svg className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd"
              d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
              clipRule="evenodd" />
          </svg>
          <p className="text-amber-800 text-xs leading-snug flex-1">
            <strong>MigriGuide is not a lawyer and does not provide legal advice.</strong>{' '}
            All answers come from official Finnish sources only. Always verify important information at{' '}
            <a href="https://migri.fi" target="_blank" rel="noopener noreferrer"
              className="underline font-medium">migri.fi</a>{' '}
            or consult a licensed professional.
          </p>
          <button
            onClick={() => setBannerVisible(false)}
            aria-label="Dismiss disclaimer"
            className="text-amber-500 hover:text-amber-700 transition-colors shrink-0 mt-0.5"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* ── Chat area ──────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          /* Empty state — centered within max-w-3xl */
          <div className="max-w-3xl mx-auto px-4 h-full flex flex-col items-center justify-center text-center gap-5 pb-8">
            <div className="w-16 h-16 bg-[#003399] rounded-full flex items-center justify-center shadow-lg">
              <span className="text-white text-2xl font-bold select-none">MG</span>
            </div>
            <div>
              <p className="font-semibold text-gray-800 text-lg">Ask about Finnish immigration</p>
              <p className="text-sm mt-1 text-gray-500 max-w-sm">
                Permits, Kela benefits, residency, citizenship — answered from official Finnish sources only.
              </p>
            </div>
            <div className="flex flex-wrap gap-2 justify-center mt-1 max-w-lg">
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
          </div>
        ) : (
          /* Messages — same max-w-3xl container as input bar */
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
          <p className="text-center text-[10px] text-gray-400 mt-2">
            Unofficial tool · Not legal advice · Always verify at{' '}
            <a href="https://migri.fi" target="_blank" rel="noopener noreferrer" className="underline">
              migri.fi
            </a>
          </p>
        </div>
      </div>

    </div>
  );
}
