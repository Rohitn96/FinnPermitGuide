'use client';

import { useState, useCallback, useRef } from 'react';
import { ChatMessage, HistoryMessage, AskResponse } from '@/types/chat';

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatHistory, setChatHistory] = useState<HistoryMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Keep a ref to messages so submitFeedback always sees the current list
  // without needing messages in its dependency array (avoids stale closure).
  const messagesRef = useRef<ChatMessage[]>([]);
  messagesRef.current = messages;

  const sendMessage = useCallback(
    async (question: string) => {
      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content: question,
      };
      setMessages(prev => [...prev, userMsg]);
      setIsLoading(true);

      try {
        const res = await fetch('/api/ask', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question, chat_history: chatHistory }),
        });

        if (!res.ok) {
          // Surface the backend's own message (rate limit, length cap) instead
          // of a generic failure. Pydantic 422s put an array in `detail`, so
          // only a plain string is safe to show.
          const errBody = await res.json().catch(() => null);
          const detail = typeof errBody?.detail === 'string' ? errBody.detail : null;
          throw new Error(detail ?? 'Something went wrong. Please try again.');
        }

        const data: AskResponse = await res.json();

        const aiMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: data.answer,
          sources: data.sources,
          category: data.category,
          quality: data.quality,
          lowConfidence: data.low_confidence,
          followUps: data.follow_ups,
          feedback: null,
        };

        setMessages(prev => [...prev, aiMsg]);
        setChatHistory(data.chat_history);
      } catch (err) {
        setMessages(prev => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: 'assistant',
            content:
              err instanceof Error && err.message
                ? err.message
                : 'Something went wrong. Please try again.',
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [chatHistory],
  );

  const submitFeedback = useCallback(
    async (messageId: string, vote: 'up' | 'down') => {
      setMessages(prev =>
        prev.map(m => (m.id === messageId ? { ...m, feedback: vote } : m)),
      );
      try {
        const index = messagesRef.current.findIndex(m => m.id === messageId);
        const msg = messagesRef.current[index];
        // A vote only means something alongside the question that produced the
        // answer, so send the user turn immediately preceding it.
        const question = index > 0 ? messagesRef.current[index - 1].content : '';
        await fetch('/api/feedback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message_id: messageId,
            vote,
            question,
            answer: msg?.content ?? '',
          }),
        });
      } catch {
        // Non-critical
      }
    },
    [],
  );

  const clearConversation = useCallback(() => {
    setMessages([]);
    setChatHistory([]);
    setIsLoading(false);
  }, []);

  return { messages, isLoading, sendMessage, submitFeedback, clearConversation };
}
