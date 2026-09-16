import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { homeFor } from "../auth/RequireAuth.jsx";
import { useAuth } from "../auth/AuthContext.jsx";
import WebinarCard from "../components/WebinarCard.jsx";
import { Button, PageSpinner } from "../components/ui.jsx";
import { api } from "../lib/api.js";

const STEPS = [
  ["Discover", "Browse live webinars for your department."],
  ["Book", "Pick a date and time that suits you — seats update live."],
  ["Pay securely", "Checkout with Razorpay: UPI, cards or netbanking."],
  ["Get reminded", "Confirmation plus reminders by email and SMS before the session."],
];

const BENEFITS = [
  ["Expert-led, live sessions", "Practical courses in programming, AI/ML and data — ask questions in real time."],
  ["Clear pricing and seats", "See the price, duration and exact seats left before you book."],
  ["Instant confirmation", "Your booking is confirmed the moment your payment is verified."],
  ["Never miss a session", "Automatic reminders 3 days, 1 day and on the day of your webinar."],
];

export default function Landing() {
  const { user } = useAuth();
  const departments = useQuery({ queryKey: ["departments"], queryFn: () => api("/departments") });
  const featured = useQuery({
    queryKey: ["webinars", { page_size: 6 }],
    queryFn: () => api("/webinars", { query: { page_size: 6 } }),
  });

  return (
    <>
      <section className="relative isolate overflow-hidden bg-ink">
        <img
          src="/brand/hero.jpg"
          alt=""
          className="absolute inset-0 -z-10 size-full object-cover object-[70%_center]"
          fetchPriority="high"
        />
        <div className="absolute inset-0 -z-10 bg-gradient-to-r from-black/80 via-black/55 to-black/20" />
        <div className="mx-auto max-w-6xl px-4 py-24 sm:py-32">
          <p className="text-sm font-semibold uppercase tracking-wide text-brand-400">
            Your journey into the tech industry starts here
          </p>
          <h1 className="mt-3 max-w-3xl text-4xl font-bold tracking-tight text-white sm:text-5xl">
            Empower your career with industry-aligned, expert-led live sessions
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-slate-200">
            Skill Cortex AI brings Computer Science, AI/ML and Data Science webinars together in one place. Choose your
            department, book a slot, pay securely and we'll remind you before it starts.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button size="lg" to="/webinars">
              Explore Webinars
            </Button>
            {user ? (
              <Button size="lg" variant="secondary" to={homeFor(user)}>
                Go to dashboard
              </Button>
            ) : (
              <Button size="lg" variant="secondary" to="/register">
                Register Now
              </Button>
            )}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16">
        <h2 className="text-2xl font-bold tracking-tight">How it works</h2>
        <ol className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map(([title, text], index) => (
            <li key={title} className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
              <span className="grid size-9 place-items-center rounded-full bg-brand-500 font-bold text-white">{index + 1}</span>
              <p className="mt-4 font-semibold">{title}</p>
              <p className="mt-1 text-sm text-slate-600">{text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-16">
        <h2 className="text-2xl font-bold tracking-tight">Departments</h2>
        {departments.isPending ? (
          <PageSpinner />
        ) : (
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {(departments.data ?? []).map((department) => (
              <Link
                key={department.id}
                to={`/webinars?department_id=${department.id}`}
                className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200 transition hover:ring-brand-300"
              >
                <p className="font-semibold text-slate-900">{department.name}</p>
                {department.description && <p className="mt-1 text-sm text-slate-600">{department.description}</p>}
                <p className="mt-3 text-sm font-medium text-brand-700">View webinars →</p>
              </Link>
            ))}
          </div>
        )}
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-16">
        <div className="flex items-end justify-between gap-4">
          <h2 className="text-2xl font-bold tracking-tight">Featured webinars</h2>
          <Link to="/webinars" className="text-sm font-semibold text-brand-700 hover:underline">
            See all →
          </Link>
        </div>
        {featured.isPending ? (
          <PageSpinner />
        ) : featured.data?.items.length ? (
          <div className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {featured.data.items.map((webinar) => (
              <WebinarCard key={webinar.id} webinar={webinar} />
            ))}
          </div>
        ) : (
          <p className="mt-6 text-slate-500">New webinars are coming soon.</p>
        )}
      </section>

      <section className="bg-white">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-16 sm:grid-cols-2">
          <div>
            <h2 className="text-2xl font-bold tracking-tight">Why Skill Cortex</h2>
            <p className="mt-3 text-slate-600">
              No more chasing registrations over messages or wondering whether your payment went through.
            </p>
          </div>
          <dl className="grid gap-6">
            {BENEFITS.map(([title, text]) => (
              <div key={title}>
                <dt className="font-semibold text-slate-900">{title}</dt>
                <dd className="mt-1 text-sm text-slate-600">{text}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16">
        <div className="rounded-3xl bg-brand-500 px-6 py-12 text-center text-white sm:px-12">
          <h2 className="text-2xl font-bold">Ready to learn something new this week?</h2>
          <p className="mt-2 text-white/90">Pick a webinar, reserve your seat and we'll handle the rest.</p>
          <div className="mt-6 flex justify-center gap-3">
            <Button size="lg" variant="secondary" to="/webinars">
              Explore Webinars
            </Button>
          </div>
        </div>
      </section>
    </>
  );
}
