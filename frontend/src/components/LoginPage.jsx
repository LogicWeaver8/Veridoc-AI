import { useState } from "react";
import Icon from "./Icons.jsx";

export default function LoginPage({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [workspace, setWorkspace] = useState("corp-india.veridox.internal");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function handleSubmit(event) {
    event.preventDefault();
    if (!email.trim() || !password.trim() || !workspace.trim()) {
      setError("Enter your work email, password and workspace instance.");
      return;
    }
    setError("");
    setSubmitting(true);
    window.setTimeout(() => {
      onLogin({ email: email.trim(), workspace: workspace.trim() });
    }, 250);
  }

  return (
    <div className="login-shell">
      <div className="login-glow login-glow-a" aria-hidden="true" />
      <div className="login-glow login-glow-b" aria-hidden="true" />

      <div className="login-card">
        <div className="login-brand">
          <div className="brand-mark brand-mark-lg">V</div>
          <div>
            <h1>VeriDox AI</h1>
            <p>Enterprise Grounded Intelligence</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <label className="field">
            <span>Work email</span>
            <input
              type="email"
              autoComplete="username"
              placeholder="you@company.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>

          <label className="field">
            <span>Password</span>
            <input
              type="password"
              autoComplete="current-password"
              placeholder="Enter your password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          <label className="field">
            <span>Workspace instance</span>
            <div className="field-static">
              <Icon name="shield" size={15} />
              <input
                type="text"
                value={workspace}
                onChange={(event) => setWorkspace(event.target.value)}
                spellCheck={false}
              />
            </div>
          </label>

          {error ? <div className="login-error">{error}</div> : null}

          <button type="submit" className="button button-primary button-lg" disabled={submitting}>
            {submitting ? "Opening workspace…" : "Sign in to workspace"}
            {!submitting ? <span aria-hidden="true">→</span> : null}
          </button>
        </form>

        <div className="login-footnote">
          <Icon name="info" size={13} />
          <span>
            Demo access gate. This build does not implement server-side authentication — do not
            expose it to untrusted networks.
          </span>
        </div>
      </div>

      <p className="login-copyright">
        Answers are restricted to indexed organisational documents · VeriDox AI 2026
      </p>
    </div>
  );
}
