import type { ReactNode } from "react";

type PageShellProps = {
  children: ReactNode;
  variant?: "default" | "teen" | "parent" | "kid";
  className?: string;
};

const blobColors: Record<NonNullable<PageShellProps["variant"]>, [string, string]> = {
  default: ["var(--color-warm-blob-default-a)", "var(--color-warm-blob-default-b)"],
  teen: ["var(--color-warm-blob-teen-a)", "var(--color-warm-blob-teen-b)"],
  kid: ["var(--color-warm-blob-teen-a)", "var(--color-warm-blob-teen-b)"],
  parent: ["var(--color-warm-blob-parent-a)", "var(--color-warm-blob-parent-b)"],
};

export default function PageShell({
  children,
  variant = "default",
  className = "",
}: PageShellProps) {
  const [blobA, blobB] = blobColors[variant];

  return (
    <div className={`relative min-h-screen overflow-hidden ${className}`}>
      <div
        className="page-blob -left-20 -top-20 h-64 w-64"
        style={{ background: blobA }}
        aria-hidden
      />
      <div
        className="page-blob -bottom-16 -right-16 h-72 w-72"
        style={{ background: blobB }}
        aria-hidden
      />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
