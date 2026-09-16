import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { Alert, Button, Card, Checkbox, Input, PageHeader, PageSpinner, Select, Textarea } from "../../components/ui.jsx";
import { api, fieldErrors } from "../../lib/api.js";
import { rupeesToPaise } from "../../lib/format.js";

const EMPTY = { title: "", description: "", instructor: "", price: "", duration_minutes: "60", department_ids: [], status: "ACTIVE" };

export default function AdminWebinarForm() {
  const { webinarId } = useParams();
  const editing = Boolean(webinarId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY);

  const departments = useQuery({ queryKey: ["admin", "departments"], queryFn: () => api("/admin/departments") });
  const existing = useQuery({
    queryKey: ["admin", "webinar", webinarId],
    queryFn: () => api(`/admin/webinars/${webinarId}`),
    enabled: editing,
  });

  useEffect(() => {
    if (existing.data) {
      const w = existing.data;
      setForm({
        title: w.title,
        description: w.description,
        instructor: w.instructor ?? "",
        price: String(w.price_paise / 100),
        duration_minutes: String(w.duration_minutes),
        department_ids: w.departments.map((d) => d.id),
        status: w.status,
      });
    }
  }, [existing.data]);

  const save = useMutation({
    mutationFn: () => {
      const body = {
        title: form.title,
        description: form.description,
        instructor: form.instructor.trim() || null,
        price_paise: rupeesToPaise(form.price || 0),
        duration_minutes: Number(form.duration_minutes),
        department_ids: form.department_ids,
        status: form.status,
      };
      return editing
        ? api(`/admin/webinars/${webinarId}`, { method: "PUT", body })
        : api("/admin/webinars", { method: "POST", body });
    },
    onSuccess: (webinar) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "webinars"] });
      queryClient.invalidateQueries({ queryKey: ["webinars"] });
      navigate(editing ? "/admin/webinars" : `/admin/webinars/${webinar.id}/slots`);
    },
  });

  if (editing && existing.isPending) return <PageSpinner />;
  const errors = fieldErrors(save.error);
  const set = (field) => (event) => setForm({ ...form, [field]: event.target.value });
  const toggleDepartment = (id) =>
    setForm({
      ...form,
      department_ids: form.department_ids.includes(id) ? form.department_ids.filter((d) => d !== id) : [...form.department_ids, id],
    });

  return (
    <>
      <Link to="/admin/webinars" className="text-sm font-medium text-brand-700 hover:underline">
        ← Webinars
      </Link>
      <PageHeader title={editing ? "Edit webinar" : "New webinar"} subtitle={editing ? existing.data?.title : "After saving you can add dates and times."} />
      <Card className="max-w-3xl">
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <Input label="Title" required value={form.title} onChange={set("title")} error={errors.title} />
          <Textarea label="Description" required rows={5} value={form.description} onChange={set("description")} error={errors.description} hint="At least 10 characters. The first 160 are shown on catalog cards." />
          <Input label="Instructor (optional)" value={form.instructor} onChange={set("instructor")} error={errors.instructor} />
          <div className="grid gap-4 sm:grid-cols-3">
            <Input label="Price (₹)" type="number" min="0" step="0.01" required value={form.price} onChange={set("price")} error={errors.price_paise} hint="0 for a free webinar" />
            <Input label="Duration (minutes)" type="number" min="1" max="1440" required value={form.duration_minutes} onChange={set("duration_minutes")} error={errors.duration_minutes} />
            <Select label="Status" value={form.status} onChange={set("status")}>
              <option value="ACTIVE">Active</option>
              <option value="INACTIVE">Inactive</option>
            </Select>
          </div>
          <fieldset>
            <legend className="text-sm font-medium text-slate-700">Departments</legend>
            <div className="mt-2 flex flex-wrap gap-x-6 gap-y-2">
              {(departments.data ?? [])
                .filter((d) => d.status === "ACTIVE" || form.department_ids.includes(d.id))
                .map((department) => (
                  <Checkbox
                    key={department.id}
                    label={department.name}
                    checked={form.department_ids.includes(department.id)}
                    onChange={() => toggleDepartment(department.id)}
                  />
                ))}
            </div>
            {errors.department_ids && <p className="mt-1 text-sm text-rose-600">Choose at least one department.</p>}
          </fieldset>
          {save.isError && Object.keys(errors).length === 0 && <Alert kind="error">{save.error.message}</Alert>}
          <div className="flex gap-3">
            <Button type="submit" loading={save.isPending} disabled={form.department_ids.length === 0}>
              {editing ? "Save changes" : "Create webinar"}
            </Button>
            <Button variant="ghost" to="/admin/webinars">
              Cancel
            </Button>
          </div>
        </form>
      </Card>
    </>
  );
}
