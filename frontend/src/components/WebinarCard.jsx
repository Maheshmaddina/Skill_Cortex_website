import { formatClock, formatDate, formatDuration, formatINR, formatLocalDate, formatTime } from "../lib/format.js";
import { SetWebinarButton } from "./SetWebinar.jsx";
import { Button, Card } from "./ui.jsx";

function detailLink(webinar, preference) {
  const params = new URLSearchParams();
  if (webinar.matching_slot) params.set("slot", webinar.matching_slot.id);
  else if (preference.date) {
    params.set("date", preference.date);
    if (preference.time) params.set("time", preference.time);
  }
  const query = params.toString();
  return `/webinars/${webinar.id}${query ? `?${query}` : ""}`;
}

export default function WebinarCard({ webinar, preference = {} }) {
  const next = webinar.next_slot;
  return (
    <Card className="flex flex-col">
      <h3 className="text-lg font-semibold text-slate-900">{webinar.title}</h3>
      <p className="mt-2 flex-1 text-sm text-slate-600">{webinar.short_description}</p>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-slate-500">Price</dt>
          <dd className="font-semibold text-slate-900">{formatINR(webinar.price_paise)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Duration</dt>
          <dd className="font-medium text-slate-900">{formatDuration(webinar.duration_minutes)}</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-slate-500">Next slot</dt>
          <dd className="font-medium text-slate-900">
            {next ? `${formatDate(next.start_at)} · ${formatTime(next.start_at)} IST` : "No open slots right now"}
          </dd>
          {next && <dd className="text-xs text-emerald-700">{next.available_seats} seats left in this session</dd>}
        </div>
      </dl>
      {preference.date && <PreferenceMatch webinar={webinar} preference={preference} />}
      <Button
        to={detailLink(webinar, preference)}
        variant="secondary"
        className="mt-5"
      >
        View Details
      </Button>
    </Card>
  );
}

/** The learner's chosen date & time from the filters: set the webinar for it right from the card. */
function PreferenceMatch({ webinar, preference }) {
  const slot = webinar.matching_slot;
  if (!preference.time) {
    return (
      <p className="mt-4 rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-600 ring-1 ring-slate-200">
        {slot
          ? `A session already runs on ${formatDate(slot.start_at)} at ${formatTime(slot.start_at)} IST.`
          : `Pick a preferred time to set your webinar on ${formatLocalDate(preference.date)}.`}
      </p>
    );
  }
  return (
    <div className="mt-4 rounded-xl bg-brand-50 px-3 py-3 text-sm text-slate-800 ring-1 ring-brand-200">
      <p>
        Your webinar: <span className="font-semibold">{formatLocalDate(preference.date)}, {formatClock(preference.time)} IST</span>
      </p>
      {slot && <p className="mt-0.5 text-xs text-emerald-700">Other learners chose this time too — you'll join them.</p>}
      <div className="mt-2">
        <SetWebinarButton webinar={webinar} date={preference.date} time={preference.time} />
      </div>
    </div>
  );
}
