import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import WebinarCard from "./WebinarCard.jsx";

vi.mock("../auth/AuthContext.jsx", () => ({ useAuth: () => ({ user: { role: "USER" } }) }));

const webinar = {
  id: "w1",
  title: "Python Programming",
  short_description: "Learn Python fundamentals and practical programming.",
  price_paise: 99_900,
  duration_minutes: 90,
  departments: [{ id: "d1", name: "CSE", description: null }],
  next_slot: { id: "s1", start_at: "2026-09-20T04:30:00Z", end_at: "2026-09-20T06:00:00Z", available_seats: 12, is_full: false },
  available_seats: 20,
};

function renderCard(props, preference) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <WebinarCard webinar={{ ...webinar, ...props }} preference={preference} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("WebinarCard", () => {
  it("shows what a learner needs to pick a course", () => {
    renderCard();

    expect(screen.getByRole("heading", { name: "Python Programming" })).toBeInTheDocument();
    expect(screen.getByText("CSE")).toBeInTheDocument();
    expect(screen.getByText("₹999")).toBeInTheDocument();
    expect(screen.getByText("1 hr 30 min")).toBeInTheDocument();
    expect(screen.getByText("Sun, 20 Sep 2026 · 10:00 AM IST")).toBeInTheDocument();
    expect(screen.getByText("12 seats left in this session")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View Details" })).toHaveAttribute("href", "/webinars/w1");
  });

  it("says when there are no open slots", () => {
    renderCard({ next_slot: null, available_seats: 0, price_paise: 0 });

    expect(screen.getByText("No open slots right now")).toBeInTheDocument();
    expect(screen.getByText("Free")).toBeInTheDocument();
    expect(screen.queryByText(/seats left/)).not.toBeInTheDocument();
  });

  it("tells the learner when others already chose the same time", () => {
    const slot = { id: "s9", start_at: "2026-09-22T13:00:00Z", end_at: "2026-09-22T15:00:00Z", available_seats: 59, is_full: false };
    renderCard({ matching_slot: slot }, { date: "2026-09-22", time: "18:30" });

    expect(screen.getByText(/you'll join them/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Set webinar" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View Details" })).toHaveAttribute("href", "/webinars/w1?slot=s9");
  });

  it("lets the learner set the webinar for their chosen date and time", () => {
    renderCard({ matching_slot: null }, { date: "2026-09-22", time: "18:30" });

    expect(screen.getByText("Tue, 22 Sep 2026, 6:30 PM IST")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Set webinar" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View Details" })).toHaveAttribute("href", "/webinars/w1?date=2026-09-22&time=18%3A30");
  });

  it("asks for a time before a webinar can be set", () => {
    renderCard({ matching_slot: null }, { date: "2026-09-22" });

    expect(screen.getByText("Pick a preferred time to set your webinar on Tue, 22 Sep 2026.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
