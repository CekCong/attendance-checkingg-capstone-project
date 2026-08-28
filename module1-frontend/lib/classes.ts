export type KnownClass = {
  code: string;
  title: string;
};

export const KNOWN_CLASSES: KnownClass[] = [
  { code: "CS101-L4", title: "CS101 Lecture 4" },
  { code: "CS101-TUTB", title: "CS101 Tutorial B" },
  { code: "CS204-LAB", title: "CS204 Lab" },
  { code: "CZ3002-L2", title: "CZ3002 Lecture 2" },
];

export function lookupClass(raw: string): KnownClass | null {
  const code = raw.trim().toUpperCase();
  if (!code) return null;
  return (
    KNOWN_CLASSES.find((item) => item.code === code) ?? {
      code,
      title: `Class ${code}`,
    }
  );
}
