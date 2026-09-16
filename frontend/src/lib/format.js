/** Display helpers. All times are shown in IST, matching emails and SMS. */

export const TIME_ZONE = "Asia/Kolkata";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const displayParts = new Intl.DateTimeFormat("en-US", {
  timeZone: TIME_ZONE,
  weekday: "short",
  year: "numeric",
  month: "numeric",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

const inputParts = new Intl.DateTimeFormat("en-US", {
  timeZone: TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

function partsOf(formatter, value) {
  return Object.fromEntries(formatter.formatToParts(new Date(value)).map((part) => [part.type, part.value]));
}

export function formatINR(paise) {
  if (paise === 0) return "Free";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: paise % 100 ? 2 : 0,
    maximumFractionDigits: 2,
  }).format(paise / 100);
}

/** "Sun, 20 Sep 2026" */
export function formatDate(value) {
  const p = partsOf(displayParts, value);
  return `${p.weekday}, ${p.day} ${MONTHS[Number(p.month) - 1]} ${p.year}`;
}

/** "10:00 AM" */
export function formatTime(value) {
  const p = partsOf(displayParts, value);
  return `${p.hour}:${p.minute} ${p.dayPeriod.toUpperCase()}`;
}

export function formatDateTime(value) {
  return `${formatDate(value)}, ${formatTime(value)} IST`;
}

export function formatTimeRange(start, end) {
  return `${formatTime(start)} – ${formatTime(end)} IST`;
}

export function formatDuration(minutes) {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return [hours && `${hours} hr`, rest && `${rest} min`].filter(Boolean).join(" ") || "0 min";
}

/** ISO timestamp → value for <input type="datetime-local">, in IST. */
export function toISTInput(value) {
  if (!value) return "";
  const p = partsOf(inputParts, value);
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}

/** <input type="datetime-local"> value (entered as IST) → ISO timestamp with offset. */
export function fromISTInput(value) {
  return value ? `${value}:00+05:30` : null;
}

export function rupeesToPaise(value) {
  return Math.round(Number(value) * 100);
}

export function humanize(value) {
  if (!value) return "";
  const text = value.toLowerCase().replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Milliseconds → "m:ss" */
export function formatCountdown(ms) {
  const seconds = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/** Milliseconds → { days, hours, minutes, seconds }, never negative. */
export function countdownParts(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  return {
    days: Math.floor(total / 86_400),
    hours: Math.floor((total % 86_400) / 3_600),
    minutes: Math.floor((total % 3_600) / 60),
    seconds: total % 60,
  };
}

/** Milliseconds until a session → "Starts in 2d 4h" / "Starts in 3h 12m" / "Starts in 5m". */
export function formatStartsIn(ms) {
  const { days, hours, minutes } = countdownParts(ms);
  if (days) return `Starts in ${days}d ${hours}h`;
  if (hours) return `Starts in ${hours}h ${minutes}m`;
  return minutes ? `Starts in ${minutes}m` : "Starting now";
}

// --- learner-chosen dates & times (all IST) ---------------------------------

/** Start times a learner can ask for: every half hour from 7:00 AM to 9:00 PM IST ("HH:MM"). */
export const PREFERRED_TIMES = Array.from({ length: 29 }, (_, i) => {
  const minutes = 7 * 60 + i * 30;
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
});

/** "18:30" or "18:30:00" → "6:30 PM" */
export function formatClock(value) {
  const [hours, minutes] = value.split(":").map(Number);
  return `${hours % 12 || 12}:${String(minutes).padStart(2, "0")} ${hours < 12 ? "AM" : "PM"}`;
}

/** "2026-09-20" (an IST calendar date) → "Sun, 20 Sep 2026" */
export function formatLocalDate(value) {
  return formatDate(`${value}T12:00:00+05:30`);
}

/** Today's IST date plus `days`, as "YYYY-MM-DD". */
export function istDate(days = 0, now = Date.now()) {
  return toISTInput(now + days * 86_400_000).slice(0, 10);
}
