import { type HTMLAttributes } from "react";

type CardProps = HTMLAttributes<HTMLDivElement>;

export function Card({ className = "", children, ...props }: CardProps) {
  return (
    <div
      className={[
        "rounded-lg border border-[#2d3748] bg-[#1a1f2e] p-4",
        className,
      ].join(" ")}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ className = "", children, ...props }: CardProps) {
  return (
    <div className={["mb-4", className].join(" ")} {...props}>
      {children}
    </div>
  );
}

export function CardTitle({ className = "", children, ...props }: CardProps) {
  return (
    <h3
      className={["text-lg font-semibold text-[#e2e8f0]", className].join(" ")}
      {...props}
    >
      {children}
    </h3>
  );
}
