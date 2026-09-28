"use client"

import * as React from "react"

import { cn } from "@/lib/utils"

interface FieldShellProps {
  label?: string
  hint?: string
  error?: string
  htmlFor?: string
  className?: string
  children: React.ReactNode
}

function FieldShell({ label, hint, error, htmlFor, className, children }: FieldShellProps) {
  return (
    <div className={cn("flex flex-col", className)}>
      {label && (
        <label className="field-label" htmlFor={htmlFor}>
          {label}
        </label>
      )}
      {children}
      {error ? (
        <p className="mt-1.5 text-[12px] text-[var(--color-error)]">{error}</p>
      ) : (
        hint && <p className="mt-1.5 text-[12px] text-ink-subtle">{hint}</p>
      )}
    </div>
  )
}

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  hint?: string
  error?: string
  wrapperClassName?: string
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, className, wrapperClassName, id, ...props },
  ref,
) {
  const generatedId = React.useId()
  const fieldId = id ?? generatedId

  return (
    <FieldShell label={label} hint={hint} error={error} htmlFor={fieldId} className={wrapperClassName}>
      <input
        ref={ref}
        id={fieldId}
        className={cn("field", error && "!border-[var(--color-error)]", className)}
        aria-invalid={error ? true : undefined}
        {...props}
      />
    </FieldShell>
  )
})

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  hint?: string
  error?: string
  wrapperClassName?: string
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, hint, error, className, wrapperClassName, id, ...props },
  ref,
) {
  const generatedId = React.useId()
  const fieldId = id ?? generatedId

  return (
    <FieldShell label={label} hint={hint} error={error} htmlFor={fieldId} className={wrapperClassName}>
      <textarea
        ref={ref}
        id={fieldId}
        className={cn("field resize-y leading-relaxed", error && "!border-[var(--color-error)]", className)}
        aria-invalid={error ? true : undefined}
        {...props}
      />
    </FieldShell>
  )
})

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  hint?: string
  error?: string
  wrapperClassName?: string
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hint, error, className, wrapperClassName, id, children, ...props },
  ref,
) {
  const generatedId = React.useId()
  const fieldId = id ?? generatedId

  return (
    <FieldShell label={label} hint={hint} error={error} htmlFor={fieldId} className={wrapperClassName}>
      <select
        ref={ref}
        id={fieldId}
        // Native option lists render with the OS palette; force a dark
        // background so the dropdown is not white-on-white.
        className={cn("field cursor-pointer [&>option]:bg-[var(--color-bg-muted)]", error && "!border-[var(--color-error)]", className)}
        aria-invalid={error ? true : undefined}
        {...props}
      >
        {children}
      </select>
    </FieldShell>
  )
})
