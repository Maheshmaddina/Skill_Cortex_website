import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { Badge, EmptyState, PageHeader, Pagination, QueryState } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { formatDateTime, humanize } from "../lib/format.js";
import { useQueryParams } from "../lib/hooks.js";

const PAGE_SIZE = 20;

export default function Notifications() {
  const [params, setParams] = useQueryParams();
  const page = Number(params.page ?? 1);
  const queryClient = useQueryClient();

  // Opening the inbox clears the unread badge in the menu.
  useEffect(() => {
    api("/notifications/mark-seen", { method: "POST" })
      .then(() => queryClient.setQueryData(["notifications", "unread-count"], { count: 0 }))
      .catch(() => {});
  }, [queryClient]);
  const notifications = useQuery({
    queryKey: ["notifications", page],
    queryFn: () => api("/notifications", { query: { page, page_size: PAGE_SIZE } }),
  });

  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <PageHeader title="Notifications" subtitle="Your booking confirmations, payment updates and reminders." />
      <QueryState query={notifications}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState title="No notifications yet" description="Booking confirmations and reminders will show up here." />
          ) : (
            <>
              <ul className="space-y-3">
                {data.items.map((notification) => (
                  <li key={notification.id} className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge>{humanize(notification.type)}</Badge>
                      <span className="ml-auto text-xs text-slate-400">{formatDateTime(notification.created_at)}</span>
                    </div>
                    {notification.subject && <p className="mt-3 font-medium text-slate-900">{notification.subject}</p>}
                    <p className="mt-1 line-clamp-3 whitespace-pre-line text-sm text-slate-600">{notification.message}</p>
                  </li>
                ))}
              </ul>
              <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={(next) => setParams({ page: next })} />
            </>
          )
        }
      </QueryState>
    </div>
  );
}
