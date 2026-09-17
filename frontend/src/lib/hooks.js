import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

/**
 * URL search params as a plain object plus an updater. Changing any filter resets `page`,
 * so list pages keep their filters and paging in the URL (shareable, back-button friendly).
 */
export function useQueryParams() {
  const [params, setParams] = useSearchParams();
  const values = Object.fromEntries(params.entries());

  function update(changes) {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        for (const [key, value] of Object.entries(changes)) {
          if (value === undefined || value === null || value === "") next.delete(key);
          else next.set(key, String(value));
        }
        if (!("page" in changes)) next.delete("page");
        return next;
      },
      { replace: true },
    );
  }

  return [values, update];
}

const HEARTBEAT_MS = 2 * 60_000;

/**
 * While the site is open, ping the API so its background jobs (seat-hold release, reminders,
 * email/SMS delivery) keep running on hosts without a scheduler. The server runs them at most
 * once a minute however many visitors ping; failures are ignored.
 */
export function useJobsHeartbeat(apiUrl) {
  useEffect(() => {
    const ping = () => {
      if (document.visibilityState !== "visible") return;
      fetch(new URL(`${apiUrl}/internal/tick`, window.location.origin), { method: "POST", keepalive: true }).catch(() => {});
    };
    ping();
    const id = setInterval(ping, HEARTBEAT_MS);
    document.addEventListener("visibilitychange", ping);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", ping);
    };
  }, [apiUrl]);
}
