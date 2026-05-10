import { type HTMLAttributes } from "react";

type BadgeVariant = "buy" | "sell" | "hold" | "default" | "success" | "warning" | "danger";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const variantClasses: Record<BadgeVariant, string> = {
  buy: "bg-emerald-900/50 text-emerald-400 border-emerald-700",
  sell: "bg-red-900/50 text-red-400 border-red-700",
  hold: "bg-yellow-900/50 text-yellow-400 border-yellow-700",
  success: "bg-emerald-900/50 text-emerald-400 border-emerald-700",
  warning: "bg-yellow-900/50 text-yellow-400 border-yellow-700",
  danger: "bg-red-900/50 text-red-400 border-red-700",
  default: "bg-[#2d3748] text-[#a0aec0] border-[#4a5568]",
};

export function Badge({ variant = "default", className = "", children, ...props }: BadgeProps) {
  return (
    <span
      className={[
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold",
        variantClasses[variant],
        className,
      ].join(" ")}
      {...props}
    >
      {children}
    </span>
  );
}

export function signalToBadgeVariant(signal: string): BadgeVariant {
  const s = signal.toUpperCase();
  if (s === "BUY" || s === "STRONG BUY") return "buy";
  if (s === "SELL" || s === "STRONG SELL") return "sell";
  if (s === "HOLD") return "hold";
  return "default";
}
