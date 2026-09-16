/**
 * API client. The access token lives only in memory; the refresh token is an httpOnly cookie
 * the browser sends to /auth/*. An expired access token is refreshed once and the request retried.
 */

export const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

const TAB_RACE_RETRY_MS = 300;

let accessToken = null;
let refreshInFlight = null;
let onSessionChange = () => {};

export class ApiError extends Error {
  constructor(status, message, details) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

export function setAccessToken(token) {
  accessToken = token;
}

/** Called with the new session (or null) whenever a background refresh changes it. */
export function setSessionListener(listener) {
  onSessionChange = listener;
}

function send(path, { method = "GET", body, query, auth = true } = {}) {
  // API_URL may be relative (e.g. "/api" in production, same origin as the site).
  const url = new URL(API_URL + path, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  }
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`;
  return fetch(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "include",
  });
}

async function requestRefresh(retryOnce) {
  const response = await send("/auth/refresh", { method: "POST", auth: false });
  if (response.ok) {
    const session = await response.json();
    accessToken = session.access_token;
    return session;
  }
  if (retryOnce) {
    // Another tab may have just rotated the refresh cookie; the browser now holds the new one.
    await new Promise((resolve) => setTimeout(resolve, TAB_RACE_RETRY_MS));
    return requestRefresh(false);
  }
  accessToken = null;
  return null;
}

/** Exchange the refresh cookie for a new access token. Concurrent callers share one request. */
export function refreshSession() {
  refreshInFlight ??= requestRefresh(accessToken !== null)
    .catch(() => {
      accessToken = null;
      return null;
    })
    .finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}

export async function api(path, options = {}) {
  let response;
  try {
    response = await send(path, options);
    if (response.status === 401 && options.auth !== false && accessToken) {
      const session = await refreshSession();
      onSessionChange(session);
      if (session) response = await send(path, options);
    }
  } catch {
    throw new ApiError(0, "Can't reach Skill Cortex right now. Check your connection and try again.");
  }

  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, errorMessage(data, response.status), data);
  return data;
}

function cleanMessage(message = "") {
  return message.replace(/^Value error, /, "");
}

function errorMessage(data, status) {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => {
        const field = item.loc?.[item.loc.length - 1];
        const label = typeof field === "string" ? field.replaceAll("_", " ") : null;
        return label && label !== "body" ? `${label}: ${cleanMessage(item.msg)}` : cleanMessage(item.msg);
      })
      .join(" ");
  }
  return status >= 500 ? "Something went wrong on our side. Please try again." : "The request could not be completed.";
}

/** Map a 422 validation error to `{fieldName: message}` for form display. */
export function fieldErrors(error) {
  const detail = error?.details?.detail;
  if (!Array.isArray(detail)) return {};
  return Object.fromEntries(detail.map((item) => [item.loc?.[item.loc.length - 1], cleanMessage(item.msg)]));
}
