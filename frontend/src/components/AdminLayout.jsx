import { NavLink, Outlet, useNavigate } from "react-router";

import { useAuth } from "../auth/AuthContext.jsx";
import Logo from "./Logo.jsx";
import { Button } from "./ui.jsx";

const LINKS = [
  ["/admin", "Dashboard", true],
  ["/admin/departments", "Departments"],
  ["/admin/webinars", "Webinars & slots"],
  ["/admin/learner-webinars", "Learner webinars"],
  ["/admin/bookings", "Bookings"],
  ["/admin/payments", "Payments"],
  ["/admin/users", "Users"],
  ["/admin/notifications", "Notifications"],
  ["/admin/reminders", "Reminders"],
];

function linkClass({ isActive }) {
  return `whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium ${isActive ? "bg-brand-500 text-white" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"}`;
}

export default function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/");
  }

  return (
    <div className="min-h-screen lg:flex">
      <aside className="border-b border-slate-200 bg-white lg:sticky lg:top-0 lg:h-screen lg:w-60 lg:shrink-0 lg:border-r lg:border-b-0">
        <div className="flex items-center justify-between px-4 py-4 lg:block">
          <Logo to="/admin" />
          <p className="hidden text-xs font-semibold uppercase tracking-wide text-slate-400 lg:mt-1 lg:block">Admin</p>
          <div className="flex gap-2 lg:hidden">
            <Button variant="secondary" size="sm" to="/webinars">
              View site
            </Button>
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              Log out
            </Button>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 lg:flex-col lg:overflow-visible" aria-label="Admin">
          {LINKS.map(([to, label, end]) => (
            <NavLink key={to} to={to} end={end} className={linkClass}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="hidden border-t border-slate-100 px-4 py-4 text-sm lg:absolute lg:bottom-0 lg:block lg:w-60">
          <p className="truncate font-medium text-slate-900">{user?.name}</p>
          <p className="truncate text-slate-500">{user?.email}</p>
          <div className="mt-3 flex gap-2">
            <Button variant="secondary" size="sm" to="/webinars">
              View site
            </Button>
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              Log out
            </Button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 lg:px-8 lg:py-8">
        <Outlet />
      </main>
    </div>
  );
}
