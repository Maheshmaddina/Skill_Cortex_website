import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router";

import { useAuth } from "../auth/AuthContext.jsx";
import { homeFor } from "../auth/RequireAuth.jsx";
import AuthCard from "../components/AuthCard.jsx";
import { Alert, Button, Input, Select } from "../components/ui.jsx";
import { api, fieldErrors } from "../lib/api.js";

const EMPTY = { name: "", email: "", phone: "", password: "", department_id: "" };

export default function Register() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const departments = useQuery({ queryKey: ["departments"], queryFn: () => api("/departments") });

  if (user) return <Navigate to={homeFor(user)} replace />;

  const set = (field) => (event) => setForm({ ...form, [field]: event.target.value });

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setErrors({});
    setError(null);
    try {
      await api("/auth/register", { method: "POST", body: form, auth: false });
      navigate("/login?registered=1");
    } catch (err) {
      const byField = fieldErrors(err);
      setErrors(byField);
      if (Object.keys(byField).length === 0) setError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Create your account"
      subtitle="Book live webinars and track your sessions."
      footer={
        <>
          Already registered?{" "}
          <Link to="/login" className="font-semibold text-brand-700 hover:underline">
            Log in
          </Link>
        </>
      }
    >
      <form className="space-y-4" onSubmit={handleSubmit} noValidate>
        <Input label="Full name" autoComplete="name" required value={form.name} onChange={set("name")} error={errors.name} />
        <Input label="Email" type="email" autoComplete="email" required value={form.email} onChange={set("email")} error={errors.email} />
        <Input
          label="Mobile number"
          type="tel"
          autoComplete="tel"
          placeholder="98765 43210"
          required
          value={form.phone}
          onChange={set("phone")}
          error={errors.phone}
          hint="10-digit Indian mobile number — used for booking SMS and reminders."
        />
        <Input
          label="Password"
          type="password"
          autoComplete="new-password"
          required
          value={form.password}
          onChange={set("password")}
          error={errors.password}
          hint="At least 8 characters, with a letter and a number."
        />
        <Select label="Department" required value={form.department_id} onChange={set("department_id")} error={errors.department_id}>
          <option value="" disabled>
            Select your department
          </option>
          {(departments.data ?? []).map((department) => (
            <option key={department.id} value={department.id}>
              {department.name}
            </option>
          ))}
        </Select>
        {error && <Alert kind="error">{error}</Alert>}
        <Button type="submit" className="w-full" loading={submitting}>
          Create account
        </Button>
      </form>
    </AuthCard>
  );
}
