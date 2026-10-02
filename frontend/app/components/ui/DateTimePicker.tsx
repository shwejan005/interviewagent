"use client"

import { useEffect, useId, useMemo, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Clock3 } from "lucide-react"

export type DateTimePickerProps = {
  value: string
  onChange: (value: string) => void
  label?: string
  placeholder?: string
  minDate?: string
  minDatetime?: string
  minDatetimeLabel?: string
  error?: string
  disabled?: boolean
}

type ParsedValue = {
  date: string
  hour24: number
  minute: number
}

type PopoverPosition = {
  top: number
  left: number
  width: number
  height: number
  compact: boolean
}

type MonthCell = {
  day: number | null
  key: string
}

type Period = "AM" | "PM"

const DAY_LABELS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]
const POPOVER_WIDTH = 460
const POPOVER_HEIGHT = 366
const COMPACT_POPOVER_HEIGHT = 610
const VIEWPORT_PADDING = 12
const PICKER_OPEN_EVENT = "evalia:datetime-picker-open"

function pad2(value: number): string {
  return String(value).padStart(2, "0")
}

export function dateKey(date = new Date()): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`
}

function parseValue(value: string): ParsedValue {
  if (!value) return { date: "", hour24: 9, minute: 0 }
  const [date, time = "09:00"] = value.split("T")
  const [hour = "9", minute = "0"] = time.split(":")
  return {
    date,
    hour24: Math.max(0, Math.min(23, Number.parseInt(hour, 10) || 0)),
    minute: Math.max(0, Math.min(59, Number.parseInt(minute, 10) || 0)),
  }
}

function monthCells(year: number, month: number): MonthCell[] {
  const firstWeekday = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const cells: MonthCell[] = []
  for (let slot = 0; slot < firstWeekday; slot += 1) {
    cells.push({ day: null, key: `empty-leading-${year}-${month}-${slot}` })
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push({ day, key: `${year}-${pad2(month + 1)}-${pad2(day)}` })
  }
  let trailingSlot = 0
  while (cells.length % 7 !== 0) {
    cells.push({ day: null, key: `empty-trailing-${year}-${month}-${trailingSlot}` })
    trailingSlot += 1
  }
  return cells
}

function formatMonth(date: Date): string {
  return date.toLocaleDateString(undefined, { month: "long", year: "numeric" })
}

function formatDateTime(value: string): string | null {
  if (!value) return null
  const { date, hour24, minute } = parseValue(value)
  if (!date) return null
  const parsed = new Date(`${date}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return null
  const hour12 = hour24 % 12 || 12
  const period = hour24 >= 12 ? "PM" : "AM"
  return `${parsed.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}, ${hour12}:${pad2(minute)} ${period}`
}

function sameMonth(left: Date, right: Date): boolean {
  return left.getFullYear() === right.getFullYear() && left.getMonth() === right.getMonth()
}

function toDateKey(year: number, month: number, day: number): string {
  return `${year}-${pad2(month + 1)}-${pad2(day)}`
}

function compareDateTime(date: string, hour24: number, minute: number, minimum: string): boolean {
  const minimumValue = parseValue(minimum)
  if (!minimumValue.date) return false
  if (date !== minimumValue.date) return date < minimumValue.date
  return hour24 < minimumValue.hour24 || (hour24 === minimumValue.hour24 && minute < minimumValue.minute)
}

function hourFrom12(hour12: number, period: Period): number {
  if (period === "AM") return hour12 === 12 ? 0 : hour12
  return hour12 === 12 ? 12 : hour12 + 12
}

function dayClass(disabled: boolean, selected: boolean, today: boolean): string {
  if (disabled) return "cursor-not-allowed text-ink-subtle/40"
  if (selected) return "bg-[var(--color-primary)] text-[#0a0a0a] shadow-glow-primary"
  if (today) return "bg-[rgba(249,115,22,0.14)] font-bold text-brand"
  return "text-ink-muted hover:bg-glass-low hover:text-ink-heading"
}

function periodClass(active: boolean): string {
  return active
    ? "border border-[var(--color-primary)] bg-[var(--color-primary)] text-[#0a0a0a] shadow-glow-primary"
    : "border border-[rgba(255,255,255,0.16)] bg-[rgba(255,255,255,0.06)] text-ink-heading hover:border-[rgba(249,115,22,0.55)] hover:bg-[rgba(249,115,22,0.12)]"
}

export function DateTimePicker({
  value,
  onChange,
  label,
  placeholder = "Select date & time",
  minDate,
  minDatetime,
  minDatetimeLabel,
  error,
  disabled = false,
}: Readonly<DateTimePickerProps>) {
  const parsed = useMemo(() => parseValue(value), [value])
  const [open, setOpen] = useState(false)
  const [selectedDate, setSelectedDate] = useState(parsed.date)
  const [hour24, setHour24] = useState(parsed.hour24)
  const [minute, setMinute] = useState(parsed.minute)
  const [pickerMonth, setPickerMonth] = useState(() => {
    const source = parsed.date ? new Date(`${parsed.date}T00:00:00`) : new Date()
    return new Date(source.getFullYear(), source.getMonth(), 1)
  })
  const [position, setPosition] = useState<PopoverPosition>({
    top: 0,
    left: 0,
    width: POPOVER_WIDTH,
    height: POPOVER_HEIGHT,
    compact: false,
  })
  const pickerId = useId()
  const wrapperRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const popoverRef = useRef<HTMLDialogElement>(null)
  const dayGridRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setSelectedDate(parsed.date)
    setHour24(parsed.hour24)
    setMinute(parsed.minute)
    const constraintDate = parsed.date || (minDatetime ? parseValue(minDatetime).date : minDate)
    if (constraintDate) {
      const nextMonth = new Date(`${constraintDate}T00:00:00`)
      if (!Number.isNaN(nextMonth.getTime())) setPickerMonth(new Date(nextMonth.getFullYear(), nextMonth.getMonth(), 1))
    }
  }, [minDate, minDatetime, parsed])

  useEffect(() => {
    if (!open) return
    const closeOnPointerDown = (event: MouseEvent) => {
      const target = event.target as Node
      if (!wrapperRef.current?.contains(target) && !popoverRef.current?.contains(target)) setOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", closeOnPointerDown)
    document.addEventListener("keydown", closeOnEscape)
    return () => {
      document.removeEventListener("mousedown", closeOnPointerDown)
      document.removeEventListener("keydown", closeOnEscape)
    }
  }, [open])

  useEffect(() => {
    const closeWhenAnotherPickerOpens = (event: Event) => {
      const openedPickerId = (event as CustomEvent<string>).detail
      if (openedPickerId !== pickerId) setOpen(false)
    }
    window.addEventListener(PICKER_OPEN_EVENT, closeWhenAnotherPickerOpens)
    return () => window.removeEventListener(PICKER_OPEN_EVENT, closeWhenAnotherPickerOpens)
  }, [pickerId])

  useEffect(() => {
    if (!open) return
    const updatePosition = () => {
      const trigger = triggerRef.current
      if (!trigger) return
      const rect = trigger.getBoundingClientRect()
      const width = Math.min(POPOVER_WIDTH, window.innerWidth - VIEWPORT_PADDING * 2)
      const compact = width < 420 || window.innerWidth < 560
      const height = Math.min(
        compact ? COMPACT_POPOVER_HEIGHT : POPOVER_HEIGHT,
        window.innerHeight - VIEWPORT_PADDING * 2,
      )
      const belowSpace = window.innerHeight - rect.bottom - VIEWPORT_PADDING
      const aboveSpace = rect.top - VIEWPORT_PADDING
      const below = belowSpace >= height || belowSpace >= aboveSpace
      const rawTop = below ? rect.bottom + 8 : rect.top - height - 8
      const rawLeft = Math.min(rect.left, window.innerWidth - width - VIEWPORT_PADDING)
      setPosition({
        top: Math.max(VIEWPORT_PADDING, Math.min(rawTop, window.innerHeight - height - VIEWPORT_PADDING)),
        left: Math.max(VIEWPORT_PADDING, rawLeft),
        width,
        height,
        compact,
      })
    }
    updatePosition()
    window.addEventListener("resize", updatePosition)
    window.addEventListener("scroll", updatePosition, true)
    return () => {
      window.removeEventListener("resize", updatePosition)
      window.removeEventListener("scroll", updatePosition, true)
    }
  }, [open])

  const minTime = minDatetime ? parseValue(minDatetime) : null
  const minimumDay = minDatetime ? minTime?.date : minDate
  const today = dateKey()
  const displayValue = formatDateTime(value)
  const period = hour24 >= 12 ? "PM" : "AM"
  const hour12 = hour24 % 12 || 12
  const cells = monthCells(pickerMonth.getFullYear(), pickerMonth.getMonth())

  const isDisabledDay = (iso: string) => Boolean(minimumDay && iso < minimumDay)

  const emit = (nextDate: string, nextHour: number, nextMinute: number) => {
    let resolvedHour = nextHour
    let resolvedMinute = nextMinute
    if (nextDate && minDatetime && compareDateTime(nextDate, resolvedHour, resolvedMinute, minDatetime)) {
      resolvedHour = minTime?.hour24 ?? resolvedHour
      resolvedMinute = minTime?.minute ?? resolvedMinute
    }
    setSelectedDate(nextDate)
    setHour24(resolvedHour)
    setMinute(resolvedMinute)
    if (!nextDate) return
    onChange(`${nextDate}T${pad2(resolvedHour)}:${pad2(resolvedMinute)}`)
  }

  const stepHour = (direction: -1 | 1) => {
    emit(selectedDate, (hour24 + direction + 24) % 24, minute)
  }

  const stepMinute = (direction: -1 | 1) => {
    const minutesInDay = 24 * 60
    const steppedTime = (hour24 * 60 + minute + direction * 5 + minutesInDay) % minutesInDay
    emit(selectedDate, Math.floor(steppedTime / 60), steppedTime % 60)
  }

  const moveDay = (iso: string, offset: number) => {
    const current = new Date(`${iso}T00:00:00`)
    current.setDate(current.getDate() + offset)
    const nextIso = dateKey(current)
    if (isDisabledDay(nextIso)) return
    const nextMonth = new Date(current.getFullYear(), current.getMonth(), 1)
    if (!sameMonth(nextMonth, pickerMonth)) setPickerMonth(nextMonth)
    window.requestAnimationFrame(() => dayGridRef.current?.querySelector<HTMLButtonElement>(`[data-iso="${nextIso}"]`)?.focus())
  }

  const openPicker = () => {
    if (disabled) return
    setOpen((current) => {
      const next = !current
      if (next) window.dispatchEvent(new CustomEvent(PICKER_OPEN_EVENT, { detail: pickerId }))
      return next
    })
  }

  return (
    <div ref={wrapperRef} className="relative flex flex-col">
      {label && <label className="field-label" htmlFor={`datetime-${label.toLowerCase().replaceAll(" ", "-")}`}>{label}</label>}
      <button
        ref={triggerRef}
        id={label ? `datetime-${label.toLowerCase().replaceAll(" ", "-")}` : undefined}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        disabled={disabled}
        onClick={openPicker}
        className={`field flex items-center gap-3 text-left ${error ? "!border-[var(--color-error)]" : ""} ${disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"}`}
      >
        <CalendarDays size={16} className="shrink-0 text-brand" />
        <span className={displayValue ? "text-ink-heading" : "text-ink-subtle"}>{displayValue || placeholder}</span>
      </button>
      {error && <p className="mt-1.5 text-[12px] text-[var(--color-error)]">{error}</p>}

      {open && typeof document !== "undefined" && createPortal(
        <dialog
          ref={popoverRef}
          open
          aria-label={`${label || "Date and time"} picker`}
          className={`glass-high fixed z-[9999] m-0 flex overflow-y-auto p-0 ${position.compact ? "flex-col" : "overflow-hidden"}`}
          style={{ top: position.top, left: position.left, width: position.width, maxWidth: `calc(100vw - ${VIEWPORT_PADDING * 2}px)`, maxHeight: position.height }}
        >
          <div className={position.compact ? "w-full shrink-0 border-b border-subtle p-3" : "w-[60%] shrink-0 border-r border-subtle p-3"}>
            <div className="mb-2 flex items-center justify-between">
              <button type="button" aria-label="Previous month" onClick={() => setPickerMonth((current) => new Date(current.getFullYear(), current.getMonth() - 1, 1))} className="rounded-md p-1.5 text-ink-subtle hover:bg-glass-low hover:text-ink-heading"><ChevronLeft size={16} /></button>
              <span className="text-[13px] font-semibold text-ink-heading">{formatMonth(pickerMonth)}</span>
              <button type="button" aria-label="Next month" onClick={() => setPickerMonth((current) => new Date(current.getFullYear(), current.getMonth() + 1, 1))} className="rounded-md p-1.5 text-ink-subtle hover:bg-glass-low hover:text-ink-heading"><ChevronRight size={16} /></button>
            </div>
            <div className="mb-1 grid grid-cols-7 gap-1 text-[10px] font-semibold text-ink-subtle">{DAY_LABELS.map((day) => <div key={day} className="py-1 text-center">{day}</div>)}</div>
            <div ref={dayGridRef} role="grid" aria-label="Choose date" className="grid grid-cols-7 gap-1">
              {cells.map(({ day, key }) => {
                if (!day) return <div key={key} className="h-8" aria-hidden="true" />
                const iso = toDateKey(pickerMonth.getFullYear(), pickerMonth.getMonth(), day)
                const selected = iso === selectedDate
                const isToday = iso === today
                const disabledDay = isDisabledDay(iso)
                return (
                  <button
                    key={iso}
                    type="button"
                    data-iso={iso}
                    aria-label={new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" })}
                    aria-current={isToday ? "date" : undefined}
                    aria-pressed={selected}
                    disabled={disabledDay}
                    tabIndex={selected || (!selectedDate && isToday) ? 0 : -1}
                    onClick={() => emit(iso, hour24, minute)}
                    onKeyDown={(event) => {
                      const offset = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key as "ArrowLeft" | "ArrowRight" | "ArrowUp" | "ArrowDown"]
                      if (offset) {
                        event.preventDefault()
                        moveDay(iso, offset)
                      }
                    }}
                    className={`h-8 rounded-md text-[12px] font-medium transition-colors ${dayClass(disabledDay, selected, isToday)}`}
                  >
                    {day}
                  </button>
                )
              })}
            </div>
            <div className="mt-2 flex justify-end border-t border-subtle pt-2">
              <button
                type="button"
                onClick={() => !isDisabledDay(today) && emit(today, hour24, minute)}
                className="min-h-8 rounded-md border border-[rgba(249,115,22,0.45)] bg-[rgba(249,115,22,0.1)] px-3 text-[11px] font-bold text-brand transition-colors hover:border-brand hover:bg-[rgba(249,115,22,0.18)]"
              >
                Today
              </button>
            </div>
          </div>

          <div className={position.compact ? "flex w-full min-w-0 shrink-0 flex-col items-center gap-3 p-4" : "flex min-w-0 flex-1 flex-col items-center gap-3 p-4"}>
            <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-subtle"><Clock3 size={12} /> Time</div>
            {minDatetime && selectedDate === minTime?.date && <div className="w-full rounded-lg border border-[rgba(245,158,11,0.3)] bg-[rgba(245,158,11,0.1)] px-2 py-1 text-[10px] text-[var(--color-warning)]">Must be after {pad2(minTime?.hour24 % 12 || 12)}:{pad2(minTime?.minute || 0)} {minTime?.hour24 && minTime.hour24 >= 12 ? "PM" : "AM"}</div>}
            <div className="flex items-center gap-1.5">
              <TimeStepper label="Hour" value={hour12} min={1} max={12} onChange={(next) => emit(selectedDate, hourFrom12(next, period), minute)} onStep={stepHour} />
              <span className="text-lg font-bold text-ink-subtle">:</span>
              <TimeStepper label="Minute" value={minute} min={0} max={59} step={5} formatValue={pad2} onChange={(next) => emit(selectedDate, hour24, next)} onStep={stepMinute} />
              <div className="flex min-w-[64px] flex-col gap-1 rounded-lg bg-[rgba(0,0,0,0.18)] p-1">
                {(["AM", "PM"] as const).map((option) => <button key={option} type="button" aria-label={`Set ${option}`} aria-pressed={period === option} onClick={() => emit(selectedDate, hourFrom12(hour12, option), minute)} className={`min-h-8 w-full rounded-md px-2 text-[11px] font-bold tracking-[0.04em] transition-colors ${periodClass(period === option)}`}>{option}</button>)}
              </div>
            </div>
              <button type="button" onClick={() => setOpen(false)} className="mt-auto w-full rounded-lg bg-[var(--color-primary)] py-2 text-[12px] font-semibold text-[#0a0a0a] transition-colors hover:bg-[var(--color-primary-light)]">Done</button>
          </div>
        </dialog>,
        document.body,
      )}
    </div>
  )
}

function TimeStepper({
  label,
  value,
  min,
  max,
  step = 1,
  formatValue = String,
  onChange,
  onStep,
}: Readonly<{
  label: string
  value: number
  min: number
  max: number
  step?: number
  formatValue?: (value: number) => string
  onChange: (value: number) => void
  onStep?: (direction: -1 | 1) => void
}>) {
  const wrap = (next: number) => {
    if (next > max) return min
    if (next < min) return max
    return next
  }
  const handleStep = (direction: -1 | 1) => {
    if (onStep) {
      onStep(direction)
      return
    }
    onChange(wrap(value + direction * step))
  }
  return (
    <div className="flex flex-col items-center gap-1">
      <button type="button" aria-label={`Increase ${label.toLowerCase()}`} onClick={() => handleStep(1)} className="rounded-md p-1 text-ink-subtle hover:bg-glass-low hover:text-ink-heading"><ChevronUp size={14} /></button>
      <input
        aria-label={label}
        type="number"
        min={min}
        max={max}
        step={step}
        value={formatValue(value)}
        onChange={(event) => onChange(Math.max(min, Math.min(max, Number.parseInt(event.target.value, 10) || min)))}
        onKeyDown={(event) => {
          if (!onStep || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return
          event.preventDefault()
          handleStep(event.key === "ArrowUp" ? 1 : -1)
        }}
        className="w-12 rounded-lg border border-subtle bg-glass-low py-2 text-center text-[14px] font-semibold text-ink-heading outline-none focus:border-brand [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
      />
      <button type="button" aria-label={`Decrease ${label.toLowerCase()}`} onClick={() => handleStep(-1)} className="rounded-md p-1 text-ink-subtle hover:bg-glass-low hover:text-ink-heading"><ChevronDown size={14} /></button>
    </div>
  )
}
