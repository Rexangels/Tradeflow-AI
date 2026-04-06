import { cn } from "../../lib/utils";

export function MetricCard({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "positive" | "warning";
}) {
  return (
    <div className="rounded-3xl border border-slate-800 bg-slate-950/80 p-5 shadow-[0_20px_80px_rgba(2,6,23,0.35)]">
      <p className="text-xs uppercase tracking-[0.22em] text-slate-500">{label}</p>
      <p
        className={cn(
          "mt-3 text-2xl font-semibold text-slate-100",
          tone === "positive" && "text-emerald-300",
          tone === "warning" && "text-amber-300",
        )}
      >
        {value}
      </p>
    </div>
  );
}
