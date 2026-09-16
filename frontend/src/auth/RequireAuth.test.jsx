import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RequireAuth, { safeNext } from "./RequireAuth.jsx";

let authState;
vi.mock("./AuthContext.jsx", () => ({ useAuth: () => authState }));

function ShowLocation() {
  const location = useLocation();
  return <p>at {location.pathname + location.search}</p>;
}

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<RequireAuth role="USER" />}>
          <Route path="/bookings" element={<p>my bookings</p>} />
        </Route>
        <Route
          path="/admin"
          element={
            <RequireAuth role="ADMIN">
              <p>admin area</p>
            </RequireAuth>
          }
        />
        <Route path="*" element={<ShowLocation />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RequireAuth", () => {
  beforeEach(() => {
    authState = { status: "ready", user: null };
  });

  it("sends guests to login and remembers where they were going", () => {
    renderAt("/bookings?scope=past");

    expect(screen.getByText("at /login?next=%2Fbookings%3Fscope%3Dpast")).toBeInTheDocument();
  });

  it("lets learners into learner pages but not the admin area", () => {
    authState.user = { role: "USER" };

    renderAt("/bookings");
    expect(screen.getByText("my bookings")).toBeInTheDocument();
  });

  it("redirects a learner away from admin pages", () => {
    authState.user = { role: "USER" };

    renderAt("/admin");
    expect(screen.getByText("at /dashboard")).toBeInTheDocument();
  });

  it("lets admins into the admin area", () => {
    authState.user = { role: "ADMIN" };

    renderAt("/admin");
    expect(screen.getByText("admin area")).toBeInTheDocument();
  });

  it("waits while the session is being restored", () => {
    authState = { status: "loading", user: null };

    renderAt("/bookings");
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
  });

  it("only allows relative post-login redirects", () => {
    expect(safeNext("/bookings")).toBe("/bookings");
    expect(safeNext("//evil.example.com")).toBeNull();
    expect(safeNext("https://evil.example.com")).toBeNull();
  });
});
