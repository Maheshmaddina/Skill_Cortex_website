import { describe, expect, it } from "vitest";

import {
  PREFERRED_TIMES,
  countdownParts,
  formatClock,
  formatCountdown,
  formatDate,
  formatDateTime,
  formatDuration,
  formatINR,
  formatLocalDate,
  formatStartsIn,
  formatTimeRange,
  fromISTInput,
  humanize,
  istDate,
  rupeesToPaise,
  toISTInput,
} from "./format.js";

describe("money", () => {
  it("formats paise as rupees with Indian grouping", () => {
    expect(formatINR(99_900)).toBe("₹999");
    expect(formatINR(14_990_050)).toBe("₹1,49,900.50");
    expect(formatINR(0)).toBe("Free");
  });

  it("converts rupee input to paise without float drift", () => {
    expect(rupeesToPaise("999")).toBe(99_900);
    expect(rupeesToPaise("19.99")).toBe(1_999);
  });
});

describe("dates are shown in IST", () => {
  const start = "2026-09-20T04:30:00Z"; // 10:00 AM IST

  it("formats dates and times", () => {
    expect(formatDate(start)).toBe("Sun, 20 Sep 2026");
    expect(formatDateTime(start)).toBe("Sun, 20 Sep 2026, 10:00 AM IST");
    expect(formatTimeRange(start, "2026-09-20T05:30:00Z")).toBe("10:00 AM – 11:00 AM IST");
  });

  it("round-trips datetime-local inputs through IST", () => {
    expect(toISTInput(start)).toBe("2026-09-20T10:00");
    expect(fromISTInput("2026-09-20T10:00")).toBe("2026-09-20T10:00:00+05:30");
    expect(new Date(fromISTInput(toISTInput(start))).toISOString()).toBe("2026-09-20T04:30:00.000Z");
    expect(toISTInput("2026-09-20T18:45:00Z")).toBe("2026-09-21T00:15");
  });
});

describe("misc", () => {
  it("formats durations, countdowns and enum labels", () => {
    expect(formatDuration(90)).toBe("1 hr 30 min");
    expect(formatDuration(60)).toBe("1 hr");
    expect(formatCountdown(14 * 60_000 + 5_000)).toBe("14:05");
    expect(formatCountdown(-1)).toBe("0:00");
    expect(humanize("BOOKING_CONFIRMATION")).toBe("Booking confirmation");
  });
});

describe("session countdown", () => {
  const MINUTE = 60_000;
  const HOUR = 60 * MINUTE;
  const DAY = 24 * HOUR;

  it("splits the time left into days, hours, minutes and seconds", () => {
    expect(countdownParts(2 * DAY + 3 * HOUR + 4 * MINUTE + 5_900)).toEqual({ days: 2, hours: 3, minutes: 4, seconds: 5 });
    expect(countdownParts(-5_000)).toEqual({ days: 0, hours: 0, minutes: 0, seconds: 0 });
  });

  it("summarises it for booking lists", () => {
    expect(formatStartsIn(2 * DAY + 4 * HOUR + 30 * MINUTE)).toBe("Starts in 2d 4h");
    expect(formatStartsIn(3 * HOUR + 12 * MINUTE)).toBe("Starts in 3h 12m");
    expect(formatStartsIn(5 * MINUTE + 20_000)).toBe("Starts in 5m");
    expect(formatStartsIn(30_000)).toBe("Starting now");
  });
});

describe("learner-chosen dates and times", () => {
  it("offers half-hour start times from 7 AM to 9 PM", () => {
    expect(PREFERRED_TIMES[0]).toBe("07:00");
    expect(PREFERRED_TIMES[1]).toBe("07:30");
    expect(PREFERRED_TIMES.at(-1)).toBe("21:00");
    expect(PREFERRED_TIMES).toHaveLength(29);
  });

  it("formats clock times and calendar dates", () => {
    expect(formatClock("18:30")).toBe("6:30 PM");
    expect(formatClock("12:00:00")).toBe("12:00 PM");
    expect(formatClock("07:00")).toBe("7:00 AM");
    expect(formatLocalDate("2026-09-20")).toBe("Sun, 20 Sep 2026");
  });

  it("works out IST dates, even when UTC is still on the previous day", () => {
    const lateEveningUtc = Date.parse("2026-09-16T20:00:00Z"); // 17 Sep, 1:30 AM IST
    expect(istDate(0, lateEveningUtc)).toBe("2026-09-17");
    expect(istDate(1, lateEveningUtc)).toBe("2026-09-18");
  });
});
