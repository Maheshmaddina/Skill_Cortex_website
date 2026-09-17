import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { useAuth } from "../auth/AuthContext.jsx";
import { api } from "../lib/api.js";
import Logo from "./Logo.jsx";
import { Button } from "./ui.jsx";

const CONTACT_EMAIL = import.meta.env.VITE_CONTACT_EMAIL ?? "info@skillcortexai.com";

function navLinks(user) {
  if (!user) return [["/webinars", "Webinars"]];
  if (user.role === "ADMIN") return [["/webinars", "Webinars"], ["/admin", "Admin"]];
  return [
    ["/webinars", "Webinars"],
    ["/dashboard", "Dashboard"],
    ["/bookings", "My Bookings"],
    ["/notifications", "Notifications"],
  ];
}

/** Bell + count of messages that arrived since the learner last opened Notifications. */
function NotificationsLabel({ count }) {
  return (
    <span className="inline-flex items-center gap-3">
      <span className="relative">
        <svg className="size-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.4-1.4A2 2 0 0 1 18 14.2V11a6 6 0 1 0-12 0v3.2a2 2 0 0 1-.6 1.4L4 17h5m6 0v1a3 3 0 1 1-6 0v-1m6 0H9" />
        </svg>
        {count > 0 && (
          <span className="absolute -top-2 -right-2.5 grid min-w-5 place-items-center rounded-full bg-rose-600 px-1 text-[0.65rem] leading-5 font-bold text-white">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </span>
      Notifications
      {count > 0 && <span className="sr-only">({count} new)</span>}
    </span>
  );
}

function linkClass({ isActive }) {
  return `rounded-lg px-3 py-2 text-sm font-medium ${isActive ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"}`;
}

export default function Layout() {
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => setMenuOpen(false), [location.pathname]);

  const unread = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: () => api("/notifications/unread-count"),
    enabled: user?.role === "USER",
    refetchInterval: 60_000,
  });
  const unreadCount = user?.role === "USER" ? (unread.data?.count ?? 0) : 0;
  const label = (to, text) => (to === "/notifications" ? <NotificationsLabel count={unreadCount} /> : text);

  async function handleLogout() {
    await logout();
    navigate("/");
  }

  const account = user ? (
    <>
      <NavLink
        to="/profile"
        title={`${user.name} — profile`}
        aria-label={`Your profile (${user.name})`}
        className={({ isActive }) =>
          `grid size-9 place-items-center rounded-full bg-brand-500 text-sm font-bold uppercase text-white ring-2 ring-offset-2 transition hover:bg-brand-600 ${isActive ? "ring-brand-500" : "ring-transparent"}`
        }
      >
        {user.name.trim().charAt(0) || "?"}
      </NavLink>
      <Button variant="ghost" onClick={handleLogout}>
        Log out
      </Button>
    </>
  ) : (
    <>
      <Button variant="ghost" to="/login">
        Log in
      </Button>
      <Button to="/register">Register</Button>
    </>
  );

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur print:hidden">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <Logo />
          <nav className="hidden items-center gap-1 md:flex" aria-label="Main">
            {navLinks(user).map(([to, text]) => (
              <NavLink key={to} to={to} end={to === "/admin" ? false : undefined} className={linkClass}>
                {label(to, text)}
              </NavLink>
            ))}
          </nav>
          <div className="hidden items-center gap-2 md:flex">{account}</div>
          <button
            type="button"
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 md:hidden"
            aria-expanded={menuOpen}
            aria-label="Toggle menu"
            onClick={() => setMenuOpen((open) => !open)}
          >
            <svg className="size-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" d={menuOpen ? "M6 6l12 12M6 18L18 6" : "M4 7h16M4 12h16M4 17h16"} />
            </svg>
          </button>
        </div>
        {menuOpen && (
          <nav className="flex flex-col gap-1 border-t border-slate-200 px-4 py-3 md:hidden" aria-label="Mobile">
            {navLinks(user).map(([to, text]) => (
              <NavLink key={to} to={to} className={linkClass}>
                {label(to, text)}
              </NavLink>
            ))}
            <div className="mt-2 flex items-center gap-2 border-t border-slate-100 pt-3">{account}</div>
          </nav>
        )}
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="bg-ink text-slate-300 print:hidden">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 text-sm sm:grid-cols-2">
          <div>
            <Logo light />
            <p className="mt-3 max-w-sm">
              SkillCortex AI builds technology and develops talent — live webinars and courses for CSE, AI/ML and Data
              Science learners.
            </p>
          </div>
          <address className="not-italic sm:text-right">
            <p>#17/2-F-4-1-3, SreeNagar Colony, Punganur Road, Madanapalle</p>
            <p className="mt-1">
              <a className="hover:text-white" href="tel:+919032756326">+91 90327 56326</a>,{" "}
              <a className="hover:text-white" href="tel:+916281460747">+91 62814 60747</a>
            </p>
            <p className="mt-1">
              <a className="font-medium text-brand-400 hover:underline" href={`mailto:${CONTACT_EMAIL}`}>
                {CONTACT_EMAIL}
              </a>
            </p>
          </address>
        </div>
        <div className="border-t border-white/10">
          <p className="mx-auto max-w-6xl px-4 py-4 text-xs text-slate-400">© {new Date().getFullYear()} SkillCortex AI</p>
        </div>
      </footer>
    </div>
  );
}
