export type UserRole = "student" | "ta" | "instructor" | "admin";

export type AuthUser = {
  id: string;
  email: string;
  username: string;
  full_name: string;
  matriculation_number?: string | null;
  role: UserRole;
  language: string;
};

export const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "zh", label: "中文 (简体)" },
  { code: "zh-Hant", label: "中文 (繁體)" },
  { code: "ms", label: "Bahasa Melayu" },
  { code: "ta", label: "தமிழ்" },
] as const;

export const ROLE_LABELS: Record<UserRole, string> = {
  student: "Student",
  ta: "Teaching Assistant",
  instructor: "Instructor",
  admin: "Admin",
};

export const ROLE_NAV: Record<UserRole, { href: string; label: string }[]> = {
  student: [{ href: "/", label: "Check-in" }],
  ta: [
    { href: "/", label: "Review" },
    { href: "/", label: "Session check-ins" },
  ],
  instructor: [
    { href: "/", label: "Sessions" },
    { href: "/", label: "Enrollments" },
  ],
  admin: [
    { href: "/", label: "Users" },
    { href: "/", label: "Audit" },
    { href: "/", label: "Rate limits" },
  ],
};
