import { useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router";

import { useAuth } from "../auth/AuthContext.jsx";
import { homeFor, safeNext } from "../auth/RequireAuth.jsx";
import AuthCard from "../components/AuthCard.jsx";
import { Alert, Button, Input } from "../components/ui.jsx";

export default function Login() {
  const { user, login } = useAuth();
  const [params] = useSearchParams();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to={safeNext(params.get("next")) ?? homeFor(user)} replace />;

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(form.email, form.password);
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Log in"
      subtitle="Welcome back to Skill Cortex."
      footer={
        <>
          New here?{" "}
          <Link to="/register" className="font-semibold text-brand-700 hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      {params.get("registered") && (
        <Alert kind="success" className="mb-4">
          Account created successfully. Log in to continue.
        </Alert>
      )}
      {params.get("reset") && (
        <Alert kind="success" className="mb-4">
          Password updated. Log in with your new password.
        </Alert>
      )}
      <form className="space-y-4" onSubmit={handleSubmit}>
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
        />
        <Input
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
        />
        {error && <Alert kind="error">{error}</Alert>}
        <Button type="submit" className="w-full" loading={submitting}>
          Log in
        </Button>
        <p className="text-center text-sm">
          <Link to="/forgot-password" className="text-brand-700 hover:underline">
            Forgot your password?
          </Link>
        </p>
      </form>
    </AuthCard>
  );
}
