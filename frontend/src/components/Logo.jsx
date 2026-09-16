import { Link } from "react-router";

export default function Logo({ to = "/", light = false }) {
  return (
    <Link to={to} className="flex items-center gap-2.5 font-bold">
      <img src="/brand/logo.png" alt="" width="40" height="40" className="size-10 rounded-full bg-white" />
      <span className={`text-xl tracking-tight ${light ? "text-white" : "text-slate-900"}`}>
        Skill <span className="text-brand-500">Cortex</span>
      </span>
    </Link>
  );
}
