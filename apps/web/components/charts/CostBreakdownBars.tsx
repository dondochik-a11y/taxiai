// Part-to-whole cost breakdown -> horizontal bars (long Russian category
// names). Every bar carries a direct ₽ label, so color is redundant: a single
// hue reads as one metric, and the largest cost is emphasized (full opacity)
// while the rest recede — no 6-hue rainbow to decode.
export interface CostItem {
  label: string;
  value: number;
}

export function CostBreakdownBars({ title, items }: { title: string; items: CostItem[] }) {
  const max = Math.max(...items.map((i) => i.value), 1);
  const total = items.reduce((s, i) => s + i.value, 0);

  return (
    <div
      className="card p-4 flex flex-col gap-3"
      role="img"
      aria-label={`${title}. Всего ${Math.round(total)} ₽. ${items
        .map((i) => `${i.label} ${Math.round(i.value)} ₽`)
        .join(", ")}.`}
    >
      <h3 className="text-sm text-[var(--text-secondary)]">{title}</h3>
      {items.map((item) => {
        const isMax = item.value === max;
        return (
          <div key={item.label} className="flex items-center gap-2">
            <span className="w-28 text-xs text-[var(--text-secondary)] shrink-0">{item.label}</span>
            <div className="flex-1 h-4 rounded-sm bg-[var(--gridline)] overflow-hidden">
              <div
                className="h-full rounded-sm"
                style={{
                  width: `${(item.value / max) * 100}%`,
                  background: "var(--series-1)",
                  opacity: isMax ? 1 : 0.5,
                }}
              />
            </div>
            <span className="w-16 text-xs text-right figure text-[var(--text-primary)]">
              {item.value.toFixed(0)} ₽
            </span>
          </div>
        );
      })}
      <table className="sr-only">
        <caption>{title}</caption>
        <thead>
          <tr>
            <th>Категория</th>
            <th>Сумма, ₽</th>
          </tr>
        </thead>
        <tbody>
          {items.map((i) => (
            <tr key={i.label}>
              <td>{i.label}</td>
              <td>{Math.round(i.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
