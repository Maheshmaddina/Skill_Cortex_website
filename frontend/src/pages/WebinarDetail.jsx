import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { useAuth } from "../auth/AuthContext.jsx";
import { SetWebinarPanel } from "../components/SetWebinar.jsx";
import { Alert, Badge, Button, Card, QueryState } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { formatDate, formatDuration, formatINR, formatTimeRange } from "../lib/format.js";

/** Slots (already sorted by start) → [{ label: "Sat, 19 Sep 2026", slots, full }] in IST days. */
function groupSlotsByDay(slots) {
  const days = [];
  for (const slot of slots) {
    const label = formatDate(slot.start_at);
    if (days.at(-1)?.label !== label) days.push({ label, slots: [] });
    days.at(-1).slots.push(slot);
  }
  return days.map((day) => ({ ...day, full: day.slots.every((slot) => slot.is_full) }));
}

export default function WebinarDetail() {
  const { webinarId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  // ?slot= preselects a session (from a matching catalog card or a "your request is scheduled" link).
  const [selectedSlotId, setSelectedSlotId] = useState(searchParams.get("slot"));
  const [selectedDay, setSelectedDay] = useState(null);

  const webinar = useQuery({ queryKey: ["webinar", webinarId], queryFn: () => api(`/webinars/${webinarId}`) });

  const book = useMutation({
    mutationFn: (slotId) => api("/bookings", { method: "POST", body: { slot_id: slotId } }),
    onSuccess: (booking) => {
      queryClient.invalidateQueries({ queryKey: ["bookings"] });
      navigate(`/bookings/${booking.id}`);
    },
    onError: () => queryClient.invalidateQueries({ queryKey: ["webinar", webinarId] }),
  });

  function handleBook() {
    if (!user) {
      navigate(`/login?next=${encodeURIComponent(`/webinars/${webinarId}`)}`);
      return;
    }
    book.mutate(selectedSlotId);
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <Link to="/webinars" className="text-sm font-medium text-brand-700 hover:underline">
        ← All webinars
      </Link>
      <QueryState query={webinar}>
        {(data) => {
          const selected = data.slots.find((slot) => slot.id === selectedSlotId);
          const slotDays = groupSlotsByDay(data.slots);
          const activeDay =
            slotDays.find((day) => day.label === (selectedDay ?? (selected && formatDate(selected.start_at)))) ??
            slotDays.find((day) => !day.full) ??
            slotDays[0];
          return (
            <div className="mt-4 grid gap-8 lg:grid-cols-[1fr_24rem]">
              <div>
                <div className="flex flex-wrap gap-1.5">
                  {data.departments.map((department) => (
                    <Badge key={department.id}>{department.name}</Badge>
                  ))}
                </div>
                <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-900">{data.title}</h1>
                <dl className="mt-4 flex flex-wrap gap-x-8 gap-y-2 text-sm text-slate-600">
                  {data.instructor && (
                    <div>
                      <dt className="inline text-slate-400">Instructor: </dt>
                      <dd className="inline font-medium text-slate-900">{data.instructor}</dd>
                    </div>
                  )}
                  <div>
                    <dt className="inline text-slate-400">Duration: </dt>
                    <dd className="inline font-medium text-slate-900">{formatDuration(data.duration_minutes)}</dd>
                  </div>
                  <div>
                    <dt className="inline text-slate-400">Price: </dt>
                    <dd className="inline font-medium text-slate-900">{formatINR(data.price_paise)}</dd>
                  </div>
                </dl>
                <p className="mt-6 whitespace-pre-line leading-7 text-slate-700">{data.description}</p>
              </div>

              <div className="grid h-fit gap-6">
              <Card>
                <SetWebinarPanel
                  webinar={data}
                  defaultDate={searchParams.get("date") ?? ""}
                  defaultTime={searchParams.get("time") ?? ""}
                />
              </Card>
              <Card>
                <h2 className="text-lg font-semibold">Or join a scheduled session</h2>
                {data.slots.length === 0 ? (
                  <p className="mt-3 text-sm text-slate-500">No sessions scheduled yet — set your own date and time above.</p>
                ) : (
                  <>
                    <p className="mt-4 text-sm font-medium text-slate-700">1. Pick a date</p>
                    <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="Session dates">
                      {slotDays.map((day) => (
                        <button
                          key={day.label}
                          type="button"
                          aria-pressed={day.label === activeDay?.label}
                          disabled={day.full}
                          onClick={() => {
                            setSelectedDay(day.label);
                            setSelectedSlotId(null);
                          }}
                          className={`rounded-lg px-3 py-2 text-left text-xs font-medium ring-1 transition ${
                            day.label === activeDay?.label
                              ? "bg-brand-500 text-white ring-brand-500"
                              : day.full
                                ? "cursor-not-allowed bg-slate-50 text-slate-400 ring-slate-200"
                                : "bg-white text-slate-700 ring-slate-300 hover:ring-brand-400"
                          }`}
                        >
                          {day.label.replace(/ \d{4}$/, "")}
                          <span className="block font-normal opacity-80">{day.full ? "Full" : `${day.slots.length} ${day.slots.length === 1 ? "time" : "times"}`}</span>
                        </button>
                      ))}
                    </div>

                    <p className="mt-5 text-sm font-medium text-slate-700">2. Pick a time</p>
                    <fieldset className="mt-2 space-y-2">
                      <legend className="sr-only">Available times on {activeDay?.label}</legend>
                      {(activeDay?.slots ?? []).map((slot) => (
                        <label
                          key={slot.id}
                          className={`flex cursor-pointer items-center justify-between gap-3 rounded-xl p-3 ring-1 ${
                            slot.is_full
                              ? "cursor-not-allowed bg-slate-50 text-slate-400 ring-slate-200"
                              : selectedSlotId === slot.id
                                ? "bg-brand-50 ring-2 ring-brand-600"
                                : "ring-slate-200 hover:ring-brand-300"
                          }`}
                        >
                          <span className="flex items-center gap-3">
                            <input
                              type="radio"
                              name="slot"
                              className="size-4 accent-brand-600"
                              disabled={slot.is_full}
                              checked={selectedSlotId === slot.id}
                              onChange={() => setSelectedSlotId(slot.id)}
                            />
                            <span className="text-sm font-medium">{formatTimeRange(slot.start_at, slot.end_at)}</span>
                          </span>
                          <span className={`text-xs font-medium ${slot.is_full ? "" : "text-emerald-700"}`}>
                            {slot.is_full ? "Full" : `${slot.available_seats} seats`}
                          </span>
                        </label>
                      ))}
                    </fieldset>
                    {selected && (
                      <p className="mt-3 text-sm text-slate-600">
                        Your webinar: <span className="font-semibold text-slate-900">{formatDate(selected.start_at)}</span>,{" "}
                        {formatTimeRange(selected.start_at, selected.end_at)}
                      </p>
                    )}
                  </>
                )}

                {book.isError && (
                  <Alert kind="error" className="mt-4">
                    {book.error.message}
                  </Alert>
                )}
                {user?.role === "ADMIN" ? (
                  <Alert kind="info" className="mt-4">
                    You're signed in as an admin. Bookings are made from learner accounts.
                  </Alert>
                ) : (
                  <Button className="mt-5 w-full" size="lg" variant="secondary" disabled={!selected} loading={book.isPending} onClick={handleBook}>
                    {selected ? `Book this session · ${formatINR(data.price_paise)}` : "Select a session"}
                  </Button>
                )}
                {!user && <p className="mt-2 text-center text-xs text-slate-500">You'll be asked to log in first.</p>}
              </Card>
              </div>
            </div>
          );
        }}
      </QueryState>
    </div>
  );
}
