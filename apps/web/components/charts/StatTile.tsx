// Stat tile per the dataviz skill's figure contract: label (sentence case, no
// trailing colon) + value (semibold, auto-compact) + optional delta (signed,
// color = direction x whether up is good).
interface StatTileProps {
  label: string;
  value: string;
  delta?: { text: string; direction: "up" | "down"; goodDirection: "up" | "down" };
}

export function StatTile({ label, value, delta }: StatTileProps) {
  const deltaIsGood = delta && delta.direction === delta.goodDirection;
  return (
    <div className="card p-3.5 md:p-4 flex flex-col gap-1">
      <span className="text-xs md:text-sm text-[var(--text-secondary)]">{label}</span>
      <span className="text-2xl md:text-3xl font-semibold text-[var(--text-primary)] tabular">{value}</span>
      {delta && (
        <span
          className="text-sm tabular"
          style={{ color: deltaIsGood ? "var(--status-good)" : "var(--status-critical)" }}
        >
          {delta.direction === "up" ? "▲" : "▼"} {delta.text}
        </span>
      )}
    </div>
  );
}
