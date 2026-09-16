import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Badge, Button, EmptyState, Input, PageHeader, Pagination, QueryState, Select, StatusBadge, Table, Td } from "../../components/ui.jsx";
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
      api("/admin/payments", {
        query: { status: params.status, method: params.method, q: params.q, user_id: params.user_id, page, page_size: PAGE_SIZE },
      }),
  });
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin"] });
  const confirmUpi = useMutation({
    mutationFn: (id) => api(`/admin/payments/${id}/confirm-upi`, { method: "POST" }),
    onSuccess: refresh,
  });
  const rejectUpi = useMutation({
    mutationFn: ({ id, reason }) => api(`/admin/payments/${id}/reject-upi`, { method: "POST", body: { reason } }),
    onSuccess: refresh,
  });
  const reviewError = confirmUpi.error ?? rejectUpi.error;
  const toVerify = params.method === "UPI" && params.status === "PENDING";

  return (
    <>
      <PageHeader
        title="Payments"
        subtitle="Razorpay payments are verified automatically. UPI payments: check the UTR arrived in your bank/UPI app, then Confirm."
        actions={
          <Button
            variant={toVerify ? "primary" : "secondary"}
            onClick={() => setParams(toVerify ? { method: "", status: "" } : { method: "UPI", status: "PENDING" })}
          >
            {toVerify ? "Show all payments" : "UPI payments to verify"}
          </Button>
        }
      />
      <form
        className="mb-4 grid gap-3 sm:grid-cols-[1fr_10rem_10rem_auto] sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          setParams({ q: search.trim() });
        }}
      >
        <Input label="Search" placeholder="UTR, order/payment ID, booking ID, learner" value={search} onChange={(e) => setSearch(e.target.value)} />
        <Select label="Method" value={params.method ?? ""} onChange={(e) => setParams({ method: e.target.value })}>
          <option value="">All</option>
          <option value="RAZORPAY">Razorpay</option>
          <option value="UPI">UPI</option>
        </Select>
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
      {reviewError && (
        <Alert kind="error" className="mb-4">
          {reviewError.message}
        </Alert>
      )}
      <QueryState query={payments}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState title="No payments match these filters" />
          ) : (
            <>
              <Table headers={["Created", "Booking", "Learner", "Webinar", "Amount", "Status", "Reference"]}>
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
                    <Td className="text-xs text-slate-500">
                      {payment.method === "UPI" ? (
                        <>
                          <Badge>UPI</Badge>
                          <p className="mt-1 font-mono text-sm text-slate-900">UTR {payment.upi_reference}</p>
                          {payment.status === "PENDING" && (
                            <div className="mt-2 flex gap-2">
                              <Button
                                size="sm"
                                loading={confirmUpi.isPending && confirmUpi.variables === payment.id}
                                onClick={() =>
                                  window.confirm(
                                    `Confirm ${formatINR(payment.amount_paise)} from ${payment.booking.user.name} (UTR ${payment.upi_reference}) arrived in your account?`,
                                  ) && confirmUpi.mutate(payment.id)
                                }
                              >
                                Confirm
                              </Button>
                              <Button
                                size="sm"
                                variant="danger"
                                loading={rejectUpi.isPending && rejectUpi.variables?.id === payment.id}
                                onClick={() => {
                                  const reason = window.prompt("Why is this UPI payment rejected? (shown to the learner)", "No payment received with this UTR.");
                                  if (reason && reason.trim().length >= 3) rejectUpi.mutate({ id: payment.id, reason });
                                }}
                              >
                                Reject
                              </Button>
                            </div>
                          )}
                        </>
                      ) : (
                        <div className="font-mono">
                          <p>{payment.razorpay_order_id}</p>
                          {payment.razorpay_payment_id && <p>{payment.razorpay_payment_id}</p>}
                          {payment.razorpay_refund_id && <p>refund {payment.razorpay_refund_id}</p>}
                        </div>
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
