import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Button, Card, Input, PageHeader, QueryState, StatusBadge, Table, Td } from "../../components/ui.jsx";
import { api } from "../../lib/api.js";

function useInvalidateDepartments() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["admin", "departments"] });
    queryClient.invalidateQueries({ queryKey: ["departments"] });
  };
}

export default function AdminDepartments() {
  const invalidate = useInvalidateDepartments();
  const [form, setForm] = useState({ name: "", description: "" });
  const departments = useQuery({ queryKey: ["admin", "departments"], queryFn: () => api("/admin/departments") });
  const create = useMutation({
    mutationFn: () => api("/admin/departments", { method: "POST", body: { name: form.name, description: form.description || null } }),
    onSuccess: () => {
      setForm({ name: "", description: "" });
      invalidate();
    },
  });

  return (
    <>
      <PageHeader title="Departments" subtitle="Learners pick one when they register; webinars can belong to several." />
      <Card className="mb-6">
        <form
          className="grid gap-3 md:grid-cols-[1fr_2fr_auto] md:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <Input label="Name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Input label="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <Button type="submit" loading={create.isPending}>
            Add department
          </Button>
        </form>
        {create.isError && (
          <Alert kind="error" className="mt-3">
            {create.error.message}
          </Alert>
        )}
      </Card>
      <QueryState query={departments}>
        {(rows) => (
          <Table headers={["Name", "Description", "Status", ""]}>
            {rows.map((department) => (
              <DepartmentRow key={department.id} department={department} onChanged={invalidate} />
            ))}
          </Table>
        )}
      </QueryState>
    </>
  );
}

function DepartmentRow({ department, onChanged }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ name: department.name, description: department.description ?? "" });
  const update = useMutation({
    mutationFn: (body) => api(`/admin/departments/${department.id}`, { method: "PUT", body }),
    onSuccess: () => {
      setEditing(false);
      onChanged();
    },
  });
  const active = department.status === "ACTIVE";

  return (
    <tr>
      {editing ? (
        <>
          <Td>
            <Input aria-label="Name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          </Td>
          <Td>
            <Input aria-label="Description" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
            {update.isError && <p className="mt-1 text-sm text-rose-600">{update.error.message}</p>}
          </Td>
        </>
      ) : (
        <>
          <Td className="font-medium text-slate-900">{department.name}</Td>
          <Td>{department.description}</Td>
        </>
      )}
      <Td>
        <StatusBadge status={department.status} />
      </Td>
      <Td className="whitespace-nowrap text-right">
        {editing ? (
          <div className="flex justify-end gap-2">
            <Button size="sm" loading={update.isPending} onClick={() => update.mutate({ name: draft.name, description: draft.description || null })}>
              Save
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
              Edit
            </Button>
            <Button size="sm" variant={active ? "ghost" : "secondary"} loading={update.isPending} onClick={() => update.mutate({ status: active ? "INACTIVE" : "ACTIVE" })}>
              {active ? "Deactivate" : "Activate"}
            </Button>
          </div>
        )}
      </Td>
    </tr>
  );
}
