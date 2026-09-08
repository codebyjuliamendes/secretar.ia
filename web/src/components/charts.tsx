"use client";

import { useId, useState } from "react";

/**
 * Gráfico de barras diário de uma única série (sem legenda; o título nomeia a série).
 * Marcas finas, topo arredondado, grade recessiva e tooltip por barra ao passar o mouse/foco.
 */
export function DailyBars({
  data,
  valueKey,
  title,
  color = "var(--c-chart)",
}: {
  data: { day: string; [k: string]: number | string }[];
  valueKey: string;
  title: string;
  color?: string;
}) {
  const id = useId();
  const [hover, setHover] = useState<number | null>(null);
  const width = 640;
  const height = 160;
  const pad = { top: 12, right: 8, bottom: 22, left: 28 };
  const max = Math.max(1, ...data.map((d) => Number(d[valueKey]) || 0));
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const step = innerW / Math.max(1, data.length);
  const barW = Math.max(2, Math.min(14, step - 2));
  const ticks = [0, Math.ceil(max / 2), max];
  const total = data.reduce((s, d) => s + (Number(d[valueKey]) || 0), 0);

  if (total === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted">
        Sem {title.toLowerCase()} no período.
      </div>
    );
  }

  return (
    <figure className="relative">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-40 w-full" role="img" aria-labelledby={`${id}-title`}>
        <title id={`${id}-title`}>{title} por dia</title>
        {ticks.map((t) => {
          const y = pad.top + innerH - (t / max) * innerH;
          return (
            <g key={t}>
              <line x1={pad.left} x2={width - pad.right} y1={y} y2={y} stroke="var(--c-border)" strokeWidth={1} />
              <text x={pad.left - 6} y={y + 3} textAnchor="end" fontSize={10} fill="var(--c-fg-muted)">
                {t}
              </text>
            </g>
          );
        })}
        {data.map((d, i) => {
          const v = Number(d[valueKey]) || 0;
          const h = (v / max) * innerH;
          const x = pad.left + i * step + (step - barW) / 2;
          const y = pad.top + innerH - h;
          const showLabel = data.length <= 14 || i === 0 || i === data.length - 1 || i % 7 === 0;
          return (
            <g key={d.day} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)} tabIndex={0}>
              <rect x={pad.left + i * step} y={pad.top} width={step} height={innerH} fill="transparent" />
              {v > 0 && <rect x={x} y={y} width={barW} height={h} rx={barW > 4 ? 3 : 1} fill={color} opacity={hover === null || hover === i ? 1 : 0.55} />}
              {showLabel && (
                <text x={pad.left + i * step + step / 2} y={height - 6} textAnchor="middle" fontSize={10} fill="var(--c-fg-muted)">
                  {d.day.slice(8, 10)}/{d.day.slice(5, 7)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {hover !== null && (
        <figcaption
          role="status"
          className="pointer-events-none absolute -top-2 left-1/2 -translate-x-1/2 rounded-md border border-border bg-surface px-2 py-1 text-xs shadow"
        >
          {new Date(data[hover].day + "T00:00:00").toLocaleDateString("pt-BR")}: <strong>{data[hover][valueKey]}</strong>
        </figcaption>
      )}
    </figure>
  );
}

export function HorizontalBars({ items, color = "var(--c-chart-2)" }: { items: { label: string; value: number }[]; color?: string }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  if (!items.length) return <p className="text-sm text-muted">Sem dados no período.</p>;
  return (
    <ul className="space-y-2">
      {items.map((i) => (
        <li key={i.label} className="grid grid-cols-[110px_1fr_40px] items-center gap-2 text-sm">
          <span className="truncate text-muted">{i.label}</span>
          <div className="h-2 rounded-full bg-surface-2" aria-hidden>
            <div className="h-2 rounded-full" style={{ width: `${(i.value / max) * 100}%`, background: color }} />
          </div>
          <span className="text-right tabular-nums">{i.value}</span>
        </li>
      ))}
    </ul>
  );
}
