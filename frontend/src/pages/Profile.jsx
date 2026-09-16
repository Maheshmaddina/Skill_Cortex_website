import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useAuth } from "../auth/AuthContext.jsx";
import { Alert, Button, Card, Input, PageHeader, Select } from "../components/ui.jsx";
import { api, fieldErrors } from "../lib/api.js";

export default function Profile() {
  const { user, setUser } = useAuth();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ name: user.name, phone: user.phone, department_id: user.department?.id ?? "" });
  const departments = useQuery({ queryKey: ["departments"], queryFn: () => api("/departments") });

  const save = useMutation({
    mutationFn: () =>
      api("/users/me", {
        method: "PUT",
        body: { name: form.name, phone: form.phone, ...(form.department_id ? { department_id: form.department_id } : {}) },
      }),
    onSuccess: (updated) => {
      setUser(updated);
      queryClient.invalidateQueries({ queryKey: ["webinars"] });
    },
  });
  const errors = fieldErrors(save.error);

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <PageHeader title="Profile" subtitle="Your details are used for booking confirmations and reminders." />
      <Card>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <Input label="Email" value={user.email} disabled hint="Contact support to change your email address." />
          <Input label="Full name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} error={errors.name} />
          <Input label="Mobile number" type="tel" required value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} error={errors.phone} />
          {user.role === "USER" && (
            <Select
              label="Department"
              value={form.department_id}
              onChange={(e) => setForm({ ...form, department_id: e.target.value })}
              hint="Webinars for your department are shown first."
            >
              {(departments.data ?? []).map((department) => (
                <option key={department.id} value={department.id}>
                  {department.name}
                </option>
              ))}
            </Select>
          )}
          {save.isSuccess && <Alert kind="success">Profile updated.</Alert>}
          {save.isError && Object.keys(errors).length === 0 && <Alert kind="error">{save.error.message}</Alert>}
          <Button type="submit" loading={save.isPending}>
            Save changes
          </Button>
        </form>
      </Card>
    </div>
  );
}
