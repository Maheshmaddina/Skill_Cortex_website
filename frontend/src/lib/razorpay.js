const CHECKOUT_SCRIPT = "https://checkout.razorpay.com/v1/checkout.js";

let loading;

export function loadRazorpay() {
  if (window.Razorpay) return Promise.resolve();
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = CHECKOUT_SCRIPT;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      loading = undefined;
      reject(new Error("Couldn't load Razorpay Checkout. Check your connection and try again."));
    };
    document.body.appendChild(script);
  });
  return loading;
}

export class CheckoutDismissed extends Error {}

/**
 * Open Razorpay Checkout for an order from POST /payments/create-order.
 * Resolves with {razorpay_order_id, razorpay_payment_id, razorpay_signature} — which must still be
 * verified by the backend — or rejects with CheckoutDismissed if the learner closes it.
 * Failed attempts stay inside Checkout so the learner can retry.
 */
export function openCheckout(order) {
  return new Promise((resolve, reject) => {
    const checkout = new window.Razorpay({
      key: order.key_id,
      order_id: order.order_id,
      amount: order.amount_paise,
      currency: order.currency,
      name: "Skill Cortex",
      description: `${order.webinar_title} · ${order.booking_reference}`,
      prefill: order.prefill,
      notes: { booking_reference: order.booking_reference },
      theme: { color: "#ff6b00" },
      // UPI first. Razorpay only shows methods enabled on the account: UPI apps on phones need
      // "UPI intent", a UPI ID / QR code on laptops needs "UPI" (Dashboard → Payment Methods).
      config: {
        display: {
          blocks: { upi: { name: "Pay using UPI", instruments: [{ method: "upi" }] } },
          sequence: ["block.upi"],
          preferences: { show_default_blocks: true },
        },
      },
      handler: (response) => resolve(response),
      modal: { ondismiss: () => reject(new CheckoutDismissed("Payment was not completed.")) },
    });
    checkout.open();
  });
}
