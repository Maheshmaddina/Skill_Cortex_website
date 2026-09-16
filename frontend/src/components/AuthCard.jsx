import { Card } from "./ui.jsx";

export default function AuthCard({ title, subtitle, children, footer }) {
  return (
    <div className="relative isolate grid min-h-[calc(100svh-4rem)] place-items-center overflow-hidden bg-ink">
      <img src="/brand/hero.jpg" alt="" className="absolute inset-0 -z-10 size-full object-cover" />
      <div className="absolute inset-0 -z-10 bg-black/60" />
      <div className="w-full max-w-md px-4 py-12 sm:py-16">
        <Card>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
          <div className="mt-6">{children}</div>
          {footer && <div className="mt-6 border-t border-slate-100 pt-4 text-center text-sm text-slate-600">{footer}</div>}
        </Card>
      </div>
    </div>
  );
}
