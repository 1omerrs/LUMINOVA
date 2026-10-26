import { useId } from "react";
import { monthLabel, type Point } from "../../lib/reports.ts";

export type Series = { label: string; color: string; points: Point[] };

const HEIGHT = 160;

export function BarChart({ title, series, format }: { title: string; series: Series[]; format: (value: number) => string }) {
  const id = useId();
  const months = series[0]?.points.map((point) => point.month) ?? [];
  const values = series.flatMap((item) => item.points.map((point) => Number(point.value)));
  const max = Math.max(...values, 0);
  const empty = max === 0;
  const groupWidth = 100 / Math.max(months.length, 1);
  const barWidth = Math.min(groupWidth / (series.length + 1), 7);

  return (
    <figure aria-labelledby={`${id}-title`} className="min-w-0">
      <figcaption id={`${id}-title`} className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[14px] font-semibold">{title}</span>
        {series.length > 1 ? (
          <span className="flex flex-wrap gap-3 text-[12px] text-slate">
            {series.map((item) => (
              <span key={item.label} className="inline-flex items-center gap-1.5">
                <span aria-hidden className="h-2 w-2 rounded-full" style={{ background: item.color }} />
                {item.label}
              </span>
            ))}
          </span>
        ) : null}
      </figcaption>
      <div className="relative mt-4" aria-hidden>
        {empty ? (
          <div className="grid h-[160px] place-items-center rounded-xl border border-dashed border-mist text-[13px] text-slate">Bu dönemde kayıt yok.</div>
        ) : (
          <svg viewBox={`0 0 100 ${HEIGHT}`} preserveAspectRatio="none" className="h-[160px] w-full overflow-visible">
            {[0.25, 0.5, 0.75].map((line) => (
              <line key={line} x1="0" x2="100" y1={HEIGHT * line} y2={HEIGHT * line} stroke="#e7e5df" strokeWidth="0.6" vectorEffect="non-scaling-stroke" />
            ))}
            <line x1="0" x2="100" y1={HEIGHT} y2={HEIGHT} stroke="#dcd9d1" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            {months.map((month, index) =>
              series.map((item, position) => {
                const value = Number(item.points[index]?.value ?? 0);
                const height = (value / max) * (HEIGHT - 8);
                const x = index * groupWidth + (groupWidth - barWidth * series.length) / 2 + position * barWidth;
                return (
                  <rect key={`${month}-${item.label}`} x={x} y={HEIGHT - height} width={barWidth * 0.86} height={Math.max(height, value > 0 ? 1.5 : 0)} rx="1.2" fill={item.color}>
                    <title>{`${monthLabel(month, true)} · ${item.label}: ${format(value)}`}</title>
                  </rect>
                );
              }),
            )}
          </svg>
        )}
        <div className="mt-2 grid text-center text-[11px] text-slate" style={{ gridTemplateColumns: `repeat(${months.length}, minmax(0, 1fr))` }}>
          {months.map((month) => (
            <span key={month} className="truncate capitalize">
              {monthLabel(month)}
            </span>
          ))}
        </div>
      </div>
      <div className="sr-only">
      <table>
        <caption>{title}</caption>
        <thead>
          <tr>
            <th scope="col">Ay</th>
            {series.map((item) => (
              <th key={item.label} scope="col">
                {item.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {months.map((month, index) => (
            <tr key={month}>
              <th scope="row">{monthLabel(month, true)}</th>
              {series.map((item) => (
                <td key={item.label}>{format(Number(item.points[index]?.value ?? 0))}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </figure>
  );
}
