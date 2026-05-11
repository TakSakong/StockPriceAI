import { type InputHTMLAttributes, forwardRef } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className = "", ...props }, ref) => {
    return (
      <div className="flex flex-col gap-1">
        {label && (
          <label className="text-sm font-medium text-[#a0aec0]">{label}</label>
        )}
        <input
          ref={ref}
          className={[
            "rounded-md border border-[#4a5568] bg-[#2d3748] px-3 py-2 text-[#e2e8f0]",
            "placeholder:text-[#718096]",
            "focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500",
            "disabled:opacity-60 disabled:cursor-not-allowed",
            error ? "border-red-500" : "",
            className,
          ].join(" ")}
          {...props}
        />
        {error && <span className="text-xs text-red-400">{error}</span>}
      </div>
    );
  },
);

Input.displayName = "Input";
