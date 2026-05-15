'use client';

import { useState, useCallback } from 'react';
import { ChatMessage, HistoryMessage, AskResponse } from '@/types/chat';

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatHistory, setChatHistory] = useState<HistoryMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);

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

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const data: AskResponse = await res.json();

        const aiMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: data.answer,
          sources: data.sources,
          category: data.category,
          lowConfidence: data.low_confidence,
          followUps: data.follow_ups,
          feedback: null,
        };

        setMessages(prev => [...prev, aiMsg]);
        setChatHistory(data.chat_history);
      } catch {
        setMessages(prev => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: 'Something went wrong. Please try again.',
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
        const msg = messages.find(m => m.id === messageId);
        await fetch('/api/feedback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message_id: messageId,
            vote,
            answer: msg?.content ?? '',
          }),
        });
      } catch {
        // Non-critical
      }
    },
    [messages],
  );

  return { messages, isLoading, sendMessage, submitFeedback };
}
