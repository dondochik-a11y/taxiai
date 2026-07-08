// Part-to-whole cost breakdown -> horizontal bars (long Russian category
// names). Categorical palette, but every bar carries a direct text label too
// (not color-alone) since 5-6 series sits in the CVD floor band per the
// validator run for this palette.
const CATEGORY_COLORS = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
  "var(--series-4)",
  "var(--series-5)",
  "var(--series-6)",
];

export interface CostItem {
  label: string;
  value: number;
}

export function CostBreakdownBars({ title, items }: { title: string; items: CostItem[] }) {
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <div className="rounded-lg border border-white/10 bg-[var(--surface-1)] p-4 flex flex-col gap-3">
      <h3 className="text-sm text-[var(--text-secondary)]">{title}</h3>
      {items.map((item, i) => (
        <div key={item.label} className="flex items-center gap-2">
          <span className="w-28 text-xs text-[var(--text-secondary)] shrink-0">{item.label}</span>
          <div className="flex-1 h-4 rounded-sm bg-[var(--gridline)] overflow-hidden">
            <div
              className="h-full rounded-sm"
              style={{ width: `${(item.value / max) * 100}%`, background: CATEGORY_COLORS[i % CATEGORY_COLORS.length] }}
            />
          </div>
          <span className="w-16 text-xs text-right tabular text-[var(--text-primary)]">
            {item.value.toFixed(0)} ₽
          </span>
        </div>
      ))}
    </div>
  );
}
