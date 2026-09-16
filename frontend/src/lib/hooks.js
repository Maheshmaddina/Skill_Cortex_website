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
