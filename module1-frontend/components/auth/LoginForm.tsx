"use client";
import { useState, type FormEvent } from "react";
import { GlassCard } from "@/components/check-in/GlassCard";
import { useAuth } from "./AuthProvider";
import { isInstructorApp } from "@/lib/appSurface";
export function LoginForm() {
  const { login } = useAuth();
  const instructorApp = isInstructorApp();
  const [register, setRegister] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setPending(true);
    try {
      if (register) {
        const response = await fetch("/api/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, full_name: fullName }),
        });
        const data = await response.json();
        if (!response.ok)
          throw new Error(
            typeof data.detail === "string"
              ? data.detail
              : "Registration failed. Check your name, email, and password.",
          );
      }
      await login(email, password, instructorApp ? "instructor" : "student");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to sign in.");
    } finally {
      setPending(false);
    }
  }
  const input =
    "mt-2 w-full rounded-xl border border-white/25 bg-white/15 p-3 text-white";
  return (
    <GlassCard className="w-full max-w-md p-8">
      <h1 className="text-3xl font-semibold">
        {register ? "Create student account" : "Sign in"}
      </h1>
      <p className="mt-3">
        {instructorApp
          ? "Use your instructor or administrator account."
          : "Sign in to enroll your face and record attendance."}
      </p>
      <form onSubmit={submit} className="mt-6 space-y-4">
        {register && (
          <label className="block">
            Full name
            <input
              className={input}
              autoComplete="name"
              required
              maxLength={255}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </label>
        )}
        <label className="block">
          Email
          <input
            className={input}
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="block">
          Password
          <input
            className={input}
            type="password"
            autoComplete={register ? "new-password" : "current-password"}
            minLength={register ? 8 : undefined}
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {register && (
          <p className="text-sm">
            Use at least 8 characters. Your instructor will enroll you in your
            courses.
          </p>
        )}
        {error && (
          <p role="alert" className="text-rose-200">
            {error}
          </p>
        )}
        <button
          disabled={pending}
          className="w-full rounded-xl bg-white p-3 font-semibold text-sky-950 disabled:opacity-40"
        >
          {pending ? "Please wait…" : register ? "Create account" : "Sign in"}
        </button>
      </form>
      {!instructorApp && (
        <button
          disabled={pending}
          onClick={() => {
            setRegister(!register);
            setError("");
          }}
          className="mt-5 underline"
        >
          {register
            ? "Already have an account? Sign in"
            : "Create a student account"}
        </button>
      )}
    </GlassCard>
  );
}
