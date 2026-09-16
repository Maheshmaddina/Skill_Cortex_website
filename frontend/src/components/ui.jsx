import { useId } from "react";
import { Link } from "react-router";

import { humanize } from "../lib/format.js";

const BUTTON_VARIANTS = {
  primary: "bg-brand-500 text-white shadow-sm hover:bg-brand-600 focus-visible:outline-brand-600",
  secondary: "bg-white text-slate-700 shadow-sm ring-1 ring-inset ring-slate-300 hover:bg-slate-50",
  danger: "bg-rose-600 text-white shadow-sm hover:bg-rose-500 focus-visible:outline-rose-600",
  ghost: "text-slate-600 hover:bg-slate-100",
};

const BUTTON_SIZES = {
  sm: "px-2.5 py-1.5 text-xs",
  md: "px-4 py-2 text-sm",
  lg: "px-6 py-3 text-base",
};

export function Button({ variant = "primary", size = "md", loading = false, to, className = "", children, ...props }) {
  const classes = `inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${BUTTON_VARIANTS[variant]} ${BUTTON_SIZES[size]} ${className}`;
  if (to) {
    return (
      <Link to={to} className={classes}>
        {children}
      </Link>
    );
  }
  return (
    <button type="button" {...props} disabled={loading || props.disabled} className={classes}>
      {loading && <Spinner className="size-4" />}
      {children}
    </button>
  );
}

const CONTROL =
  "mt-1 block w-full rounded-lg border-0 bg-white px-3 py-2 text-slate-900 shadow-sm ring-1 ring-inset placeholder:text-slate-400 focus:ring-2 focus:ring-inset focus:ring-brand-600 disabled:bg-slate-100 sm:text-sm";

function FieldShell({ id, label, error, hint, className = "", children }) {
  return (
    <div className={className}>
      {label && (
        <label htmlFor={id} className="block text-sm font-medium text-slate-700">
          {label}
        </label>
      )}
      {children}
      {error ? (
        <p className="mt-1 text-sm text-rose-600">{error}</p>
      ) : (
        hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>
      )}
    </div>
  );
}

export function Input({ label, error, hint, className, ...props }) {
  const id = useId();
  return (
    <FieldShell id={id} label={label} error={error} hint={hint} className={className}>
      <input
        id={id}
        aria-invalid={Boolean(error)}
        className={`${CONTROL} ${error ? "ring-rose-400" : "ring-slate-300"}`}
        {...props}
      />
    </FieldShell>
  );
}

export function Select({ label, error, hint, className, children, ...props }) {
  const id = useId();
  return (
    <FieldShell id={id} label={label} error={error} hint={hint} className={className}>
      <select id={id} aria-invalid={Boolean(error)} className={`${CONTROL} ${error ? "ring-rose-400" : "ring-slate-300"}`} {...props}>
        {children}
      </select>
    </FieldShell>
  );
}

export function Textarea({ label, error, hint, className, ...props }) {
  const id = useId();
  return (
    <FieldShell id={id} label={label} error={error} hint={hint} className={className}>
      <textarea id={id} aria-invalid={Boolean(error)} className={`${CONTROL} ${error ? "ring-rose-400" : "ring-slate-300"}`} {...props} />
    </FieldShell>
  );
}

export function Checkbox({ label, className = "", ...props }) {
  return (
    <label className={`inline-flex items-center gap-2 text-sm text-slate-700 ${className}`}>
      <input type="checkbox" className="size-4 rounded border-slate-300 text-brand-700 focus:ring-brand-600" {...props} />
      {label}
    </label>
  );
}

export function Card({ className = "", children }) {
  return <div className={`rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200 ${className}`}>{children}</div>;
}

const BADGE_COLORS = {
  slate: "bg-slate-100 text-slate-700 ring-slate-500/10",
  brand: "bg-brand-50 text-brand-700 ring-brand-600/20",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  amber: "bg-amber-50 text-amber-800 ring-amber-600/20",
  red: "bg-rose-50 text-rose-700 ring-rose-600/20",
};

export function Badge({ color = "brand", children }) {
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${BADGE_COLORS[color]}`}>
      {children}
    </span>
  );
}

const STATUS_COLORS = {
  ACTIVE: "green",
  CONFIRMED: "green",
  PAID: "green",
  SENT: "green",
  DELIVERED: "green",
  COMPLETED: "brand",
  PENDING: "amber",
  FAILED: "red",
  EXPIRED: "red",
  CANCELLED: "slate",
  INACTIVE: "slate",
  REFUNDED: "slate",
};

export function StatusBadge({ status }) {
  if (!status) return <span className="text-slate-400">—</span>;
  return <Badge color={STATUS_COLORS[status] ?? "slate"}>{humanize(status)}</Badge>;
}

export function Spinner({ className = "size-6" }) {
  return (
    <svg className={`animate-spin text-current ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}

export function PageSpinner() {
  return (
    <div className="flex justify-center py-24 text-brand-700" role="status" aria-label="Loading">
      <Spinner className="size-8" />
    </div>
  );
}

const ALERT_STYLES = {
  error: "bg-rose-50 text-rose-800 ring-rose-200",
  success: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  info: "bg-sky-50 text-sky-800 ring-sky-200",
  warning: "bg-amber-50 text-amber-900 ring-amber-200",
};

export function Alert({ kind = "info", title, children, className = "" }) {
  return (
    <div role={kind === "error" ? "alert" : "status"} className={`rounded-xl p-4 text-sm ring-1 ${ALERT_STYLES[kind]} ${className}`}>
      {title && <p className="font-semibold">{title}</p>}
      {children && <div className={title ? "mt-1" : ""}>{children}</div>}
    </div>
  );
}

export function EmptyState({ title, description, action }) {
  return (
    <div className="rounded-2xl border-2 border-dashed border-slate-200 px-6 py-12 text-center">
      <p className="font-semibold text-slate-900">{title}</p>
      {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Pagination({ page, pageSize, total, onChange }) {
  if (total <= pageSize) return null;
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  return (
    <nav className="mt-6 flex items-center justify-between text-sm text-slate-600" aria-label="Pagination">
      <p>
        Showing {first}–{last} of {total}
      </p>
      <div className="flex gap-2">
        <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          Previous
        </Button>
        <Button variant="secondary" size="sm" disabled={last >= total} onClick={() => onChange(page + 1)}>
          Next
        </Button>
      </div>
    </nav>
  );
}

/** Renders loading / error states for a react-query result, then `children(data)`. */
export function QueryState({ query, children }) {
  if (query.isPending) return <PageSpinner />;
  if (query.isError) return <Alert kind="error">{query.error.message}</Alert>;
  return children(query.data);
}

export function Table({ headers, children }) {
  return (
    <div className="overflow-x-auto rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr>
            {headers.map((header) => (
              <th key={header} scope="col" className="whitespace-nowrap px-4 py-3 text-left font-semibold text-slate-700">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">{children}</tbody>
      </table>
    </div>
  );
}

export function Td({ className = "", children, ...props }) {
  return (
    <td className={`px-4 py-3 align-top text-slate-700 ${className}`} {...props}>
      {children}
    </td>
  );
}
