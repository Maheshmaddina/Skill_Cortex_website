import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { Alert, Badge, Button, Card, Checkbox, EmptyState, Input, PageHeader, QueryState, StatusBadge, Table, Td } from "../../components/ui.jsx";
import { api } from "../../lib/api.js";
import { formatDate, formatINR, formatTimeRange, fromISTInput, toISTInput } from "../../lib/format.js";

function addMinutes(localValue, minutes) {
  const date = new Date(fromISTInput(localValue));
  return toISTInput(new Date(date.getTime() + minutes * 60_000).toISOString());
}

export default function AdminSlots() {
  const { webinarId } = useParams();
  const queryClient = useQueryClient();
  const [upcomingOnly, setUpcomingOnly] = useState(true);
  const [form, setForm] = useState({ start: "", end: "", capacity: "30" });

  const webinar = useQuery({ queryKey: ["admin", "webinar", webinarId], queryFn: () => api(`/admin/webinars/${webinarId}`) });
  const slots = useQuery({
    queryKey: ["admin", "slots", webinarId, upcomingOnly],
    queryFn: () => api("/admin/slots", { query: { webinar_id: webinarId, upcoming: upcomingOnly, page_size: 100 } }),
  });
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin", "slots", webinarId] });
    queryClient.invalidateQueries({ queryKey: ["webinar", webinarId] });
  };
  const create = useMutation({
    mutationFn: () =>
      api("/admin/slots", {
        method: "POST",
        body: { webinar_id: webinarId, start_at: fromISTInput(form.start), end_at: fromISTInput(form.end), capacity: Number(form.capacity) },
      }),
    onSuccess: () => {
      setForm({ start: "", end: "", capacity: form.capacity });
      invalidate();
    },
  });

  return (
    <>
      <Link to="/admin/webinars" className="text-sm font-medium text-brand-700 hover:underline">
        ← Webinars
      </Link>
      <PageHeader
        title={webinar.data ? `Slots · ${webinar.data.title}` : "Slots"}
        subtitle={webinar.data && `${formatINR(webinar.data.price_paise)} · ${webinar.data.duration_minutes} min · all times IST`}
      />

      <Card className="mb-6">
        <h2 className="font-semibold">Add a slot</h2>
        <form
          className="mt-3 grid gap-3 md:grid-cols-[1fr_1fr_9rem_auto] md:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <Input
            label="Starts (IST)"
            type="datetime-local"
            required
            value={form.start}
            onChange={(e) => {
              const start = e.target.value;
              setForm({ ...form, start, end: start && webinar.data ? addMinutes(start, webinar.data.duration_minutes) : form.end });
            }}
          />
          <Input label="Ends (IST)" type="datetime-local" required value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} />
          <Input label="Capacity" type="number" min="1" max="10000" required value={form.capacity} onChange={(e) => setForm({ ...form, capacity: e.target.value })} />
          <Button type="submit" loading={create.isPending}>
            Add slot
          </Button>
        </form>
        {create.isError && (
          <Alert kind="error" className="mt-3">
            {create.error.message}
          </Alert>
        )}
      </Card>

      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Slots</h2>
        <Checkbox label="Upcoming only" checked={upcomingOnly} onChange={(e) => setUpcomingOnly(e.target.checked)} />
      </div>
      <QueryState query={slots}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState title="No slots" description="Add a date and time above so learners can book." />
          ) : (
            <Table headers={["Date & time", "Capacity", "Booked", "Available", "Status", ""]}>
              {data.items.map((slot) => (
                <SlotRow key={slot.id} slot={slot} onChanged={invalidate} />
              ))}
            </Table>
          )
        }
      </QueryState>
    </>
  );
}

function SlotRow({ slot, onChanged }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ start: toISTInput(slot.start_at), end: toISTInput(slot.end_at), capacity: String(slot.capacity) });
  const [message, setMessage] = useState(null);

  const update = useMutation({
    mutationFn: (body) => api(`/admin/slots/${slot.id}`, { method: "PUT", body }),
    onSuccess: () => {
      setEditing(false);
      onChanged();
    },
  });
  const cancelSession = useMutation({
    mutationFn: () => api(`/admin/slots/${slot.id}/cancel`, { method: "POST" }),
    onSuccess: (result) => {
      setMessage(`Session cancelled: ${result.cancelled_bookings} booking(s) cancelled, ${result.refunds_issued} refund(s) issued.`);
      onChanged();
    },
  });

  function saveDraft() {
    const body = { capacity: Number(draft.capacity) };
    if (draft.start !== toISTInput(slot.start_at)) body.start_at = fromISTInput(draft.start);
    if (draft.end !== toISTInput(slot.end_at)) body.end_at = fromISTInput(draft.end);
    update.mutate(body);
  }

  const error = update.error ?? cancelSession.error;
  const isCancelled = slot.status === "CANCELLED";

  return (
    <tr>
      <Td className="min-w-64">
        {editing ? (
          <div className="grid gap-2">
            <Input aria-label="Starts" type="datetime-local" value={draft.start} onChange={(e) => setDraft({ ...draft, start: e.target.value })} />
            <Input aria-label="Ends" type="datetime-local" value={draft.end} onChange={(e) => setDraft({ ...draft, end: e.target.value })} />
          </div>
        ) : (
          <>
            <p className="font-medium text-slate-900">{formatDate(slot.start_at)}</p>
            <p className="text-xs text-slate-500">{formatTimeRange(slot.start_at, slot.end_at)}</p>
            {slot.set_by && (
              <p className="mt-1 text-xs text-slate-600">
                <Badge>Set by learner</Badge> {slot.set_by.name}
              </p>
            )}
          </>
        )}
        {error && <p className="mt-1 text-sm text-rose-600">{error.message}</p>}
        {message && <p className="mt-1 text-sm text-emerald-700">{message}</p>}
      </Td>
      <Td>
        {editing ? (
          <Input aria-label="Capacity" type="number" min="1" className="w-24" value={draft.capacity} onChange={(e) => setDraft({ ...draft, capacity: e.target.value })} />
        ) : (
          slot.capacity
        )}
      </Td>
      <Td>{slot.booked_seats}</Td>
      <Td>{slot.available_seats}</Td>
      <Td>
        <StatusBadge status={slot.status} />
      </Td>
      <Td className="whitespace-nowrap">
        <div className="flex justify-end gap-2">
          {editing ? (
            <>
              <Button size="sm" loading={update.isPending} onClick={saveDraft}>
                Save
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            </>
          ) : (
            !isCancelled && (
              <>
                <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
                  Edit
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  loading={update.isPending}
                  onClick={() => update.mutate({ status: slot.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" })}
                >
                  {slot.status === "ACTIVE" ? "Deactivate" : "Activate"}
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  loading={cancelSession.isPending}
                  onClick={() =>
                    window.confirm("Cancel this session? Every booking will be cancelled, paid bookings refunded in full, and learners notified.") &&
                    cancelSession.mutate()
                  }
                >
                  Cancel session
                </Button>
              </>
            )
          )}
        </div>
      </Td>
    </tr>
  );
}
