import type { AuthUser } from "./authTypes";

const PROFILE_KEY = "saiv_profile";

export type StoredProfile = Pick<
  AuthUser,
  "id" | "email" | "username" | "full_name" | "language" | "role"
>;

export function loadStoredProfile(): StoredProfile | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(PROFILE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as StoredProfile;
  } catch {
    return null;
  }
}

export function saveStoredProfile(user: AuthUser) {
  const stored: StoredProfile = {
    id: user.id,
    email: user.email,
    username: user.username,
    full_name: user.full_name,
    language: user.language,
    role: user.role,
  };
  sessionStorage.setItem(PROFILE_KEY, JSON.stringify(stored));
}

export function clearStoredProfile() {
  sessionStorage.removeItem(PROFILE_KEY);
}

export function mergeProfile(user: AuthUser): AuthUser {
  const stored = loadStoredProfile();
  if (!stored) return user;
  if (stored.email !== user.email && stored.id !== user.id) return user;
  return {
    ...user,
    username: stored.username || user.username,
    full_name: stored.full_name || user.full_name,
    language: stored.language || user.language,
  };
}
