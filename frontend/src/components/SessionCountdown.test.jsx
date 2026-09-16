import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SessionCountdown from "./SessionCountdown.jsx";

const START = "2026-09-20T04:30:00Z";
const END = "2026-09-20T06:30:00Z";

function timerText() {
  return screen.getByRole("timer").textContent;
}

describe("SessionCountdown", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("counts down every second to the start", () => {
    vi.setSystemTime(new Date("2026-09-18T02:28:55Z")); // 2d 2h 1m 5s before
    render(<SessionCountdown start={START} end={END} />);

    expect(timerText()).toBe("Starts in02Days02Hours01Minutes05Seconds");
    act(() => vi.advanceTimersByTime(1000));
    expect(timerText()).toContain("04Seconds");
  });

  it("shows live while the session runs, then ended", () => {
    vi.setSystemTime(new Date("2026-09-20T04:29:59Z"));
    render(<SessionCountdown start={START} end={END} />);

    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText(/Live now/)).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(2 * 60 * 60 * 1000));
    expect(screen.getByText("This session has ended.")).toBeInTheDocument();
  });
});
