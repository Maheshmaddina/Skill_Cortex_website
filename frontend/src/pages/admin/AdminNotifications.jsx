import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Badge, Button, EmptyState, Input, PageHeader, Pagination, QueryState, Select, StatusBadge, Table, Td } from "../../components/ui.jsx";
import { api } from "../../lib/api.js";
import { formatDateTime, humanize } from "../../lib/format.js";
import { useQueryParams } from "../../lib/hooks.js";

const PAGE_SIZE = 25;
const TYPES = ["REGISTRATION", "BOOKING_CONFIRMATION", "ADMIN_PAYMENT", "REMINDER", "CANCELLATION", "REFUND", "PASSWORD_RESET"];

export default function AdminNotifications() {
  const queryClient = useQueryClient();
  const [params, setParams] = useQueryParams();
  const [search, setSearch] = useState(params.q ?? "");
  const page = Number(params.page ?? 1);
  const notifications = useQuery({
    queryKey: ["admin", "notifications", params],
    queryFn: () =>
      api("/admin/notifications", {
        query: { status: params.status, type: params.type, channel: params.channel, q: params.q, page, page_size: PAGE_SIZE },
      }),
  });
  const retry = useMutation({
    mutationFn: (id) => api(`/admin/notifications/${id}/retry`, { method: "POST" }),
    onSuccess: () => {
      // Delivery runs in the background right after the response.
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ["admin", "notifications"] }), 1500);
      queryClient.invalidateQueries({ queryKey: ["admin", "notifications"] });
    },
  });

  return (
    <>
      <PageHeader title="Notifications" subtitle="Email and SMS delivery history. Failed messages retry automatically up to 3 times." />
      <form
        className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_11rem_14rem_9rem_auto] lg:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          setParams({ q: search.trim() });
        }}
      >
        <Input label="Search" placeholder="Recipient or subject" value={search} onChange={(e) => setSearch(e.target.value)} />
        <Select label="Status" value={params.status ?? ""} onChange={(e) => setParams({ status: e.target.value })}>
          <option value="">All</option>
          <option value="PENDING">Pending</option>
          <option value="SENT">Sent</option>
          <option value="FAILED">Failed</option>
        </Select>
        <Select label="Type" value={params.type ?? ""} onChange={(e) => setParams({ type: e.target.value })}>
          <option value="">All</option>
          {TYPES.map((type) => (
            <option key={type} value={type}>
              {humanize(type)}
            </option>
          ))}
        </Select>
        <Select label="Channel" value={params.channel ?? ""} onChange={(e) => setParams({ channel: e.target.value })}>
          <option value="">All</option>
          <option value="EMAIL">Email</option>
          <option value="SMS">SMS</option>
        </Select>
        <Button type="submit" variant="secondary">
          Search
        </Button>
      </form>
      {retry.isError && (
        <Alert kind="error" className="mb-4">
          {retry.error.message}
        </Alert>
      )}
      <QueryState query={notifications}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState title="No notifications match these filters" />
          ) : (
            <>
              <Table headers={["Created", "Type", "Recipient", "Message", "Delivery", ""]}>
                {data.items.map((notification) => (
                  <tr key={notification.id}>
                    <Td className="whitespace-nowrap text-xs">{formatDateTime(notification.created_at)}</Td>
                    <Td>
                      <p className="font-medium text-slate-900">{humanize(notification.type)}</p>
                      <Badge color="slate">{notification.channel === "SMS" ? "SMS" : "Email"}</Badge>
                      {notification.reminder_offset_days !== null && (
                        <p className="mt-1 text-xs text-slate-500">
                          {notification.reminder_offset_days === 0 ? "Same day" : `${notification.reminder_offset_days} day(s) before`}
                        </p>
                      )}
                    </Td>
                    <Td>
                      <p className="break-all">{notification.recipient_address}</p>
                      <p className="text-xs text-slate-500">{notification.recipient_type === "ADMIN" ? "Admin" : "Learner"}</p>
                    </Td>
                    <Td className="max-w-md">
                      {notification.subject && <p className="font-medium text-slate-900">{notification.subject}</p>}
                      <p className="line-clamp-2 whitespace-pre-line text-xs text-slate-500">{notification.message}</p>
                    </Td>
                    <Td className="whitespace-nowrap">
                      <StatusBadge status={notification.status} />
                      <p className="mt-1 text-xs text-slate-500">
                        {notification.attempts} attempt{notification.attempts === 1 ? "" : "s"}
                        {notification.sent_at && ` · sent ${formatDateTime(notification.sent_at)}`}
                      </p>
                      {notification.failure_reason && <p className="mt-1 max-w-56 whitespace-normal text-xs text-rose-600">{notification.failure_reason}</p>}
                    </Td>
                    <Td className="text-right">
                      {["FAILED", "PENDING"].includes(notification.status) && notification.type !== "PASSWORD_RESET" && (
                        <Button size="sm" variant="secondary" loading={retry.isPending && retry.variables === notification.id} onClick={() => retry.mutate(notification.id)}>
                          Retry
                        </Button>
                      )}
                    </Td>
                  </tr>
                ))}
              </Table>
              <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={(next) => setParams({ page: next })} />
            </>
          )
        }
      </QueryState>
    </>
  );
}
