interface SpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

const sizeClasses = { sm: "w-4 h-4", md: "w-8 h-8", lg: "w-12 h-12" };

export function Spinner({ size = "md", className = "" }: SpinnerProps) {
  return (
    <div
      className={[
        "border-2 border-[#4a5568] border-t-blue-500 rounded-full animate-spin",
        sizeClasses[size],
        className,
      ].join(" ")}
    />
  );
}

export function FullPageSpinner() {
  return (
    <div className="flex h-64 items-center justify-center">
      <Spinner size="lg" />
    </div>
  );
}
