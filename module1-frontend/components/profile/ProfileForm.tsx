"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { GlassCard } from "@/components/check-in/GlassCard";
import { useAuth } from "@/components/auth/AuthProvider";
import { LANGUAGES } from "@/lib/authTypes";
import { useTheme } from "@/components/theme/ThemeProvider";
import type { ThemePreference } from "@/lib/theme";

export function ProfileForm() {
  const { user, updateProfile, changePassword } = useAuth();
  const { preference, setPreference } = useTheme();
  const [username, setUsername] = useState(user?.username ?? "");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [language, setLanguage] = useState(user?.language ?? "en");
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);

  const [currentPassword, setCurrentPassword] = useState("");
  const [nextPassword, setNextPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [pendingProfile, setPendingProfile] = useState(false);
  const [pendingPassword, setPendingPassword] = useState(false);

  if (!user) return null;

  async function onSaveProfile(event: FormEvent) {
    event.preventDefault();
    setProfileError(null);
    setProfileMessage(null);
    if (!username.trim() || !fullName.trim() || !email.trim()) {
      setProfileError("Username, display name, and email are required.");
      return;
    }
    setPendingProfile(true);
    await new Promise((resolve) => setTimeout(resolve, 250));
    updateProfile({
      username: username.trim(),
      full_name: fullName.trim(),
      email: email.trim(),
      language,
    });
    setPendingProfile(false);
    setProfileMessage("Profile saved.");
  }

  async function onChangePassword(event: FormEvent) {
    event.preventDefault();
    setPasswordError(null);
    setPasswordMessage(null);
    if (nextPassword !== confirmPassword) {
      setPasswordError("New passwords do not match.");
      return;
    }
    setPendingPassword(true);
    try {
      await changePassword(currentPassword, nextPassword);
      setCurrentPassword("");
      setNextPassword("");
      setConfirmPassword("");
      setPasswordMessage("Password updated.");
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : "Could not update password.");
    } finally {
      setPendingPassword(false);
    }
  }

  return (
    <div className="flex w-full max-w-lg flex-col gap-4 px-4 py-6 animate-fade-up sm:py-8">
      <div className="px-1">
        <Link href="/" className="text-sm text-white/70 hover:text-white">
          ← Back
        </Link>
        <h1 className="mt-2 font-display text-3xl font-semibold text-white">
          Profile
        </h1>
        <p className="mt-1 text-sm text-white/75">
          Manage your account. Changes are stored on this device for the current
          session.
        </p>
      </div>

      <GlassCard className="p-6 sm:p-7">
        <h2 className="font-display text-xl font-semibold text-white">Account</h2>
        <form className="mt-5 space-y-4" onSubmit={onSaveProfile}>
          <label className="block text-sm font-medium text-white/90">
            Username
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              className="mt-2 w-full rounded-2xl border border-white/25 bg-white/15 px-4 py-3 text-white outline-none focus:border-white/60"
            />
          </label>
          <label className="block text-sm font-medium text-white/90">
            Display name
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              autoComplete="name"
              className="mt-2 w-full rounded-2xl border border-white/25 bg-white/15 px-4 py-3 text-white outline-none focus:border-white/60"
            />
          </label>
          <label className="block text-sm font-medium text-white/90">
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              className="mt-2 w-full rounded-2xl border border-white/25 bg-white/15 px-4 py-3 text-white outline-none focus:border-white/60"
            />
          </label>
          <label className="block text-sm font-medium text-white/90">
            Language
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="mt-2 w-full rounded-2xl border border-white/25 bg-sky-950/70 px-4 py-3 text-white outline-none focus:border-white/60"
            >
              {LANGUAGES.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          {profileError && <p className="text-sm text-rose-200">{profileError}</p>}
          {profileMessage && <p className="text-sm text-emerald-600 dark:text-emerald-200">{profileMessage}</p>}
          <button
            type="submit"
            disabled={pendingProfile}
            className="w-full rounded-2xl bg-white/90 px-6 py-3.5 text-sm font-semibold text-sky-950 disabled:opacity-60"
          >
            {pendingProfile ? "Saving…" : "Save profile"}
          </button>
        </form>
      </GlassCard>

      <GlassCard className="p-6 sm:p-7">
        <h2 className="font-display text-xl font-semibold text-white">Appearance</h2>
        <p className="mt-1 text-sm text-white/70">
          Default follows your device. Light uses a pale base; dark uses a near-black base.
        </p>
        <div className="mt-4 grid grid-cols-3 gap-2">
          {(
            [
              { id: "system", label: "System" },
              { id: "light", label: "Light" },
              { id: "dark", label: "Dark" },
            ] as { id: ThemePreference; label: string }[]
          ).map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setPreference(option.id)}
              className={[
                "rounded-2xl border px-3 py-3 text-sm font-semibold transition",
                preference === option.id
                  ? "border-slate-900 bg-slate-900 text-slate-50 dark:border-white dark:bg-white dark:text-slate-950"
                  : "border-white/30 bg-white/10 text-white",
              ].join(" ")}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-2xl border border-slate-200 bg-slate-100 p-3 text-slate-900">
            <p className="text-xs font-semibold uppercase tracking-wide">Light</p>
            <p className="mt-1 text-sm">Pale gray-white canvas</p>
          </div>
          <div className="rounded-2xl border border-slate-700 bg-slate-950 p-3 text-slate-100">
            <p className="text-xs font-semibold uppercase tracking-wide">Dark</p>
            <p className="mt-1 text-sm">Near-black canvas</p>
          </div>
        </div>
      </GlassCard>

      <GlassCard className="p-6 sm:p-7">
        <h2 className="font-display text-xl font-semibold text-white">Password</h2>
        <p className="mt-1 text-sm text-white/70">
          Password updates are stubbed and are not sent to a server yet.
        </p>
        <form className="mt-5 space-y-4" onSubmit={onChangePassword}>
          <label className="block text-sm font-medium text-white/90">
            Current password
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              autoComplete="current-password"
              className="mt-2 w-full rounded-2xl border border-white/25 bg-white/15 px-4 py-3 text-white outline-none focus:border-white/60"
            />
          </label>
          <label className="block text-sm font-medium text-white/90">
            New password
            <input
              type="password"
              value={nextPassword}
              onChange={(e) => setNextPassword(e.target.value)}
              autoComplete="new-password"
              className="mt-2 w-full rounded-2xl border border-white/25 bg-white/15 px-4 py-3 text-white outline-none focus:border-white/60"
            />
          </label>
          <label className="block text-sm font-medium text-white/90">
            Confirm new password
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              className="mt-2 w-full rounded-2xl border border-white/25 bg-white/15 px-4 py-3 text-white outline-none focus:border-white/60"
            />
          </label>
          {passwordError && <p className="text-sm text-rose-200">{passwordError}</p>}
          {passwordMessage && <p className="text-sm text-emerald-200">{passwordMessage}</p>}
          <button
            type="submit"
            disabled={pendingPassword}
            className="w-full rounded-2xl bg-white/90 px-6 py-3.5 text-sm font-semibold text-sky-950 disabled:opacity-60"
          >
            {pendingPassword ? "Updating…" : "Update password"}
          </button>
        </form>
      </GlassCard>
    </div>
  );
}
