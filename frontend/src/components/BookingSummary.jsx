import { Link } from "react-router";

import { formatDate, formatINR, formatStartsIn, formatTimeRange } from "../lib/format.js";
import { useNow } from "../lib/hooks.js";
import { StatusBadge } from "./ui.jsx";

/** One booking in a list (dashboard, My Bookings). */
export default function BookingSummary({ booking }) {
  const now = useNow(30_000);
  const startsIn = new Date(booking.slot.start_at).getTime() - now;
  const showTimer = booking.status === "CONFIRMED" && new Date(booking.slot.end_at).getTime() > now;
  const live = startsIn <= 0;
  return (
    <Link
      to={`/bookings/${booking.id}`}
      className="flex flex-col gap-3 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 transition hover:ring-brand-300 sm:flex-row sm:items-center sm:justify-between"
    >
      <div>
        <p className="font-semibold text-slate-900">{booking.webinar.title}</p>
        <p className="mt-1 text-sm text-slate-600">
          {formatDate(booking.slot.start_at)} · {formatTimeRange(booking.slot.start_at, booking.slot.end_at)}
        </p>
        {showTimer && (
          <p className={`mt-1 text-sm font-semibold ${live ? "text-emerald-700" : "text-brand-700"}`}>
            {live ? "Live now" : formatStartsIn(startsIn)}
          </p>
        )}
        <p className="mt-1 text-xs text-slate-400">Booking {booking.reference}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2 sm:justify-end">
        <span className="text-sm font-medium text-slate-900">{formatINR(booking.amount_paise)}</span>
        <StatusBadge status={booking.status} />
        {booking.payment_status && (
          <span className="text-xs text-slate-500">
            Payment: <StatusBadge status={booking.payment_status} />
          </span>
        )}
      </div>
    </Link>
  );
}
