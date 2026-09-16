import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { Checkbox, EmptyState, PageHeader, QueryState, StatusBadge, Table, Td } from "../../components/ui.jsx";
import { api } from "../../lib/api.js";
import { formatDate, formatDateTime, formatTimeRange } from "../../lib/format.js";

/** Sessions learners set for their own date and time — the schedule the team needs to conduct. */
export default function AdminLearnerSessions() {
  const [upcomingOnly, setUpcomingOnly] = useState(true);
  const sessions = useQuery({
    queryKey: ["admin", "slots", "learner-set", upcomingOnly],
    queryFn: () => api("/admin/slots", { query: { learner_set: true, upcoming: upcomingOnly, page_size: 100 } }),
    refetchInterval: 60_000,
  });

  return (
    <>
      <PageHeader
        title="Learner webinars"
        subtitle="Webinars learners set for the date and time they chose. Conduct each one at its time. Seats show paid bookings plus payments in progress; unpaid sessions are withdrawn automatically after an hour."
        actions={<Checkbox label="Upcoming only" checked={upcomingOnly} onChange={(e) => setUpcomingOnly(e.target.checked)} />}
      />
      <QueryState query={sessions}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState title="No learner webinars yet" description="When a learner sets a webinar for their own date and time, it appears here." />
          ) : (
            <Table headers={["When (IST)", "Course", "Set by", "Note", "Seats", "Status", ""]}>
              {data.items.map((slot) => (
                <tr key={slot.id}>
                  <Td className="whitespace-nowrap">
                    <p className="font-medium text-slate-900">{formatDate(slot.start_at)}</p>
                    <p className="text-xs text-slate-500">{formatTimeRange(slot.start_at, slot.end_at)}</p>
                  </Td>
                  <Td className="font-medium text-slate-900">{slot.webinar.title}</Td>
                  <Td>
                    {slot.set_by ? (
                      <>
                        <p className="text-slate-900">{slot.set_by.name}</p>
                        <p className="text-xs text-slate-500">
                          {slot.set_by.email} · {slot.set_by.phone}
                        </p>
                      </>
                    ) : (
                      "—"
                    )}
                    <p className="text-xs text-slate-400">Set {formatDateTime(slot.created_at)}</p>
                  </Td>
                  <Td className="max-w-56 whitespace-pre-line text-xs">{slot.learner_note ?? "—"}</Td>
                  <Td className="whitespace-nowrap">
                    {slot.booked_seats} / {slot.capacity}
                  </Td>
                  <Td>
                    <StatusBadge status={slot.status} />
                  </Td>
                  <Td className="whitespace-nowrap text-sm">
                    <Link to={`/admin/bookings?slot_id=${slot.id}`} className="font-medium text-brand-700 hover:underline">
                      Bookings
                    </Link>
                    <span className="mx-2 text-slate-300">|</span>
                    <Link to={`/admin/webinars/${slot.webinar.id}/slots`} className="font-medium text-brand-700 hover:underline">
                      Manage
                    </Link>
                  </Td>
                </tr>
              ))}
            </Table>
          )
        }
      </QueryState>
    </>
  );
}
