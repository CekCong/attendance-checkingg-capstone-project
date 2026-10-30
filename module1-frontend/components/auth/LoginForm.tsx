"use client";

import { useState, type FormEvent } from "react";
import { GlassCard } from "@/components/check-in/GlassCard";
import { useAuth } from "@/components/auth/AuthProvider";
import { isInstructorApp } from "@/lib/appSurface";

const inputClass = "mt-2 w-full rounded-2xl border border-white/25 bg-white/15 px-4 py-3 text-white outline-none placeholder:text-white/40 focus:border-white/60";

export function LoginForm() {
  const { login } = useAuth();
  const instructorApp = isInstructorApp();
  const accountLabel = instructorApp ? "tutor" : "student";
  const [signingUp, setSigningUp] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function changeMode() {
    setSigningUp(!signingUp);
    setPassword("");
    setConfirmPassword("");
    setError(null);
    setNotice(null);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    if (signingUp && !fullName.trim()) {
      setError("Enter your full name.");
      return;
    }
    if (signingUp && password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setPending(true);
    try {
      if (signingUp) {
        const response = await fetch("/api/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ full_name: fullName.trim(), email: email.trim(), password }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(typeof data.detail === "string" ? data.detail : "Unable to create your account.");
        }
        setSigningUp(false);
        setPassword("");
        setConfirmPassword("");
        setNotice(`Your ${accountLabel} account is ready. Sign in to continue.`);
      } else {
        await login(email.trim(), password, instructorApp ? "instructor" : "student");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to connect. Please try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <GlassCard className="w-full max-w-md p-8 animate-fade-up">
      <p className="mb-2 text-center text-sm font-medium uppercase tracking-[0.2em] text-white/70">
        {instructorApp ? "Tutor dashboard" : "Student check-in"}
      </p>
      <h1 className="text-center font-display text-4xl font-semibold tracking-tight text-white">
        {signingUp ? "Create account" : "Sign in"}
      </h1>
      <p className="mt-3 text-center text-sm leading-relaxed text-white/80">
        {signingUp
          ? `Sign up as a ${accountLabel} to ${instructorApp ? "manage your classes and attendance" : "check in to your classes"}.`
          : `Welcome back. Sign in to your ${accountLabel} account.`}
      </p>

      <form className="mt-8" onSubmit={onSubmit}>
        <fieldset disabled={pending} className="space-y-5">
          {signingUp && (
            <label className="block text-left text-sm font-medium text-white/90">
              Full name
              <input type="text" autoComplete="name" required value={fullName}
                onChange={(e) => setFullName(e.target.value)} className={inputClass}
                placeholder="Your full name" />
            </label>
          )}
          <label className="block text-left text-sm font-medium text-white/90">
            Email
            <input type="email" autoComplete="username" required value={email}
              onChange={(e) => setEmail(e.target.value)} className={inputClass}
              placeholder="you@example.com" />
          </label>
          <label className="block text-left text-sm font-medium text-white/90">
            Password
            <input type="password" autoComplete={signingUp ? "new-password" : "current-password"}
              required minLength={signingUp ? 8 : undefined} value={password}
              aria-describedby={signingUp ? "password-help" : undefined}
              onChange={(e) => setPassword(e.target.value)} className={inputClass}
              placeholder={signingUp ? "At least 8 characters" : "Your password"} />
            {signingUp && <span id="password-help" className="mt-2 block text-xs font-normal text-white/70">Use at least 8 characters.</span>}
          </label>
          {signingUp && (
            <label className="block text-left text-sm font-medium text-white/90">
              Confirm password
              <input type="password" autoComplete="new-password" required value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)} className={inputClass}
                placeholder="Enter your password again" />
            </label>
          )}
          {error && <p role="alert" className="rounded-xl bg-red-500/20 px-3 py-2 text-sm text-rose-100">{error}</p>}
          {notice && <p role="status" className="rounded-xl border border-white/25 bg-white/10 px-3 py-2 text-sm text-white">{notice}</p>}
          <button type="submit" disabled={pending}
            className="w-full rounded-2xl bg-white/90 px-6 py-3.5 text-base font-semibold text-sky-950 shadow-lg transition hover:bg-white disabled:opacity-60">
            {pending ? (signingUp ? "Creating account…" : "Signing in…") : (signingUp ? `Create ${accountLabel} account` : "Sign in")}
          </button>
        </fieldset>
      </form>
      <p className="mt-6 text-center text-sm text-white/80">
        {signingUp ? "Already have an account?" : "New here?"}{" "}
        <button type="button" onClick={changeMode} disabled={pending}
          className="font-semibold text-white underline decoration-white/40 underline-offset-4 hover:decoration-white disabled:opacity-60">
          {signingUp ? "Sign in" : "Sign up"}
        </button>
      </p>
      <p className="mt-4 text-center text-sm text-white/70">
        {instructorApp ? "Are you a student?" : "Are you a tutor?"}{" "}
        <a className="underline decoration-white/40 underline-offset-4 hover:decoration-white"
          href={instructorApp ? "http://localhost:3000" : "http://localhost:8501"}>
          {instructorApp ? "Student portal" : "Tutor portal"}
        </a>
      </p>
    </GlassCard>
  );
}
