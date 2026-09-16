import { countdownParts } from "../lib/format.js";
import { useNow } from "../lib/hooks.js";

const UNITS = [
  ["days", "Days"],
  ["hours", "Hours"],
  ["minutes", "Minutes"],
  ["seconds", "Seconds"],
];

/** Live timer to a session's start; switches to "Live now" while it runs and "ended" afterwards. */
export default function SessionCountdown({ start, end }) {
  const now = useNow(1000);
  const startsIn = new Date(start).getTime() - now;
  const endsIn = new Date(end).getTime() - now;

  if (endsIn <= 0) {
    return <p className="rounded-xl bg-slate-100 px-4 py-3 text-sm font-medium text-slate-600">This session has ended.</p>;
  }
  if (startsIn <= 0) {
    return (
      <p className="flex items-center gap-2 rounded-xl bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-800 ring-1 ring-emerald-200">
        <span className="size-2.5 animate-pulse rounded-full bg-emerald-500" aria-hidden="true" />
        Live now — your webinar has started.
      </p>
    );
  }

  const parts = countdownParts(startsIn);
  return (
    <div role="timer" aria-label="Time until your webinar starts">
      <p className="text-xs font-semibold uppercase tracking-wide text-brand-700">Starts in</p>
      <div className="mt-2 grid grid-cols-4 gap-2 sm:max-w-md">
        {UNITS.map(([key, label]) => (
          <div key={key} className="rounded-xl bg-ink px-2 py-3 text-center text-white">
            <span className="block text-2xl font-bold tabular-nums sm:text-3xl">{String(parts[key]).padStart(2, "0")}</span>
            <span className="block text-[0.7rem] uppercase tracking-wide text-slate-300">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
