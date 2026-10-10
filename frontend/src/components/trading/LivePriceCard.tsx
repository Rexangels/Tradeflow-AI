import type { ForexPair } from "../../shared";
import { cn } from "../../lib/utils";

interface LivePriceCardProps {
  pair: ForexPair;
  isSelected?: boolean;
  onSelect?: (symbol: string) => void;
  onQuickTrade?: (symbol: string, side: "buy" | "sell") => void;
}

export function LivePriceCard({
  pair,
  isSelected,
  onSelect,
  onQuickTrade,
}: LivePriceCardProps) {
  const isJpy = pair.symbol.includes("JPY");
  const decimals = isJpy ? 3 : 5;
  const quote = pair.quote;

  const bidFormatted = quote.bid.toFixed(decimals);
  const askFormatted = quote.ask.toFixed(decimals);
  const spread = quote.spread_pips.toFixed(1);

  return (
    <div
      onClick={() => onSelect?.(pair.symbol)}
      className={cn(
        "group relative flex flex-col justify-between rounded-2xl border p-4.5 transition-all duration-200 cursor-pointer",
        isSelected
          ? "border-cyan-500/60 bg-gradient-to-b from-cyan-950/40 to-slate-950 shadow-lg shadow-cyan-950/30"
          : "border-slate-800/80 bg-slate-900/40 hover:border-slate-700/80 hover:bg-slate-900/60",
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-semibold tracking-wide text-slate-100 text-base">
            {pair.symbol}
          </span>
          {pair.isWatched && (
            <span className="rounded-md bg-cyan-500/10 px-1.5 py-0.5 text-[10px] font-medium text-cyan-400 border border-cyan-500/20">
              WATCHED
            </span>
          )}
        </div>
        <span className="text-xs font-mono text-slate-400 bg-slate-800/60 px-2 py-0.5 rounded-full border border-slate-700/40">
          Spread {spread} pips
        </span>
      </div>

      <div className="my-3 grid grid-cols-2 gap-2 text-center">
        <div className="rounded-xl border border-slate-800/70 bg-slate-950/60 p-2.5">
          <p className="text-[11px] font-medium uppercase text-slate-400 tracking-wider">
            BID (SELL)
          </p>
          <p className="mt-1 font-mono text-base font-bold text-rose-400">
            {bidFormatted}
          </p>
        </div>
        <div className="rounded-xl border border-slate-800/70 bg-slate-950/60 p-2.5">
          <p className="text-[11px] font-medium uppercase text-slate-400 tracking-wider">
            ASK (BUY)
          </p>
          <p className="mt-1 font-mono text-base font-bold text-emerald-400">
            {askFormatted}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 pt-1">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onQuickTrade?.(pair.symbol, "sell");
          }}
          className="flex-1 rounded-xl border border-rose-500/30 bg-rose-500/10 py-1.5 text-xs font-semibold text-rose-300 hover:bg-rose-500/20 transition-colors"
        >
          Sell
        </button>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onQuickTrade?.(pair.symbol, "buy");
          }}
          className="flex-1 rounded-xl border border-emerald-500/30 bg-emerald-500/10 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/20 transition-colors"
        >
          Buy
        </button>
      </div>
    </div>
  );
}
