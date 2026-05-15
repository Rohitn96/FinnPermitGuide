import CategoryTag from './CategoryTag';
import LowConfidenceWarning from './LowConfidenceWarning';
import SourceExpander from './SourceExpander';
import FeedbackButtons from './FeedbackButtons';
import FollowUpChips from './FollowUpChips';
import { ChatMessage } from '@/types/chat';

interface Props {
  message: ChatMessage;
  onFeedback: (id: string, vote: 'up' | 'down') => void;
  showFollowUps?: boolean;
  onFollowUp: (q: string) => void;
}

export default function ChatBubble({ message, onFeedback, showFollowUps, onFollowUp }: Props) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="bg-[#003399] text-white rounded-2xl rounded-tr-none px-4 py-3 max-w-[80%] text-sm leading-relaxed">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 max-w-[88%]">
      <div className="bg-white border border-gray-100 rounded-2xl rounded-tl-none px-4 py-3 shadow-sm text-sm leading-relaxed text-gray-800">
        {message.category && <CategoryTag category={message.category} />}
        {message.lowConfidence && <LowConfidenceWarning />}
        <div className="whitespace-pre-wrap">{message.content}</div>
        {message.sources && message.sources.length > 0 && (
          <SourceExpander sources={message.sources} />
        )}
        <FeedbackButtons
          messageId={message.id}
          feedback={message.feedback ?? null}
          onFeedback={onFeedback}
        />
      </div>
      {showFollowUps && message.followUps && message.followUps.length > 0 && (
        <FollowUpChips questions={message.followUps} onSelect={onFollowUp} />
      )}
    </div>
  );
}
