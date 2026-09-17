import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useAuth } from "../auth/AuthContext.jsx";
import { PreferredDateInput, PreferredTimeSelect } from "../components/SetWebinar.jsx";
import WebinarCard from "../components/WebinarCard.jsx";
import { Button, EmptyState, Input, PageHeader, Pagination, QueryState, Select } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { useQueryParams } from "../lib/hooks.js";

const PAGE_SIZE = 9;
const ALL = "all";

export default function Webinars() {
  const { user, status } = useAuth();
  const [params, setParams] = useQueryParams();
  const [search, setSearch] = useState(params.q ?? "");
  const page = Number(params.page ?? 1);
  const departmentId = params.department_id === ALL ? undefined : params.department_id;

  // Start from the learner's own department; they can switch to any other (decision D2).
  useEffect(() => {
    if (status === "ready" && !params.department_id && user?.department) {
      setParams({ department_id: user.department.id });
    }
  }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  const departments = useQuery({ queryKey: ["departments"], queryFn: () => api("/departments") });
  // Every course open to the chosen department, for the "Select course" dropdown.
  const courses = useQuery({
    queryKey: ["webinars", { departmentId, page_size: 100 }],
    queryFn: () => api("/webinars", { query: { department_id: departmentId, page_size: 100 } }),
  });
  const courseTitles = (courses.data?.items ?? []).map((course) => course.title);
  const selectedCourse = courseTitles.includes(params.q) ? params.q : ALL;
  const preference = { date: params.date, time: params.time };
  // The learner's own upcoming bookings, so each card can show the session they booked.
  const myBookings = useQuery({
    queryKey: ["bookings", { scope: "upcoming", page_size: 100 }],
    queryFn: () => api("/bookings", { query: { scope: "upcoming", page_size: 100 } }),
    enabled: user?.role === "USER",
  });
  const bookingByWebinar = new Map();
  for (const booking of myBookings.data?.items ?? []) {
    if (!bookingByWebinar.has(booking.webinar.id)) bookingByWebinar.set(booking.webinar.id, booking);
  }
  const webinars = useQuery({
    queryKey: ["webinars", { departmentId, q: params.q, page, ...preference }],
    queryFn: () =>
      api("/webinars", {
        query: {
          department_id: departmentId,
          q: params.q,
          page,
          page_size: PAGE_SIZE,
          preferred_date: preference.date,
          preferred_time: preference.date ? preference.time : undefined,
        },
      }),
  });

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <PageHeader title="Webinars & courses" subtitle="Live, instructor-led sessions at the date and time you choose. Prices include all taxes." />

      <form
        className="mb-8 grid gap-3 sm:grid-cols-2 sm:items-end lg:grid-cols-4"
        onSubmit={(event) => {
          event.preventDefault();
          setParams({ q: search.trim() });
        }}
      >
        <Input
          label="Search"
          placeholder="Search courses"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="sm:col-span-2"
        />
        <Select
          label="Select course"
          value={selectedCourse}
          onChange={(e) => {
            const q = e.target.value === ALL ? "" : e.target.value;
            setSearch(q);
            setParams({ q });
          }}
        >
          <option value={ALL}>All courses</option>
          {courseTitles.map((title) => (
            <option key={title} value={title}>
              {title}
            </option>
          ))}
        </Select>
        <Select
          label="Your department in college"
          value={params.department_id ?? ALL}
          onChange={(e) => setParams({ department_id: e.target.value })}
        >
          <option value={ALL}>All departments</option>
          {(departments.data ?? []).map((department) => (
            <option key={department.id} value={department.id}>
              {department.name}
            </option>
          ))}
        </Select>
        <PreferredDateInput value={params.date ?? ""} onChange={(e) => setParams({ date: e.target.value })} />
        <PreferredTimeSelect value={params.time ?? ""} onChange={(e) => setParams({ time: e.target.value })} />
        <p className="text-xs text-slate-500 sm:col-span-2 lg:col-span-1">
          Choose your date and time, then press Set webinar on a course — we'll conduct it then.
        </p>
        <Button type="submit">Search</Button>
      </form>

      <QueryState query={webinars}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState
              title="No webinars found"
              description="Try another department or search term."
              action={
                <Button variant="secondary" onClick={() => { setSearch(""); setParams({ q: "", department_id: ALL, date: "", time: "" }); }}>
                  Show all webinars
                </Button>
              }
            />
          ) : (
            <>
              <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {data.items.map((webinar) => (
                  <WebinarCard
                    key={webinar.id}
                    webinar={webinar}
                    preference={preference}
                    myBooking={bookingByWebinar.get(webinar.id)}
                  />
                ))}
              </div>
              <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={(next) => setParams({ page: next })} />
            </>
          )
        }
      </QueryState>
    </div>
  );
}
