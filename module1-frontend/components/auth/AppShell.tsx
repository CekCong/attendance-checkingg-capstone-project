"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import { ROLE_LABELS } from "@/lib/authTypes";

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();

  if (!user) return <>{children}</>;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between gap-4 px-4 py-4 sm:px-8">
        <Link href="/" className="block">
          <p className="font-display text-lg font-semibold text-white">SAIV</p>
          <p className="text-xs uppercase tracking-[0.18em] text-white/60">
            {ROLE_LABELS[user.role]}
          </p>
        </Link>
        <div className="flex items-center gap-2 sm:gap-3">
          <Link
            href="/profile"
            className="rounded-xl border border-white/30 bg-white/10 px-3 py-1.5 text-sm font-medium text-white hover:bg-white/20"
          >
            Profile
          </Link>
          <span className="hidden max-w-[12rem] truncate text-sm text-white/80 sm:block">
            {user.username || user.email}
          </span>
          <button
            type="button"
            onClick={() => void logout()}
            className="rounded-xl border border-white/30 bg-white/10 px-3 py-1.5 text-sm font-medium text-white hover:bg-white/20"
          >
            Log out
          </button>
        </div>
      </header>
      <div className="flex flex-1 flex-col items-center">{children}</div>
    </div>
  );
}
