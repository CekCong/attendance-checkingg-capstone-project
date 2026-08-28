"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { AuthUser, UserRole } from "@/lib/authTypes";
import {
  clearStoredProfile,
  mergeProfile,
  saveStoredProfile,
} from "@/lib/profileStorage";

const ACCESS_STORAGE_KEY = "saiv_access_token";

export type ProfileUpdate = {
  username?: string;
  full_name?: string;
  language?: string;
  email?: string;
};

type AuthContextValue = {
  ready: boolean;
  user: AuthUser | null;
  accessToken: string | null;
  login: (email: string, password: string, role: UserRole) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (patch: ProfileUpdate) => void;
  changePassword: (currentPassword: string, nextPassword: string) => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function decodeUser(token: string): AuthUser | null {
  try {
    const [, payload] = token.split(".");
    const json = JSON.parse(
      atob(payload.replace(/-/g, "+").replace(/_/g, "/")),
    ) as { sub?: string; email?: string; role?: UserRole };
    if (!json.email || !json.role) return null;
    const username = json.email.split("@")[0];
    return mergeProfile({
      id: json.sub || "unknown",
      email: json.email,
      username,
      full_name: username.replace(/[._]/g, " "),
      role: json.role,
      language: "en",
    });
  } catch {
    return null;
  }
}

function normalizeUser(user: AuthUser): AuthUser {
  return {
    ...user,
    username: user.username || user.email.split("@")[0],
    language: user.language || "en",
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    const stored = sessionStorage.getItem(ACCESS_STORAGE_KEY);
    if (stored) {
      setAccessToken(stored);
      setUser(decodeUser(stored));
    }
    setReady(true);
  }, []);

  const login = useCallback(async (email: string, password: string, role: UserRole) => {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, role }),
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || "Login failed");
    }
    const data = (await response.json()) as {
      access_token: string;
      user: AuthUser;
    };
    const next = mergeProfile(normalizeUser(data.user));
    sessionStorage.setItem(ACCESS_STORAGE_KEY, data.access_token);
    saveStoredProfile(next);
    setAccessToken(data.access_token);
    setUser(next);
  }, []);

  const logout = useCallback(async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    } finally {
      sessionStorage.removeItem(ACCESS_STORAGE_KEY);
      clearStoredProfile();
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  const updateProfile = useCallback((patch: ProfileUpdate) => {
    setUser((current) => {
      if (!current) return current;
      const next = { ...current, ...patch };
      saveStoredProfile(next);
      return next;
    });
  }, []);

  const changePassword = useCallback(async (currentPassword: string, nextPassword: string) => {
    await new Promise((resolve) => setTimeout(resolve, 400));
    if (!currentPassword || !nextPassword) {
      throw new Error("Enter your current and new password.");
    }
    if (nextPassword.length < 8) {
      throw new Error("New password must be at least 8 characters.");
    }
    if (currentPassword === nextPassword) {
      throw new Error("New password must be different from the current password.");
    }
  }, []);

  const value = useMemo(
    () => ({
      ready,
      user,
      accessToken,
      login,
      logout,
      updateProfile,
      changePassword,
    }),
    [ready, user, accessToken, login, logout, updateProfile, changePassword],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
