import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Button, EmptyState, Input, PageHeader, Pagination, QueryState, Select, StatusBadge, Table, Td } from "../../components/ui.jsx";
import { api } from "../../lib/api.js";
import { formatDateTime, formatINR } from "../../lib/format.js";
import { useQueryParams } from "../../lib/hooks.js";

const PAGE_SIZE = 25;

export default function AdminPayments() {
  const [params, setParams] = useQueryParams();
  const [search, setSearch] = useState(params.q ?? "");
  const page = Number(params.page ?? 1);
  const payments = useQuery({
    queryKey: ["admin", "payments", params],
    queryFn: () =>
      api("/admin/payments", { query: { status: params.status, q: params.q, user_id: params.user_id, page, page_size: PAGE_SIZE } }),
  });

  return (
    <>
      <PageHeader title="Payments" subtitle="Razorpay transactions. Bookings are confirmed only after server-side verification." />
      <form
        className="mb-4 grid gap-3 sm:grid-cols-[1fr_12rem_auto] sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          setParams({ q: search.trim() });
        }}
      >
        <Input label="Search" placeholder="Order/payment ID, booking ID, learner" value={search} onChange={(e) => setSearch(e.target.value)} />
        <Select label="Status" value={params.status ?? ""} onChange={(e) => setParams({ status: e.target.value })}>
          <option value="">All</option>
          <option value="PAID">Paid</option>
          <option value="PENDING">Pending</option>
          <option value="FAILED">Failed</option>
          <option value="REFUNDED">Refunded</option>
        </Select>
        <Button type="submit" variant="secondary">
          Search
        </Button>
      </form>
      {params.user_id && (
        <p className="mb-3 text-sm text-slate-600">
          Filtered to one learner.{" "}
          <button type="button" className="font-medium text-brand-700 hover:underline" onClick={() => setParams({ user_id: "" })}>
            Clear
          </button>
        </p>
      )}
      <QueryState query={payments}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState title="No payments match these filters" />
          ) : (
            <>
              <Table headers={["Created", "Booking", "Learner", "Webinar", "Amount", "Status", "Razorpay"]}>
                {data.items.map((payment) => (
                  <tr key={payment.id}>
                    <Td className="whitespace-nowrap text-xs">{formatDateTime(payment.created_at)}</Td>
                    <Td className="whitespace-nowrap">
                      <p className="font-medium text-slate-900">{payment.booking.reference}</p>
                      <StatusBadge status={payment.booking.status} />
                    </Td>
                    <Td>
                      <p className="font-medium text-slate-900">{payment.booking.user.name}</p>
                      <p className="text-xs text-slate-500">{payment.booking.user.email}</p>
                    </Td>
                    <Td>{payment.booking.webinar.title}</Td>
                    <Td className="whitespace-nowrap font-medium">{formatINR(payment.amount_paise)}</Td>
                    <Td>
                      <StatusBadge status={payment.status} />
                      {payment.paid_at && <p className="mt-1 text-xs text-slate-500">Paid {formatDateTime(payment.paid_at)}</p>}
                      {payment.failure_reason && <p className="mt-1 max-w-56 text-xs text-rose-600">{payment.failure_reason}</p>}
                    </Td>
                    <Td className="font-mono text-xs text-slate-500">
                      <p>{payment.razorpay_order_id}</p>
                      {payment.razorpay_payment_id && <p>{payment.razorpay_payment_id}</p>}
                      {payment.razorpay_refund_id && <p>refund {payment.razorpay_refund_id}</p>}
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
