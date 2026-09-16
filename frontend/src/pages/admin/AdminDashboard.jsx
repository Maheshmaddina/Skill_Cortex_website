import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { Badge, Card, PageHeader, QueryState, Table, Td } from "../../components/ui.jsx";
import { api } from "../../lib/api.js";
import { formatDate, formatINR, formatTimeRange } from "../../lib/format.js";

function Stat({ label, value, detail, to }) {
  const body = (
    <Card className="h-full p-5">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-3xl font-bold tracking-tight text-slate-900">{value}</p>
      {detail && <p className="mt-1 text-xs text-slate-500">{detail}</p>}
    </Card>
  );
  return to ? (
    <Link to={to} className="block rounded-2xl transition hover:ring-2 hover:ring-brand-300">
      {body}
    </Link>
  ) : (
    body
  );
}

export default function AdminDashboard() {
  const stats = useQuery({ queryKey: ["admin", "stats"], queryFn: () => api("/admin/dashboard/stats"), refetchInterval: 60_000 });

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Live overview of learners, bookings and payments." />
      <QueryState query={stats}>
        {(s) => (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Stat label="Total learners" value={s.users.learners} detail={`${s.users.new_learners_last_30_days} new in the last 30 days`} to="/admin/users?role=USER" />
              <Stat label="Webinars" value={s.webinars.total} detail={`${s.webinars.active} active`} to="/admin/webinars" />
              <Stat label="Upcoming sessions" value={s.upcoming_sessions_count} detail={`${s.upcoming_learner_set_sessions_count} set by learners`} to="/admin/learner-webinars" />
              <Stat label="Total bookings" value={s.bookings.total} detail={`${s.bookings.confirmed} confirmed · ${s.bookings.pending} awaiting payment`} to="/admin/bookings" />
              <Stat label="Revenue" value={formatINR(s.revenue.total_paise) === "Free" ? "₹0" : formatINR(s.revenue.total_paise)} detail={`${formatINR(s.revenue.last_30_days_paise) === "Free" ? "₹0" : formatINR(s.revenue.last_30_days_paise)} in the last 30 days`} to="/admin/payments?status=PAID" />
              <Stat label="Successful payments" value={s.payments.successful} detail={`${s.payments.refunded} refunded`} to="/admin/payments?status=PAID" />
              <Stat
                label="UPI payments to verify"
                value={s.payments.upi_awaiting_verification}
                detail={`${s.payments.pending} pending payments in total`}
                to="/admin/payments?method=UPI&status=PENDING"
              />
              <Stat label="Failed payments" value={s.payments.failed} detail={`${s.notifications.failed} failed notifications`} to="/admin/payments?status=FAILED" />
            </div>

            <h2 className="mt-10 mb-3 text-lg font-semibold">Upcoming sessions</h2>
            {s.upcoming_sessions.length === 0 ? (
              <p className="text-sm text-slate-500">No upcoming sessions scheduled.</p>
            ) : (
              <Table headers={["Webinar", "Date", "Time", "Booked", "Available"]}>
                {s.upcoming_sessions.map((session) => (
                  <tr key={session.slot_id}>
                    <Td className="font-medium text-slate-900">
                      <Link to={`/admin/webinars/${session.webinar_id}/slots`} className="hover:underline">
                        {session.webinar_title}
                      </Link>
                      {session.set_by_learner && (
                        <span className="ml-2">
                          <Badge>Set by learner</Badge>
                        </span>
                      )}
                    </Td>
                    <Td className="whitespace-nowrap">{formatDate(session.start_at)}</Td>
                    <Td className="whitespace-nowrap">{formatTimeRange(session.start_at, session.end_at)}</Td>
                    <Td>
                      {session.booked_seats} / {session.capacity}
                    </Td>
                    <Td>{session.available_seats}</Td>
                  </tr>
                ))}
              </Table>
            )}
          </>
        )}
      </QueryState>
    </>
  );
}
