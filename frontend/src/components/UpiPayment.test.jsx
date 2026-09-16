import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import UpiPayment from "./UpiPayment.jsx";

const api = vi.fn();
vi.mock("../lib/api.js", async (importOriginal) => ({ ...(await importOriginal()), api: (...args) => api(...args) }));

const booking = { id: "b1", reference: "SC-10005", status: "PENDING" };
const details = {
  upi_id: "skillcortex@okaxis",
  payee_name: "Skill Cortex AI",
  amount_paise: 99_900,
  booking_reference: "SC-10005",
  upi_uri: "upi://pay?pa=skillcortex%40okaxis&am=999.00",
};

function renderUpi() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <UpiPayment booking={booking} />
    </QueryClientProvider>,
  );
}

describe("UpiPayment", () => {
  beforeEach(() => api.mockReset());

  it("shows the UPI ID and sends the UTR for verification", async () => {
    api.mockImplementation((path, options) =>
      options?.method === "POST" ? Promise.resolve({ ...booking, upi_payment: { status: "PENDING" } }) : Promise.resolve(details),
    );
    renderUpi();

    expect(await screen.findByText("skillcortex@okaxis")).toBeInTheDocument();
    expect(screen.getByText("₹999")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open UPI app" })).toHaveAttribute("href", details.upi_uri);

    fireEvent.change(screen.getByLabelText(/UPI transaction ID/), { target: { value: "412345678901" } });
    fireEvent.click(screen.getByRole("button", { name: "I have paid" }));

    await waitFor(() =>
      expect(api).toHaveBeenCalledWith("/payments/upi", { method: "POST", body: { booking_id: "b1", utr: "412345678901" } }),
    );
  });
});
