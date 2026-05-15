interface Props {
  questions: string[];
  onSelect: (q: string) => void;
}

export default function FollowUpChips({ questions, onSelect }: Props) {
  return (
    <div className="flex flex-wrap gap-2 mt-1">
      {questions.map(q => (
        <button
          key={q}
          onClick={() => onSelect(q)}
          className="text-xs bg-white border border-[#003399] text-[#003399] rounded-full px-3 py-1.5 hover:bg-[#003399] hover:text-white transition-colors"
        >
          {q}
        </button>
      ))}
    </div>
  );
}
