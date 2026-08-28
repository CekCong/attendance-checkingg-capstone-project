export type AppSurface = "student" | "instructor";

export function getAppSurface(): AppSurface {
  return process.env.NEXT_PUBLIC_APP_SURFACE === "instructor"
    ? "instructor"
    : "student";
}

export function isInstructorApp() {
  return getAppSurface() === "instructor";
}
