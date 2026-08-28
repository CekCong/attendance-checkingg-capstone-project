"use client";

import { useAuth } from "@/components/auth/AuthProvider";
import { AppShell } from "@/components/auth/AppShell";
import { LoginForm } from "@/components/auth/LoginForm";
import { CheckInWorkflow } from "@/components/check-in/CheckInWorkflow";
import { InstructorDashboard } from "@/components/instructor/InstructorDashboard";
import { isInstructorApp } from "@/lib/appSurface";

export function HomeGate() {
  const { ready, user } = useAuth();
  const instructorApp = isInstructorApp();

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
      {instructorApp ? <InstructorDashboard /> : <CheckInWorkflow />}
    </AppShell>
  );
}
