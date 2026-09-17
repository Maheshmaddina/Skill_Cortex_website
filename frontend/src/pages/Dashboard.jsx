import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../auth/AuthContext.jsx";
import BookingSummary from "../components/BookingSummary.jsx";
import SessionCountdown from "../components/SessionCountdown.jsx";
import { Badge, Button, Card, EmptyState, PageSpinner, StatusBadge } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { formatDate, formatTimeRange } from "../lib/format.js";

/** One confirmed webinar with its live countdown. */
function ConfirmedWebinar({ booking }) {
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between gap-3">
        <p className="text-lg font-semibold text-slate-900">{booking.webinar.title}</p>
        <StatusBadge status={booking.status} />
      </div>
      <p className="mt-1 text-sm text-slate-600">
        {formatDate(booking.slot.start_at)} · {formatTimeRange(booking.slot.start_at, booking.slot.end_at)}
      </p>
      <div className="mt-5 flex-1">
        <SessionCountdown start={booking.slot.start_at} end={booking.slot.end_at} />
      </div>
      <div className="mt-5 flex items-center justify-between gap-3">
        <span className="text-xs text-slate-400">Booking {booking.reference}</span>
        <Button size="sm" variant="secondary" to={`/bookings/${booking.id}`}>
          View booking
        </Button>
      </div>
    </Card>
  );
}

/** A webinar the learner attended: paid, confirmed, and the session is over. */
function AttendedWebinar({ booking }) {
  return (
    <li className="flex flex-col gap-3 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="font-semibold text-slate-900">{booking.webinar.title}</p>
        <p className="mt-1 text-sm text-slate-600">
          {formatDate(booking.slot.start_at)} · {formatTimeRange(booking.slot.start_at, booking.slot.end_at)}
        </p>
        <p className="mt-1 text-xs text-slate-400">Booking {booking.reference}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2 sm:justify-end">
        <Badge color="green">✓ Attended</Badge>
        {booking.paid_payment && (
          <Button size="sm" variant="secondary" to={`/bookings/${booking.id}/receipt`}>
            Receipt
          </Button>
        )}
      </div>
    </li>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const upcoming = useQuery({
    queryKey: ["bookings", { scope: "upcoming", page_size: 100 }],
    queryFn: () => api("/bookings", { query: { scope: "upcoming", page_size: 100 } }),
  });

  const past = useQuery({
    queryKey: ["bookings", { scope: "past", page_size: 100 }],
    queryFn: () => api("/bookings", { query: { scope: "past", page_size: 100 } }),
  });
  const now = Date.now();
  // Completed sessions, plus confirmed ones that just ended before the completion job marked them.
  const attended = (past.data?.items ?? []).filter(
    (booking) =>
      booking.status === "COMPLETED" || (booking.status === "CONFIRMED" && new Date(booking.slot.end_at).getTime() <= now),
  );

  const bookings = upcoming.data?.items ?? [];
  const confirmed = bookings.filter((booking) => booking.status === "CONFIRMED"); // soonest first
  const awaitingPayment = bookings.filter((booking) => booking.status === "PENDING");

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <h1 className="text-3xl font-bold tracking-tight text-slate-900">Welcome back, {user.name.split(" ")[0]}!</h1>
      <p className="mt-1 text-slate-500">{user.department ? `Department: ${user.department.name}` : "Pick a webinar to get started."}</p>

      <section className="mt-8">
        <h2 className="text-lg font-semibold">
          Your upcoming webinars
          {confirmed.length > 0 && <span className="ml-2 text-sm font-normal text-slate-500">({confirmed.length})</span>}
        </h2>
        {upcoming.isPending ? (
          <PageSpinner />
        ) : confirmed.length ? (
          <div className="mt-4 grid gap-6 lg:grid-cols-2">
            {confirmed.map((booking) => (
              <ConfirmedWebinar key={booking.id} booking={booking} />
            ))}
          </div>
        ) : (
          !awaitingPayment.length && (
            <div className="mt-4">
              <EmptyState
                title="Nothing booked yet"
                description="Pick a course, choose your own date and time, and set your webinar."
                action={<Button to="/webinars">Set a webinar</Button>}
              />
            </div>
          )
        )}
        {!upcoming.isPending && !confirmed.length && awaitingPayment.length > 0 && (
          <p className="mt-3 text-slate-600">No confirmed webinars yet — complete the payment below to confirm your seat.</p>
        )}
      </section>

      {awaitingPayment.length > 0 && (
        <section className="mt-10">
          <h2 className="text-lg font-semibold">Awaiting payment</h2>
          <p className="mt-1 text-sm text-slate-500">Your seat is held while you pay. Open a booking to complete payment.</p>
          <div className="mt-4 space-y-3">
            {awaitingPayment.map((booking) => (
              <BookingSummary key={booking.id} booking={booking} />
            ))}
          </div>
        </section>
      )}

      <section className="mt-10">
        <h2 className="text-lg font-semibold">
          Attended webinars
          {attended.length > 0 && <span className="ml-2 text-sm font-normal text-slate-500">({attended.length})</span>}
        </h2>
        {past.isPending ? (
          <PageSpinner />
        ) : attended.length ? (
          <ul className="mt-4 space-y-3">
            {attended.map((booking) => (
              <AttendedWebinar key={booking.id} booking={booking} />
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-slate-500">Webinars you've attended will appear here after each session ends.</p>
        )}
      </section>
    </div>
  );
}
