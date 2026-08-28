"use client";

import { AppShell } from "@/components/auth/AppShell";
import { useAuth } from "@/components/auth/AuthProvider";
import { LoginForm } from "@/components/auth/LoginForm";
import { ProfileForm } from "@/components/profile/ProfileForm";

export function ProfilePage() {
  const { ready, user } = useAuth();

  if (!ready) {
    return (
      <main className="flex flex-1 items-center justify-center py-24">
        <p className="text-white/70">Loading…</p>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="flex flex-1 flex-col items-center justify-center px-4 py-12">
        <LoginForm />
      </main>
    );
  }

  return (
    <AppShell>
      <ProfileForm />
    </AppShell>
  );
}
