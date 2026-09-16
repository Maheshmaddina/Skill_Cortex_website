import { useQuery } from "@tanstack/react-query";

import BookingSummary from "../components/BookingSummary.jsx";
import { Button, EmptyState, PageHeader, Pagination, QueryState } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { useQueryParams } from "../lib/hooks.js";

const PAGE_SIZE = 10;
const TABS = [
  ["upcoming", "Upcoming"],
  ["past", "Previous"],
];

export default function MyBookings() {
  const [params, setParams] = useQueryParams();
  const scope = params.scope === "past" ? "past" : "upcoming";
  const page = Number(params.page ?? 1);
  const bookings = useQuery({
    queryKey: ["bookings", { scope, page }],
    queryFn: () => api("/bookings", { query: { scope, page, page_size: PAGE_SIZE } }),
  });

  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <PageHeader title="My bookings" actions={<Button to="/webinars">Book a webinar</Button>} />
      <div className="mb-6 flex gap-2" role="tablist">
        {TABS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={scope === value}
            onClick={() => setParams({ scope: value })}
            className={`rounded-lg px-4 py-2 text-sm font-semibold ${scope === value ? "bg-brand-500 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <QueryState query={bookings}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState
              title={scope === "upcoming" ? "No upcoming bookings" : "No previous bookings"}
              description={scope === "upcoming" ? "Webinars you book will appear here." : "Completed, cancelled and expired bookings appear here."}
            />
          ) : (
            <>
              <div className="space-y-3">
                {data.items.map((booking) => (
                  <BookingSummary key={booking.id} booking={booking} />
                ))}
              </div>
              <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={(next) => setParams({ scope, page: next })} />
            </>
          )
        }
      </QueryState>
    </div>
  );
}
