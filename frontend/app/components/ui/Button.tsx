"use client"

import * as React from "react"
import Link from "next/link"

import { cn } from "@/lib/utils"

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger"
export type ButtonSize = "sm" | "md" | "lg"

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: "btn-primary",
  secondary: "btn-secondary",
  ghost: "btn-ghost",
  danger:
    "inline-flex items-center justify-center gap-2 rounded-[10px] border border-[rgba(239,68,68,0.4)] bg-[rgba(239,68,68,0.12)] font-medium text-[var(--color-error)] transition-colors duration-fast ease-out-expo hover:bg-[rgba(239,68,68,0.2)] disabled:cursor-not-allowed disabled:opacity-50",
}

const SIZE_CLASS: Record<ButtonSize, string> = {
  sm: "!px-3 !py-1.5 !text-[12px]",
  md: "",
  lg: "!px-6 !py-3 !text-[15px]",
}

function buttonClasses(variant: ButtonVariant, size: ButtonSize, fullWidth: boolean, className?: string) {
  return cn(VARIANT_CLASS[variant], SIZE_CLASS[size], fullWidth && "w-full", className)
}

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  fullWidth?: boolean
  loading?: boolean
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "primary", size = "md", fullWidth = false, loading = false, disabled, children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={buttonClasses(variant, size, fullWidth, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && <span className="spinner" aria-hidden="true" />}
      {children}
    </button>
  )
})

export interface ButtonLinkProps extends React.ComponentPropsWithoutRef<typeof Link> {
  variant?: ButtonVariant
  size?: ButtonSize
  fullWidth?: boolean
}

export function ButtonLink({
  className,
  variant = "primary",
  size = "md",
  fullWidth = false,
  children,
  ...props
}: Readonly<ButtonLinkProps>) {
  return (
    <Link className={buttonClasses(variant, size, fullWidth, className)} {...props}>
      {children}
    </Link>
  )
}
