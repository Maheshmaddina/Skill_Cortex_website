import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { useAuth } from "../auth/AuthContext.jsx";
import { Alert, Button, Card, QueryState } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { formatDate, formatDateTime, formatDuration, formatINR, formatTimeRange } from "../lib/format.js";

const CONTACT_EMAIL = import.meta.env.VITE_CONTACT_EMAIL ?? "info@skillcortexai.com";

function Row({ label, children }) {
  return (
    <div className="flex justify-between gap-4 py-2">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-900">{children}</dd>
    </div>
  );
}

/** Printable payment receipt for a paid booking ("Save as PDF" from the print dialog). */
export default function Receipt() {
  const { bookingId } = useParams();
  const { user } = useAuth();
  const booking = useQuery({ queryKey: ["booking", bookingId], queryFn: () => api(`/bookings/${bookingId}`) });

  return (
    <div className="mx-auto max-w-2xl px-4 py-10 print:max-w-none print:p-0">
      <div className="flex items-center justify-between gap-3 print:hidden">
        <Link to={`/bookings/${bookingId}`} className="text-sm font-medium text-brand-700 hover:underline">
          ← Back to booking
        </Link>
        <Button onClick={() => window.print()}>Print / Save as PDF</Button>
      </div>

      <QueryState query={booking}>
        {(data) => {
          const payment = data.paid_payment;
          if (!payment) {
            return (
              <Alert kind="info" className="mt-6">
                A receipt is available once the payment for this booking is confirmed.
              </Alert>
            );
          }
          const reference = payment.method === "UPI" ? `UPI transaction ID ${payment.upi_reference}` : payment.razorpay_payment_id;
          return (
            <Card className="mt-4 print:mt-0 print:shadow-none print:ring-0">
              <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 pb-5">
                <div className="flex items-center gap-3">
                  <img src="/brand/logo.png" alt="" width="48" height="48" className="size-12 rounded-full" />
                  <div>
                    <p className="text-lg font-bold text-slate-900">
                      Skill <span className="text-brand-600">Cortex</span> AI
                    </p>
                    <p className="text-xs text-slate-500">SreeNagar Colony, Punganur Road, Madanapalle</p>
                    <p className="text-xs text-slate-500">
                      {CONTACT_EMAIL} · +91 90327 56326
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <h1 className="text-2xl font-bold tracking-tight text-slate-900">Payment receipt</h1>
                  <p className="mt-1 text-sm text-slate-500">Receipt no. {data.reference}</p>
                  <span className="mt-2 inline-block rounded-md bg-emerald-50 px-2 py-0.5 text-sm font-semibold text-emerald-700 ring-1 ring-emerald-600/20">
                    PAID
                  </span>
                </div>
              </div>

              <div className="grid gap-6 py-5 sm:grid-cols-2">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Billed to</p>
                  <p className="mt-1 font-medium text-slate-900">{user?.name}</p>
                  <p className="text-sm text-slate-600">{user?.email}</p>
                  <p className="text-sm text-slate-600">{user?.phone}</p>
                </div>
                <div className="sm:text-right">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Paid on</p>
                  <p className="mt-1 font-medium text-slate-900">{payment.paid_at ? formatDateTime(payment.paid_at) : "—"}</p>
                </div>
              </div>

              <table className="w-full text-sm">
                <thead>
                  <tr className="border-y border-slate-200 text-left text-slate-500">
                    <th className="py-2 font-medium">Description</th>
                    <th className="py-2 text-right font-medium">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-b border-slate-100 align-top">
                    <td className="py-3">
                      <p className="font-medium text-slate-900">{data.webinar.title}</p>
                      <p className="text-slate-600">
                        Live webinar · {formatDate(data.slot.start_at)}, {formatTimeRange(data.slot.start_at, data.slot.end_at)} ·{" "}
                        {formatDuration(data.webinar.duration_minutes)}
                      </p>
                    </td>
                    <td className="py-3 text-right font-medium text-slate-900">{formatINR(payment.amount_paise)}</td>
                  </tr>
                </tbody>
                <tfoot>
                  <tr>
                    <td className="pt-3 text-right font-semibold text-slate-900">Total paid (incl. all taxes)</td>
                    <td className="pt-3 text-right text-lg font-bold text-slate-900">{formatINR(payment.amount_paise)}</td>
                  </tr>
                </tfoot>
              </table>

              <dl className="mt-6 divide-y divide-slate-100 rounded-xl bg-slate-50 px-4 text-sm">
                <Row label="Payment method">{payment.method === "UPI" ? "UPI" : "Card / Netbanking / Wallet (Razorpay)"}</Row>
                <Row label="Payment reference">
                  <span className="font-mono">{reference}</span>
                </Row>
                <Row label="Booking ID">{data.reference}</Row>
                <Row label="Booking status">{data.status === "COMPLETED" ? "Completed" : "Confirmed"}</Row>
              </dl>

              <p className="mt-6 text-center text-xs text-slate-500">
                This is a computer-generated payment receipt and does not need a signature. Questions? Write to {CONTACT_EMAIL}.
              </p>
            </Card>
          );
        }}
      </QueryState>
    </div>
  );
}
