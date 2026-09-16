import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { Alert, Button, Card, QueryState, StatusBadge } from "../components/ui.jsx";
import { ApiError, api } from "../lib/api.js";
import { formatCountdown, formatDate, formatDuration, formatINR, formatTimeRange } from "../lib/format.js";
import { useNow } from "../lib/hooks.js";
import { CheckoutDismissed, loadRazorpay, openCheckout } from "../lib/razorpay.js";

function Row({ label, children }) {
  return (
    <div className="flex justify-between gap-4 py-2">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-900">{children}</dd>
    </div>
  );
}

export default function BookingDetail() {
  const { bookingId } = useParams();
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState(null);
  const booking = useQuery({ queryKey: ["booking", bookingId], queryFn: () => api(`/bookings/${bookingId}`) });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["booking", bookingId] });
    queryClient.invalidateQueries({ queryKey: ["bookings"] });
  };

  const pay = useMutation({
    mutationFn: async () => {
      const order = await api("/payments/create-order", { method: "POST", body: { booking_id: bookingId } });
      await loadRazorpay();
      const checkoutResponse = await openCheckout(order);
      try {
        return await api("/payments/verify", { method: "POST", body: checkoutResponse });
      } catch (error) {
        if (error instanceof ApiError && (error.status === 0 || error.status >= 500)) {
          // The webhook will still confirm or refund it (PRD §16 "Payment Verification Pending").
          throw new Error("Your payment is being verified. Please check your booking status shortly.");
        }
        throw error;
      }
    },
    onSuccess: (result) => {
      queryClient.setQueryData(["booking", bookingId], result.booking);
      setNotice({ kind: result.outcome === "refunded" ? "warning" : "success", text: result.message });
      queryClient.invalidateQueries({ queryKey: ["bookings"] });
    },
    onError: refresh,
  });

  const cancel = useMutation({
    mutationFn: () => api(`/bookings/${bookingId}/cancel`, { method: "POST" }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["booking", bookingId], updated);
      queryClient.invalidateQueries({ queryKey: ["bookings"] });
    },
  });

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <Link to="/bookings" className="text-sm font-medium text-brand-700 hover:underline">
        ← My bookings
      </Link>
      <QueryState query={booking}>
        {(data) => (
          <BookingView
            booking={data}
            notice={notice}
            pay={pay}
            cancel={cancel}
            onExpired={refresh}
          />
        )}
      </QueryState>
    </div>
  );
}

function BookingView({ booking, notice, pay, cancel, onExpired }) {
  const now = useNow();
  const remaining = booking.expires_at ? new Date(booking.expires_at).getTime() - now : 0;
  const holdActive = booking.status === "PENDING" && remaining > 0;

  useEffect(() => {
    if (booking.status === "PENDING" && booking.expires_at && remaining <= 0) onExpired();
  }, [booking.status, booking.expires_at, remaining <= 0]); // eslint-disable-line react-hooks/exhaustive-deps

  const heading = {
    PENDING: holdActive ? "Review your booking" : "Payment window closed",
    CONFIRMED: "Booking confirmed",
    COMPLETED: "Session completed",
    CANCELLED: "Booking cancelled",
    EXPIRED: "Booking expired",
    FAILED: "Booking not completed",
  }[booking.status];

  const payError = pay.error && !(pay.error instanceof CheckoutDismissed) ? pay.error.message : null;

  return (
    <Card className="mt-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">{heading}</h1>
          <p className="mt-1 text-sm text-slate-500">Booking ID {booking.reference}</p>
        </div>
        <StatusBadge status={booking.status} />
      </div>

      {notice && (
        <Alert kind={notice.kind} className="mt-4">
          {notice.text}
        </Alert>
      )}
      {booking.status === "CONFIRMED" && !notice && (
        <Alert kind="success" className="mt-4">
          You're all set. A confirmation has been sent to your email and phone, and we'll remind you before the session.
        </Alert>
      )}

      <dl className="mt-6 divide-y divide-slate-100 text-sm">
        <Row label="Webinar">{booking.webinar.title}</Row>
        <Row label="Date">{formatDate(booking.slot.start_at)}</Row>
        <Row label="Time">{formatTimeRange(booking.slot.start_at, booking.slot.end_at)}</Row>
        <Row label="Duration">{formatDuration(booking.webinar.duration_minutes)}</Row>
        <Row label={booking.status === "CONFIRMED" || booking.status === "COMPLETED" ? "Amount paid" : "Total"}>
          {formatINR(booking.amount_paise)}
        </Row>
        <Row label="Payment">
          <StatusBadge status={booking.payment_status} />
        </Row>
      </dl>

      {holdActive && (
        <>
          <Alert kind="warning" className="mt-6">
            Your seat is held for <strong className="tabular-nums">{formatCountdown(remaining)}</strong>. Complete the
            payment before then to confirm your booking.
          </Alert>
          {pay.error instanceof CheckoutDismissed && (
            <Alert kind="info" className="mt-3">
              Payment was not completed. You can try again while your seat is held.
            </Alert>
          )}
          {payError && (
            <Alert kind="error" className="mt-3">
              {payError}
            </Alert>
          )}
          {cancel.isError && (
            <Alert kind="error" className="mt-3">
              {cancel.error.message}
            </Alert>
          )}
          <div className="mt-6 flex flex-col gap-3 sm:flex-row-reverse">
            <Button size="lg" className="sm:flex-1" loading={pay.isPending} onClick={() => pay.mutate()}>
              Proceed to Payment · {formatINR(booking.amount_paise)}
            </Button>
            <Button
              size="lg"
              variant="secondary"
              loading={cancel.isPending}
              disabled={pay.isPending}
              onClick={() => window.confirm("Cancel this booking and release your seat?") && cancel.mutate()}
            >
              Cancel booking
            </Button>
          </div>
        </>
      )}

      {["EXPIRED", "CANCELLED", "FAILED"].includes(booking.status) || (booking.status === "PENDING" && !holdActive) ? (
        <div className="mt-6">
          <p className="text-sm text-slate-600">
            {booking.payment_status === "REFUNDED"
              ? "Any amount paid for this booking has been refunded."
              : "No payment was taken for this booking."}
          </p>
          <Button className="mt-4" variant="secondary" to={`/webinars/${booking.webinar.id}`}>
            Book this webinar again
          </Button>
        </div>
      ) : null}

      {booking.status === "CONFIRMED" && (
        <div className="mt-6 flex flex-wrap gap-3">
          <Button to="/bookings">View My Bookings</Button>
          <Button variant="secondary" to="/webinars">
            Browse more webinars
          </Button>
        </div>
      )}
    </Card>
  );
}
