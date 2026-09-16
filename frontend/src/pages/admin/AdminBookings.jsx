import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Button, EmptyState, Input, PageHeader, Pagination, QueryState, Select, StatusBadge, Table, Td } from "../../components/ui.jsx";
import { api } from "../../lib/api.js";
import { formatDate, formatDateTime, formatINR, formatTimeRange } from "../../lib/format.js";
import { useQueryParams } from "../../lib/hooks.js";

const PAGE_SIZE = 25;
const STATUSES = ["PENDING", "CONFIRMED", "COMPLETED", "CANCELLED", "EXPIRED", "FAILED"];

export default function AdminBookings() {
  const queryClient = useQueryClient();
  const [params, setParams] = useQueryParams();
  const [search, setSearch] = useState(params.q ?? "");
  const page = Number(params.page ?? 1);
  const bookings = useQuery({
    queryKey: ["admin", "bookings", params],
    queryFn: () =>
      api("/admin/bookings", {
        query: { status: params.status, q: params.q, user_id: params.user_id, webinar_id: params.webinar_id, slot_id: params.slot_id, page, page_size: PAGE_SIZE },
      }),
  });
  const cancel = useMutation({
    mutationFn: (id) => api(`/admin/bookings/${id}/cancel`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
  });

  return (
    <>
      <PageHeader title="Bookings" subtitle="All learner bookings, newest first." />
      <form
        className="mb-4 grid gap-3 sm:grid-cols-[1fr_12rem_auto] sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          setParams({ q: search.trim() });
        }}
      >
        <Input label="Search" placeholder="Booking ID, learner name or email" value={search} onChange={(e) => setSearch(e.target.value)} />
        <Select label="Status" value={params.status ?? ""} onChange={(e) => setParams({ status: e.target.value })}>
          <option value="">All</option>
          {STATUSES.map((status) => (
            <option key={status} value={status}>
              {status.charAt(0) + status.slice(1).toLowerCase()}
            </option>
          ))}
        </Select>
        <Button type="submit" variant="secondary">
          Search
        </Button>
      </form>
      {(params.user_id || params.webinar_id || params.slot_id) && (
        <p className="mb-3 text-sm text-slate-600">
          Filtered to one {params.user_id ? "learner" : params.slot_id ? "session" : "webinar"}.{" "}
          <button type="button" className="font-medium text-brand-700 hover:underline" onClick={() => setParams({ user_id: "", webinar_id: "", slot_id: "" })}>
            Clear
          </button>
        </p>
      )}
      {cancel.isError && (
        <Alert kind="error" className="mb-4">
          {cancel.error.message}
        </Alert>
      )}
      <QueryState query={bookings}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState title="No bookings match these filters" />
          ) : (
            <>
              <Table headers={["Booking", "Learner", "Webinar & slot", "Amount", "Status", "Payment", ""]}>
                {data.items.map((booking) => (
                  <tr key={booking.id}>
                    <Td className="whitespace-nowrap">
                      <p className="font-medium text-slate-900">{booking.reference}</p>
                      <p className="text-xs text-slate-500">{formatDateTime(booking.created_at)}</p>
                    </Td>
                    <Td>
                      <p className="font-medium text-slate-900">{booking.user.name}</p>
                      <p className="text-xs text-slate-500">{booking.user.email}</p>
                      <p className="text-xs text-slate-500">{booking.user.phone}</p>
                    </Td>
                    <Td>
                      <p className="font-medium text-slate-900">{booking.webinar.title}</p>
                      <p className="text-xs text-slate-500">
                        {formatDate(booking.slot.start_at)} · {formatTimeRange(booking.slot.start_at, booking.slot.end_at)}
                      </p>
                    </Td>
                    <Td className="whitespace-nowrap">{formatINR(booking.amount_paise)}</Td>
                    <Td>
                      <StatusBadge status={booking.status} />
                    </Td>
                    <Td>
                      <StatusBadge status={booking.payment_status} />
                    </Td>
                    <Td className="text-right">
                      {["PENDING", "CONFIRMED"].includes(booking.status) && (
                        <Button
                          size="sm"
                          variant="ghost"
                          loading={cancel.isPending && cancel.variables === booking.id}
                          onClick={() => {
                            const refundNote = booking.payment_status === "PAID" ? ` ${formatINR(booking.amount_paise)} will be refunded.` : "";
                            if (window.confirm(`Cancel booking ${booking.reference} for ${booking.user.name}?${refundNote} The learner will be notified.`)) {
                              cancel.mutate(booking.id);
                            }
                          }}
                        >
                          Cancel
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
