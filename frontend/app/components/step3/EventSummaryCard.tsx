interface EventSummaryCardProps {
  eventSummary: string;
}

export default function EventSummaryCard({ eventSummary }: EventSummaryCardProps) {
  if (!eventSummary) return null;

  return (
    <div className="mt-16 rounded-[18px] border border-amber-300/30 bg-amber-100/10 p-4 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur-sm">
      <p className="font-semibold text-amber-900">{eventSummary}</p>
    </div>
  );
}
