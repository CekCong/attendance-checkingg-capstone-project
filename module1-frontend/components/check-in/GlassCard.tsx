import type { ReactNode } from "react";

type GlassCardProps = {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
};

export function GlassCard({
  children,
  className = "",
  as: Tag = "div",
}: GlassCardProps) {
  return (
    <Tag
      className={[
        "relative overflow-hidden rounded-3xl",
        "border border-[color:var(--card-border)] bg-[color:var(--card)] shadow-[0_8px_32px_rgba(8,40,60,0.18)]",
        "backdrop-blur-2xl",
        "before:pointer-events-none before:absolute before:inset-0 before:rounded-3xl",
        "before:bg-gradient-to-br before:from-white/50 before:via-white/10 before:to-transparent dark:before:from-white/20",
        className,
      ].join(" ")}
    >
      <div className="relative z-10">{children}</div>
    </Tag>
  );
}
