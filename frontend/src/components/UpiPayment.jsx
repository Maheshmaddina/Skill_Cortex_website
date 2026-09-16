import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import QRCode from "qrcode";
import { useEffect, useState } from "react";

import { api } from "../lib/api.js";
import { formatINR } from "../lib/format.js";
import { Alert, Button, Input } from "./ui.jsx";

/**
 * Direct UPI: scan the QR (or pay the UPI ID) in any UPI app, then send the 12-digit UTR.
 * The booking is confirmed only after an admin sees the money arrive.
 * Renders nothing when UPI isn't configured on the server (or the booking can't be paid).
 */
export default function UpiPayment({ booking }) {
  const queryClient = useQueryClient();
  const [utr, setUtr] = useState("");
  const [qr, setQr] = useState(null);
  const [copied, setCopied] = useState(false);

  const details = useQuery({
    queryKey: ["upi", booking.id],
    queryFn: () => api("/payments/upi", { query: { booking_id: booking.id } }),
    retry: false,
  });

  useEffect(() => {
    if (!details.data) return;
    QRCode.toDataURL(details.data.upi_uri, { width: 240, margin: 1 }).then(setQr, () => setQr(null));
  }, [details.data]);

  const submit = useMutation({
    mutationFn: () => api("/payments/upi", { method: "POST", body: { booking_id: booking.id, utr } }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["booking", booking.id], updated);
      queryClient.invalidateQueries({ queryKey: ["bookings"] });
    },
  });

  // Not configured (503) or not payable: the card/netbanking option is still shown by the page.
  if (!details.data) return null;
  const upi = details.data;

  async function copyUpiId() {
    try {
      await navigator.clipboard.writeText(upi.upi_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard blocked: the ID is visible to copy by hand */
    }
  }

  return (
    <section className="mt-6 rounded-2xl p-5 ring-1 ring-brand-200" aria-labelledby="upi-heading">
      <h2 id="upi-heading" className="text-lg font-semibold text-slate-900">
        Pay with UPI
      </h2>
      <p className="mt-1 text-sm text-slate-600">GPay, PhonePe, Paytm, BHIM or any bank app.</p>

      <div className="mt-4 grid gap-5 sm:grid-cols-[auto_1fr] sm:items-center">
        {qr && (
          <img
            src={qr}
            alt={`UPI QR code to pay ${formatINR(upi.amount_paise)} to ${upi.payee_name}`}
            width="180"
            height="180"
            className="mx-auto size-44 rounded-xl ring-1 ring-slate-200 sm:mx-0"
          />
        )}
        <dl className="grid gap-2 text-sm">
          <div>
            <dt className="text-slate-500">1. Scan the QR, or pay to UPI ID</dt>
            <dd className="mt-1 flex flex-wrap items-center gap-2">
              <span className="rounded-lg bg-slate-100 px-2 py-1 font-mono font-semibold text-slate-900">{upi.upi_id}</span>
              <Button size="sm" variant="ghost" onClick={copyUpiId}>
                {copied ? "Copied ✓" : "Copy"}
              </Button>
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Amount</dt>
            <dd className="font-semibold text-slate-900">{formatINR(upi.amount_paise)}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Payee</dt>
            <dd className="text-slate-900">{upi.payee_name}</dd>
          </div>
          <a
            href={upi.upi_uri}
            className="inline-flex w-fit items-center rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white sm:hidden"
          >
            Open UPI app
          </a>
        </dl>
      </div>

      <form
        className="mt-5 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          submit.mutate();
        }}
      >
        <Input
          label="2. Enter the UPI transaction ID (UTR)"
          hint="12-digit number shown as UPI Ref No. / UTR in your UPI app after paying."
          inputMode="numeric"
          autoComplete="off"
          required
          maxLength={14}
          placeholder="e.g. 412345678901"
          value={utr}
          onChange={(e) => setUtr(e.target.value)}
        />
        <Button type="submit" loading={submit.isPending} className="sm:mb-5">
          I have paid
        </Button>
      </form>
      {submit.isError && (
        <Alert kind="error" className="mt-2">
          {submit.error.message}
        </Alert>
      )}
    </section>
  );
}
