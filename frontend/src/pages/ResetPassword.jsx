import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import AuthCard from "../components/AuthCard.jsx";
import { Alert, Button, Input } from "../components/ui.jsx";
import { api, fieldErrors } from "../lib/api.js";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (password !== confirm) {
      setError("The passwords don't match.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api("/auth/reset-password", { method: "POST", body: { token, new_password: password }, auth: false });
      navigate("/login?reset=1");
    } catch (err) {
      setError(fieldErrors(err).new_password ?? err.message);
      setSubmitting(false);
    }
  }

  return (
    <AuthCard title="Choose a new password" footer={<Link to="/login" className="font-semibold text-brand-700 hover:underline">Back to log in</Link>}>
      {!token ? (
        <Alert kind="error">
          This reset link is incomplete. <Link to="/forgot-password" className="font-semibold underline">Request a new one</Link>.
        </Alert>
      ) : (
        <form className="space-y-4" onSubmit={handleSubmit}>
          <Input
            label="New password"
            type="password"
            autoComplete="new-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            hint="At least 8 characters, with a letter and a number."
          />
          <Input label="Confirm new password" type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          {error && <Alert kind="error">{error}</Alert>}
          <Button type="submit" className="w-full" loading={submitting}>
            Update password
          </Button>
        </form>
      )}
    </AuthCard>
  );
}
