"use client";

import { useState, type FormEvent } from "react";
import { GlassCard } from "@/components/check-in/GlassCard";
import { useAuth } from "@/components/auth/AuthProvider";
import { isInstructorApp } from "@/lib/appSurface";

export function LoginForm() {
  const { login } = useAuth();
  const instructorApp = isInstructorApp();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await login(email, password, instructorApp ? "instructor" : "student");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <GlassCard className="w-full max-w-md p-8 animate-fade-up">
      <p className="mb-2 text-center text-sm font-medium uppercase tracking-[0.2em] text-white/70">
        {instructorApp ? "Instructor dashboard" : "Student check-in"}
      </p>
      <h1 className="text-center font-display text-4xl font-semibold tracking-tight text-white">
        Sign in
      </h1>
      <p className="mt-3 text-center text-sm leading-relaxed text-white/80">
        {instructorApp ? (
          <>
            This React app runs on port 8501 for instructors. Students check in
            at{" "}
            <a
              className="underline decoration-white/40 underline-offset-2 hover:decoration-white"
              href="http://localhost:3000"
            >
              localhost:3000
            </a>
            .
          </>
        ) : (
          <>
            This React app runs on port 3000 for students. Instructors sign in
            at{" "}
            <a
              className="underline decoration-white/40 underline-offset-2 hover:decoration-white"
              href="http://localhost:8501"
            >
              localhost:8501
            </a>
            .
          </>
        )}{" "}
        Any username and password works in this stub.
      </p>

      <form className="mt-8 space-y-5" onSubmit={onSubmit}>
        <label className="block text-left text-sm font-medium text-white/90">
          Username or email
          <input
            type="text"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-2 w-full rounded-2xl border border-white/25 bg-white/15 px-4 py-3 text-white outline-none placeholder:text-white/40 focus:border-white/60"
            placeholder={instructorApp ? "instructor@saiv.local" : "student@saiv.local"}
          />
        </label>
        <label className="block text-left text-sm font-medium text-white/90">
          Password
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-2 w-full rounded-2xl border border-white/25 bg-white/15 px-4 py-3 text-white outline-none placeholder:text-white/40 focus:border-white/60"
            placeholder="any password"
          />
        </label>
        {error && (
          <p className="rounded-xl bg-red-500/20 px-3 py-2 text-sm text-rose-100">{error}</p>
        )}
        <button
          type="submit"
          disabled={pending}
          className="w-full rounded-2xl bg-white/90 px-6 py-3.5 text-base font-semibold text-sky-950 shadow-lg transition hover:bg-white disabled:opacity-60"
        >
          {pending ? "Signing in…" : "Continue"}
        </button>
      </form>
    </GlassCard>
  );
}
