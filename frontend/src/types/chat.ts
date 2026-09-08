export interface HistoryMessage {
  role: 'human' | 'ai';
  content: string;
}

export interface Source {
  url: string;
  title: string;
  domain: string;
  /** Human-readable authority name, e.g. "Finnish Immigration Service (Migri)". */
  authority?: string;
}

/** How well the knowledge base covered the question. */
export type AnswerQuality =
  | 'complete'
  | 'partial'
  | 'needs_clarification'
  | 'not_in_sources';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  /** Markdown for assistant messages, plain text for user messages. */
  content: string;
  sources?: Source[];
  category?: string | null;
  quality?: AnswerQuality;
  lowConfidence?: boolean;
  followUps?: string[];
  feedback?: 'up' | 'down' | null;
}

export interface AskResponse {
  answer: string;
  sources: Source[];
  category: string | null;
  quality: AnswerQuality;
  low_confidence: boolean;
  follow_ups: string[];
  chat_history: HistoryMessage[];
}
