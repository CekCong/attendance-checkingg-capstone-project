"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useRef,
  type ReactNode,
} from "react";
import { studentRequest } from "@/lib/studentApi";
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
  deleteAccount: (password: string) => Promise<void>;
  updateProfile: (patch: ProfileUpdate) => Promise<void>;
  changePassword: (
    currentPassword: string,
    nextPassword: string,
  ) => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function tokenExpiry(token: string): number {
  try {
    const payload = token.split(".")[1];
    return (
      JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/"))).exp * 1000
    );
  } catch {
    return 0;
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

  const generation = useRef(0);

  const clearSession = useCallback(() => {
    sessionStorage.removeItem(ACCESS_STORAGE_KEY);
    clearStoredProfile();
    setAccessToken(null);
    setUser(null);
  }, []);

  const acceptSession = useCallback(
    (data: { access_token: string; user: AuthUser }) => {
      const next = mergeProfile(normalizeUser(data.user));
      sessionStorage.setItem(ACCESS_STORAGE_KEY, data.access_token);
      saveStoredProfile(next);
      setAccessToken(data.access_token);
      setUser(next);
    },
    [],
  );

  const refresh = useCallback(async () => {
    const currentGeneration = generation.current;
    try {
      const response = await fetch("/api/auth/refresh", {
        method: "POST",
        credentials: "include",
        cache: "no-store",
      });
      if (!response.ok) throw new Error("Session refresh failed");
      const data = await response.json();
      if (currentGeneration === generation.current) acceptSession(data);
    } catch {
      if (currentGeneration === generation.current) clearSession();
    }
  }, [acceptSession, clearSession]);

  useEffect(() => {
    let active = true;
    // Restore identity from the backend, never from unverified cached claims.
    void refresh().finally(() => {
      if (active) setReady(true);
    });
    return () => {
      active = false;
      generation.current += 1;
    };
  }, [refresh]);

  useEffect(() => {
    if (!accessToken) return;
    const renew = () => {
      if (tokenExpiry(accessToken) - Date.now() < 60_000) void refresh();
    };
    const timer = window.setTimeout(
      () => void refresh(),
      Math.max(0, tokenExpiry(accessToken) - Date.now() - 60_000),
    );
    window.addEventListener("focus", renew);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("focus", renew);
    };
  }, [accessToken, refresh]);

  const login = useCallback(
    async (email: string, password: string, role: UserRole) => {
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
      generation.current += 1;
      acceptSession(data);
    },
    [acceptSession],
  );

  const logout = useCallback(async () => {
    generation.current += 1;
    clearSession();
    const response = await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "include",
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    });
    if (!response.ok)
      throw new Error(
        "Signed out locally, but server logout could not be confirmed",
      );
  }, [accessToken, clearSession]);

  const updateProfile = useCallback(
    async (patch: ProfileUpdate) => {
      if (!accessToken) throw new Error("Please sign in again.");
      const saved = await studentRequest<AuthUser>("/users/me", accessToken, {
        method: "PUT",
        body: JSON.stringify({ full_name: patch.full_name }),
      });
      const next = normalizeUser({
        ...saved,
        language: patch.language ?? user?.language ?? "en",
      });
      saveStoredProfile(next);
      setUser(next);
    },
    [accessToken, user?.language],
  );

  const changePassword = useCallback(
    async (currentPassword: string, nextPassword: string) => {
      if (!accessToken) throw new Error("Please sign in again.");
      await studentRequest("/auth/password", accessToken, {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: nextPassword,
        }),
      });
      generation.current += 1;
      clearSession();
      // The backend already revoked every session; this also clears the cookie.
      await fetch("/api/auth/logout", { method: "POST", credentials: "include" }).catch(() => {});
    },
    [accessToken, clearSession],
  );

  const deleteAccount = useCallback(async (password: string) => {
    if (!accessToken) throw new Error("Please sign in again.");
    await studentRequest("/users/me", accessToken, {
      method: "DELETE", body: JSON.stringify({ current_password: password }),
    });
    generation.current += 1;
    clearSession();
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" }).catch(() => {});
  }, [accessToken, clearSession]);

  const value = useMemo(
    () => ({
      ready,
      user,
      accessToken,
      login,
      logout,
      deleteAccount,
      updateProfile,
      changePassword,
    }),
    [ready, user, accessToken, login, logout, deleteAccount, updateProfile, changePassword],
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
