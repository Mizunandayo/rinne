import type { ComponentPropsWithoutRef, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

type Variant = "primary" | "secondary";

interface ButtonProps extends ComponentPropsWithoutRef<"button"> {
  readonly variant?: Variant;
  readonly icon?: LucideIcon;
  readonly children: ReactNode;
}

export function Button({
  variant = "primary",
  icon: Icon,
  children,
  className,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      data-variant={variant}
      className={["rinne-button", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {Icon ? <Icon size={20} strokeWidth={2.25} aria-hidden="true" /> : null}
      <span>{children}</span>
    </button>
  );
}
