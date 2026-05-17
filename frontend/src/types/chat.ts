export interface HistoryMessage {
  role: 'human' | 'ai';
  content: string;
}

export interface Source {
  url: string;
  title: string;
  domain: string;
  category: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  category?: string | null;
  lowConfidence?: boolean;
  followUps?: string[];
  feedback?: 'up' | 'down' | null;
  responseType?: string | null;
}

export interface AskResponse {
  answer: string;
  sources: Source[];
  category: string | null;
  low_confidence: boolean;
  chat_history: HistoryMessage[];
  follow_ups: string[];
  response_type?: string | null;
}
