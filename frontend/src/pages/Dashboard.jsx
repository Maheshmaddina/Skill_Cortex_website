import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../auth/AuthContext.jsx";
import BookingSummary from "../components/BookingSummary.jsx";
import SessionCountdown from "../components/SessionCountdown.jsx";
import { Button, Card, EmptyState, PageSpinner, StatusBadge } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { formatDate, formatTimeRange } from "../lib/format.js";

export default function Dashboard() {
  const { user } = useAuth();
  const upcoming = useQuery({
    queryKey: ["bookings", { scope: "upcoming", page_size: 5 }],
    queryFn: () => api("/bookings", { query: { scope: "upcoming", page_size: 5 } }),
  });
  const past = useQuery({
    queryKey: ["bookings", { scope: "past", page_size: 1 }],
    queryFn: () => api("/bookings", { query: { scope: "past", page_size: 1 } }),
  });

  const next = upcoming.data?.items.find((booking) => booking.status === "CONFIRMED") ?? upcoming.data?.items[0];

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <h1 className="text-3xl font-bold tracking-tight text-slate-900">Welcome back, {user.name.split(" ")[0]}!</h1>
      <p className="mt-1 text-slate-500">{user.department ? `Department: ${user.department.name}` : "Pick a webinar to get started."}</p>

      <div className="mt-8">
        <Card>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Upcoming webinar</h2>
          {upcoming.isPending ? (
            <PageSpinner />
          ) : next ? (
            <div className="mt-3">
              <p className="text-xl font-semibold text-slate-900">{next.webinar.title}</p>
              <p className="mt-1 text-slate-600">
                {formatDate(next.slot.start_at)} · {formatTimeRange(next.slot.start_at, next.slot.end_at)}
              </p>
              <div className="mt-5">
                <SessionCountdown start={next.slot.start_at} end={next.slot.end_at} />
              </div>
              <div className="mt-4 flex items-center gap-2 text-sm">
                <StatusBadge status={next.status} />
                {next.status === "PENDING" && <span className="text-amber-700">Payment pending — your seat is held briefly.</span>}
              </div>
              <Button className="mt-5" variant="secondary" to={`/bookings/${next.id}`}>
                {next.status === "PENDING" ? "Complete payment" : "View booking"}
              </Button>
            </div>
          ) : (
            <p className="mt-3 text-slate-600">You have no upcoming webinars yet.</p>
          )}
        </Card>
      </div>

      <div className="mt-6 grid gap-6 sm:grid-cols-2">
        <Card>
          <p className="text-sm text-slate-500">Upcoming bookings</p>
          <p className="mt-1 text-3xl font-bold">{upcoming.data?.total ?? "–"}</p>
        </Card>
        <Card>
          <p className="text-sm text-slate-500">Past & cancelled bookings</p>
          <p className="mt-1 text-3xl font-bold">{past.data?.total ?? "–"}</p>
        </Card>
      </div>

      <section className="mt-10">
        <h2 className="text-lg font-semibold">Your upcoming bookings</h2>
        <div className="mt-4 space-y-3">
          {upcoming.data?.items.length ? (
            upcoming.data.items.map((booking) => <BookingSummary key={booking.id} booking={booking} />)
          ) : (
            !upcoming.isPending && (
              <EmptyState
                title="Nothing booked yet"
                description="Pick a course, choose your own date and time, and set your webinar."
                action={<Button to="/webinars">Set a webinar</Button>}
              />
            )
          )}
        </div>
      </section>
    </div>
  );
}
