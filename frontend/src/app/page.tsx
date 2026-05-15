'use client';

import { useRef, useEffect, useState } from 'react';
import { useChat } from '@/hooks/useChat';
import ChatBubble from '@/components/ChatBubble';

const STARTER_QUESTIONS = [
  'What are the requirements for permanent residence?',
  'Can I get Kela benefits on a work permit?',
  'How do I apply for Finnish citizenship?',
];

export default function Home() {
  const { messages, isLoading, sendMessage, submitFeedback } = useChat();
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const q = input.trim();
    if (!q || isLoading) return;
    setInput('');
    sendMessage(q);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="bg-[#003399] text-white px-4 py-3 flex items-center gap-3 shrink-0 shadow-md z-10">
        <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center shrink-0">
          <span className="text-[#003399] font-bold text-sm select-none">MG</span>
        </div>
        <div className="min-w-0">
          <h1 className="font-semibold text-base leading-tight">MigriGuide</h1>
          <p className="text-blue-200 text-xs">Finnish Immigration Assistant</p>
        </div>
        <div className="ml-auto shrink-0">
          <span className="bg-[#002277] text-blue-200 text-xs px-2 py-0.5 rounded">
            Unofficial · Beta
          </span>
        </div>
      </header>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center gap-5 pb-8">
            <div className="w-16 h-16 bg-[#003399] rounded-full flex items-center justify-center shadow-lg">
              <span className="text-white text-2xl font-bold select-none">MG</span>
            </div>
            <div>
              <p className="font-semibold text-gray-800 text-lg">Ask about Finnish immigration</p>
              <p className="text-sm mt-1 text-gray-500 max-w-sm">
                Permits, Kela benefits, residency, citizenship — answered from official sources only.
              </p>
            </div>
            <div className="flex flex-wrap gap-2 justify-center mt-1 max-w-md">
              {STARTER_QUESTIONS.map(q => (
                <button
                  key={q}
                  onClick={() => sendMessage(q)}
                  className="text-sm bg-white border border-gray-200 rounded-full px-4 py-2 text-gray-700 hover:border-[#003399] hover:text-[#003399] transition-colors shadow-sm"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="max-w-2xl mx-auto space-y-4">
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
                  <div className="flex gap-1 items-center h-4">
                    {[0, 150, 300].map(delay => (
                      <div
                        key={delay}
                        className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
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

      {/* Disclaimer */}
      <p className="text-center text-[11px] text-gray-400 px-4 pb-1 shrink-0">
        Unofficial tool · Not legal advice · Always verify at{' '}
        <a
          href="https://migri.fi"
          target="_blank"
          rel="noopener noreferrer"
          className="underline"
        >
          migri.fi
        </a>
      </p>

      {/* Input bar */}
      <form
        onSubmit={handleSubmit}
        className="shrink-0 border-t border-gray-200 bg-white px-4 py-3 flex gap-2"
      >
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Ask about permits, benefits, citizenship..."
          disabled={isLoading}
          className="flex-1 min-w-0 border border-gray-300 rounded-full px-4 py-2.5 text-sm focus:outline-none focus:border-[#003399] focus:ring-2 focus:ring-[#003399]/20 disabled:opacity-50 transition"
        />
        <button
          type="submit"
          disabled={isLoading || !input.trim()}
          aria-label="Send"
          className="bg-[#003399] text-white rounded-full w-10 h-10 flex items-center justify-center hover:bg-[#002277] disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
            />
          </svg>
        </button>
      </form>
    </div>
  );
}
