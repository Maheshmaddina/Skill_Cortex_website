import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Button, Card, Checkbox, Input, PageHeader, QueryState, Table, Td } from "../../components/ui.jsx";
import { api } from "../../lib/api.js";

function describe(offset) {
  if (offset === 0) return "On the day";
  if (offset === 1) return "1 day before";
  return `${offset} days before`;
}

export default function AdminReminderRules() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ offset_days: "7", send_time_local: "09:00", send_email: true, send_sms: true });
  const rules = useQuery({ queryKey: ["admin", "reminder-rules"], queryFn: () => api("/admin/reminder-rules") });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin", "reminder-rules"] });

  const create = useMutation({
    mutationFn: () => api("/admin/reminder-rules", { method: "POST", body: { ...form, offset_days: Number(form.offset_days) } }),
    onSuccess: invalidate,
  });
  const update = useMutation({
    mutationFn: ({ id, ...body }) => api(`/admin/reminder-rules/${id}`, { method: "PUT", body }),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: (id) => api(`/admin/reminder-rules/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
  const error = create.error ?? update.error ?? remove.error;

  return (
    <>
      <PageHeader
        title="Reminder schedule"
        subtitle="Confirmed learners get these reminders before their session. Times are IST; same-day reminders go out at the set time or 2 hours before the start, whichever is earlier."
      />
      <Card className="mb-6">
        <h2 className="font-semibold">Add a reminder</h2>
        <form
          className="mt-3 flex flex-wrap items-end gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <Input label="Days before" type="number" min="0" max="30" required className="w-32" value={form.offset_days} onChange={(e) => setForm({ ...form, offset_days: e.target.value })} />
          <Input label="Send at (IST)" type="time" required className="w-36" value={form.send_time_local} onChange={(e) => setForm({ ...form, send_time_local: e.target.value })} />
          <Checkbox label="Email" checked={form.send_email} onChange={(e) => setForm({ ...form, send_email: e.target.checked })} className="pb-2" />
          <Checkbox label="SMS" checked={form.send_sms} onChange={(e) => setForm({ ...form, send_sms: e.target.checked })} className="pb-2" />
          <Button type="submit" loading={create.isPending}>
            Add reminder
          </Button>
        </form>
      </Card>
      {error && (
        <Alert kind="error" className="mb-4">
          {error.message}
        </Alert>
      )}
      <QueryState query={rules}>
        {(rows) => (
          <Table headers={["When", "Send at (IST)", "Email", "SMS", "Active", ""]}>
            {rows.map((rule) => (
              <tr key={rule.id}>
                <Td className="font-medium text-slate-900">{describe(rule.offset_days)}</Td>
                <Td>
                  <input
                    type="time"
                    aria-label={`Send time for ${describe(rule.offset_days)}`}
                    className="rounded-lg border-0 px-2 py-1 text-sm ring-1 ring-slate-300 focus:ring-2 focus:ring-brand-600"
                    defaultValue={rule.send_time_local.slice(0, 5)}
                    onBlur={(e) => e.target.value && e.target.value !== rule.send_time_local.slice(0, 5) && update.mutate({ id: rule.id, send_time_local: e.target.value })}
                  />
                </Td>
                <Td>
                  <input type="checkbox" aria-label="Email" className="size-4" checked={rule.send_email} onChange={(e) => update.mutate({ id: rule.id, send_email: e.target.checked })} />
                </Td>
                <Td>
                  <input type="checkbox" aria-label="SMS" className="size-4" checked={rule.send_sms} onChange={(e) => update.mutate({ id: rule.id, send_sms: e.target.checked })} />
                </Td>
                <Td>
                  <input type="checkbox" aria-label="Active" className="size-4" checked={rule.active} onChange={(e) => update.mutate({ id: rule.id, active: e.target.checked })} />
                </Td>
                <Td className="text-right">
                  <Button size="sm" variant="ghost" onClick={() => window.confirm(`Delete the "${describe(rule.offset_days)}" reminder?`) && remove.mutate(rule.id)}>
                    Delete
                  </Button>
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </QueryState>
    </>
  );
}
