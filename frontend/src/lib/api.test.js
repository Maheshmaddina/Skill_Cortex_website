import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, fieldErrors, setAccessToken } from "./api.js";

function jsonResponse(status, body) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  setAccessToken(null);
});

describe("api", () => {
  it("sends the access token and the refresh cookie", async () => {
    setAccessToken("token-1");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(200, { ok: true }));

    await api("/users/me");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url.toString()).toBe("http://localhost:8000/users/me");
    expect(init.headers.Authorization).toBe("Bearer token-1");
    expect(init.credentials).toBe("include");
  });

  it("refreshes an expired access token once and retries the request", async () => {
    setAccessToken("expired");
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(401, { detail: "Not authenticated." }))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: "fresh", user: { id: "u1" } }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));

    await expect(api("/users/me")).resolves.toEqual({ ok: true });

    expect(fetchMock.mock.calls[1][0].toString()).toContain("/auth/refresh");
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe("Bearer fresh");
  });

  it("retries a refresh once when another tab rotated the session at the same moment", async () => {
    setAccessToken("expired");
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(401, { detail: "Not authenticated." }))
      .mockResolvedValueOnce(jsonResponse(401, { detail: "Your session has expired. Please log in again." }))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: "from-other-tab-cookie", user: { id: "u1" } }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));

    await expect(api("/users/me")).resolves.toEqual({ ok: true });

    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(fetchMock.mock.calls[3][1].headers.Authorization).toBe("Bearer from-other-tab-cookie");
  });

  it("does not try to refresh for guests", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(401, { detail: "Not authenticated." }));

    await expect(api("/bookings")).rejects.toMatchObject({ status: 401, message: "Not authenticated." });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("surfaces the API's user-facing message", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(409, { detail: "This slot is full. Please choose another available slot." }),
    );

    const error = await api("/bookings", { method: "POST", body: { slot_id: "s1" } }).catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(409);
    expect(error.message).toBe("This slot is full. Please choose another available slot.");
  });

  it("maps validation errors to form fields", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(422, {
        detail: [{ loc: ["body", "phone"], msg: "Value error, Enter a valid 10-digit Indian mobile number." }],
      }),
    );

    const error = await api("/auth/register", { method: "POST", body: {} }).catch((e) => e);

    expect(fieldErrors(error)).toEqual({ phone: "Enter a valid 10-digit Indian mobile number." });
    expect(error.message).toBe("phone: Enter a valid 10-digit Indian mobile number.");
  });

  it("skips empty query parameters and reports network failures", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(200, { items: [] }));
    await api("/webinars", { query: { q: "", department_id: undefined, page: 2 } });
    expect(fetchMock.mock.calls[0][0].toString()).toBe("http://localhost:8000/webinars?page=2");

    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(api("/webinars")).rejects.toMatchObject({ status: 0 });
  });
});
