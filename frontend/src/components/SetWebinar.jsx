import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router";

import { useAuth } from "../auth/AuthContext.jsx";
import { api } from "../lib/api.js";
import { PREFERRED_TIMES, formatClock, formatINR, formatLocalDate, istDate } from "../lib/format.js";
import { Alert, Button, Input, Select, Textarea } from "./ui.jsx";

const MAX_DAYS_AHEAD = 90;

/**
 * Learner-set webinars: the learner picks any date and start time and presses "Set webinar".
 * The session is created then (or they join one already at that time) and they go straight to payment.
 */

export function PreferredDateInput(props) {
  return <Input label="Preferred date" type="date" min={istDate(1)} max={istDate(MAX_DAYS_AHEAD)} {...props} />;
}

export function PreferredTimeSelect({ emptyLabel = "Any time", ...props }) {
  return (
    <Select label="Preferred time (IST)" {...props}>
      <option value="">{emptyLabel}</option>
      {PREFERRED_TIMES.map((time) => (
        <option key={time} value={time}>
          {formatClock(time)}
        </option>
      ))}
    </Select>
  );
}

/** Returns the mutation plus `set(body)`, which sends guests to log in first (and back here after). */
function useSetWebinar(webinarId) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (body) => api("/bookings/set-webinar", { method: "POST", body: { webinar_id: webinarId, ...body } }),
    onSuccess: (booking) => {
      queryClient.invalidateQueries({ queryKey: ["bookings"] });
      queryClient.invalidateQueries({ queryKey: ["webinars"] });
      navigate(`/bookings/${booking.id}`); // review & pay
    },
  });
  return {
    user,
    mutation,
    set(body) {
      if (!user) {
        navigate(`/login?next=${encodeURIComponent(location.pathname + location.search)}`);
        return;
      }
      mutation.mutate(body);
    },
  };
}

/** Catalog card button for the date & time picked in the filters. */
export function SetWebinarButton({ webinar, date, time }) {
  const { user, mutation, set } = useSetWebinar(webinar.id);
  if (user?.role === "ADMIN") return null;
  return (
    <>
      <Button
        size="sm"
        className="w-full"
        loading={mutation.isPending}
        onClick={() => set({ preferred_date: date, preferred_time: time })}
      >
        Set webinar
      </Button>
      {mutation.isError && <p className="mt-1 text-xs text-rose-700">{mutation.error.message}</p>}
    </>
  );
}

/** Course page: choose any date and time and set the webinar for it. */
export function SetWebinarPanel({ webinar, defaultDate = "", defaultTime = "" }) {
  const [form, setForm] = useState({ preferred_date: defaultDate, preferred_time: defaultTime, note: "" });
  const { user, mutation, set } = useSetWebinar(webinar.id);

  if (user?.role === "ADMIN") {
    return (
      <Alert kind="info">Learners set webinars for their own date and time here. Admin accounts can't book.</Alert>
    );
  }

  const ready = form.preferred_date && form.preferred_time;
  return (
    <div>
      <h2 className="text-lg font-semibold">Set your webinar</h2>
      <p className="mt-1 text-sm text-slate-600">
        Choose the date and time that suit you — we'll conduct the webinar then. Pay to confirm your seat.
      </p>
      <form
        className="mt-4 grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          set({ ...form, note: form.note || null });
        }}
      >
        <PreferredDateInput
          required
          value={form.preferred_date}
          onChange={(e) => setForm({ ...form, preferred_date: e.target.value })}
        />
        <PreferredTimeSelect
          required
          emptyLabel="Choose a time"
          value={form.preferred_time}
          onChange={(e) => setForm({ ...form, preferred_time: e.target.value })}
        />
        <Textarea
          label="Note for the mentor (optional)"
          rows={2}
          maxLength={500}
          placeholder="e.g. Topics you'd like covered"
          value={form.note}
          onChange={(e) => setForm({ ...form, note: e.target.value })}
        />
        {ready && (
          <p className="text-sm text-slate-600">
            Your webinar:{" "}
            <span className="font-semibold text-slate-900">
              {formatLocalDate(form.preferred_date)}, {formatClock(form.preferred_time)} IST
            </span>
          </p>
        )}
        {mutation.isError && <Alert kind="error">{mutation.error.message}</Alert>}
        <Button type="submit" size="lg" className="w-full" loading={mutation.isPending}>
          Set webinar · {formatINR(webinar.price_paise)}
        </Button>
        {!user && <p className="text-center text-xs text-slate-500">You'll be asked to log in first.</p>}
      </form>
    </div>
  );
}
