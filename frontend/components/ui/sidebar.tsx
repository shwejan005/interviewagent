"use client"

import * as React from "react"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import { Slot } from "@radix-ui/react-slot"
import { PanelLeft } from "lucide-react"

import { cn } from "@/lib/utils"

const SIDEBAR_WIDTH = "16rem"
const SIDEBAR_WIDTH_ICON = "3rem"
const SIDEBAR_KEYBOARD_SHORTCUT = "b"

type SidebarContext = {
  state: "expanded" | "collapsed"
  open: boolean
  setOpen: (open: boolean) => void
  openMobile: boolean
  setOpenMobile: (open: boolean) => void
  isMobile: boolean
  toggleSidebar: () => void
}

const SidebarContext = React.createContext<SidebarContext | null>(null)

function useIsMobile() {
  const [isMobile, setIsMobile] = React.useState(false)

  React.useEffect(() => {
    const mediaQuery = window.matchMedia("(max-width: 767px)")
    const update = () => setIsMobile(mediaQuery.matches)
    update()
    mediaQuery.addEventListener("change", update)
    return () => mediaQuery.removeEventListener("change", update)
  }, [])

  return isMobile
}

export function SidebarProvider({
  defaultOpen = true,
  open: openProp,
  onOpenChange: setOpenProp,
  className,
  style,
  children,
  ...props
}: React.ComponentProps<"div"> & {
  defaultOpen?: boolean
  open?: boolean
  onOpenChange?: (open: boolean) => void
}) {
  const isMobile = useIsMobile()
  const [openMobile, setOpenMobile] = React.useState(false)
  const [_open, _setOpen] = React.useState(defaultOpen)
  const open = openProp ?? _open
  const setOpen = React.useCallback(
    (value: boolean | ((value: boolean) => boolean)) => {
      const next = typeof value === "function" ? value(open) : value
      if (setOpenProp) setOpenProp(next)
      else _setOpen(next)
      document.cookie = `sidebar_state=${next ? "expanded" : "collapsed"}; path=/; max-age=31536000`
    },
    [open, setOpenProp],
  )

  const toggleSidebar = React.useCallback(() => {
    return isMobile ? setOpenMobile((value) => !value) : setOpen((value) => !value)
  }, [isMobile, setOpen])

  React.useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === SIDEBAR_KEYBOARD_SHORTCUT && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        toggleSidebar()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [toggleSidebar])

  const contextValue = React.useMemo<SidebarContext>(
    () => ({
      state: open ? "expanded" : "collapsed",
      open,
      setOpen,
      openMobile,
      setOpenMobile,
      isMobile,
      toggleSidebar,
    }),
    [open, setOpen, openMobile, isMobile, toggleSidebar],
  )

  return (
    <SidebarContext.Provider value={contextValue}>
      <div
        style={
          {
            "--sidebar-width": SIDEBAR_WIDTH,
            "--sidebar-width-icon": SIDEBAR_WIDTH_ICON,
            ...style,
          } as React.CSSProperties
        }
        className={cn("group/sidebar-wrapper flex min-h-svh w-full has-[>div]:bg-transparent", className)}
        {...props}
      >
        {children}
      </div>
    </SidebarContext.Provider>
  )
}

export function useSidebar() {
  const context = React.useContext(SidebarContext)
  if (!context) throw new Error("useSidebar must be used within a SidebarProvider.")
  return context
}

export function Sidebar({
  side = "left",
  variant = "sidebar",
  collapsible = "offcanvas",
  topOffset = 0,
  className,
  style,
  children,
  ...props
}: React.ComponentProps<"div"> & {
  side?: "left" | "right"
  variant?: "sidebar" | "floating" | "inset"
  collapsible?: "offcanvas" | "icon" | "none"
  topOffset?: number
}) {
  const { isMobile, state, openMobile, setOpenMobile } = useSidebar()
  const offsetStyle = {
    top: `${topOffset}px`,
    height: `calc(100svh - ${topOffset}px)`,
  }

  if (collapsible === "none") {
    return (
      <div
        data-sidebar="sidebar"
        className={cn("flex h-full w-[--sidebar-width] flex-col bg-[#11131d] text-white", className)}
        {...props}
      >
        {children}
      </div>
    )
  }

  if (isMobile) {
    return (
      <DialogPrimitive.Root open={openMobile} onOpenChange={setOpenMobile}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay className="fixed inset-x-0 bottom-0 z-50 bg-black/80" style={offsetStyle} />
          <DialogPrimitive.Content
            data-sidebar="sidebar"
            data-mobile="true"
            className="fixed z-50 flex w-[--sidebar-width] flex-col bg-[#11131d] p-0 text-white shadow-xl outline-none data-[side=left]:left-0 data-[side=right]:right-0"
            data-side={side}
            style={{ ...offsetStyle, "--sidebar-width": "18rem" } as React.CSSProperties}
          >
            <DialogPrimitive.Title className="sr-only">Prep navigation</DialogPrimitive.Title>
            {children}
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>
    )
  }

  return (
    <div
      data-state={state}
      data-collapsible={state === "collapsed" ? collapsible : ""}
      data-variant={variant}
      data-side={side}
      className="group peer hidden text-white md:block"
    >
      <div
        className={cn(
          "relative w-[--sidebar-width] bg-transparent transition-[width] duration-200 ease-linear",
          "group-data-[collapsible=offcanvas]:w-0",
          "group-data-[collapsible=icon]:w-[--sidebar-width-icon]",
          variant === "floating" || variant === "inset"
            ? "group-data-[collapsible=icon]:w-[calc(var(--sidebar-width-icon)+theme(spacing.4))]"
            : "group-data-[collapsible=icon]:w-[--sidebar-width-icon]",
        )}
      />
      <div
        className={cn(
          "fixed z-10 hidden w-[--sidebar-width] transition-[left,right,width] duration-200 ease-linear md:flex",
          side === "left"
            ? "left-0 group-data-[collapsible=offcanvas]:left-[calc(var(--sidebar-width)*-1)]"
            : "right-0 group-data-[collapsible=offcanvas]:right-[calc(var(--sidebar-width)*-1)]",
          variant === "floating" || variant === "inset"
            ? "p-2 group-data-[collapsible=icon]:w-[calc(var(--sidebar-width-icon)+theme(spacing.4)+2px)]"
            : "group-data-[collapsible=icon]:w-[--sidebar-width-icon] group-data-[side=left]:border-r group-data-[side=right]:border-l",
          className,
        )}
        style={{ ...offsetStyle, ...style }}
        {...props}
      >
        <div data-sidebar="sidebar" className="flex h-full w-full flex-col bg-[#11131d] group-data-[variant=floating]:rounded-xl group-data-[variant=floating]:border group-data-[variant=floating]:border-white/10 group-data-[variant=floating]:shadow-xl">
          {children}
        </div>
      </div>
    </div>
  )
}

export function SidebarTrigger({ className, onClick, ...props }: React.ComponentProps<"button">) {
  const { toggleSidebar } = useSidebar()
  return (
    <button
      data-sidebar="trigger"
      type="button"
      aria-label="Toggle prep navigation"
      className={cn("inline-flex size-8 items-center justify-center rounded-md text-white/60 transition-colors hover:bg-white/10 hover:text-white", className)}
      onClick={(event) => {
        onClick?.(event)
        toggleSidebar()
      }}
      {...props}
    >
      <PanelLeft size={16} aria-hidden="true" />
      <span className="sr-only">Toggle sidebar</span>
    </button>
  )
}

export function SidebarRail({ className, ...props }: React.ComponentProps<"button">) {
  const { toggleSidebar } = useSidebar()
  return <button data-sidebar="rail" aria-label="Toggle prep navigation" className={cn("absolute inset-y-0 z-20 hidden w-4 -translate-x-1/2 transition-all after:absolute after:inset-y-0 after:left-1/2 after:w-px hover:after:bg-white/20 md:flex", className)} onClick={toggleSidebar} {...props} />
}

export function SidebarInset({ className, ...props }: React.ComponentProps<"main">) {
  return <main data-sidebar="inset" className={cn("relative flex w-full flex-1 flex-col bg-transparent", className)} {...props} />
}

export function SidebarHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-sidebar="header" className={cn("flex flex-col gap-2 p-3", className)} {...props} />
}

export function SidebarFooter({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-sidebar="footer" className={cn("flex flex-col gap-2 p-3", className)} {...props} />
}

export function SidebarContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-sidebar="content" className={cn("flex min-h-0 flex-1 flex-col gap-2 overflow-auto", className)} {...props} />
}

export function SidebarGroup({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-sidebar="group" className={cn("relative flex w-full min-w-0 flex-col p-2", className)} {...props} />
}

export function SidebarGroupLabel({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-sidebar="group-label" className={cn("flex h-8 shrink-0 items-center rounded-md px-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-white/40", className)} {...props} />
}

export function SidebarGroupContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-sidebar="group-content" className={cn("w-full text-sm", className)} {...props} />
}

export function SidebarMenu({ className, ...props }: React.ComponentProps<"ul">) {
  return <ul data-sidebar="menu" className={cn("flex w-full min-w-0 flex-col gap-1", className)} {...props} />
}

export function SidebarMenuItem({ className, ...props }: React.ComponentProps<"li">) {
  return <li data-sidebar="menu-item" className={cn("group/menu-item relative", className)} {...props} />
}

export function SidebarMenuButton({
  asChild = false,
  isActive = false,
  className,
  ...props
}: React.ComponentProps<"button"> & { asChild?: boolean; isActive?: boolean }) {
  const Comp = asChild ? Slot : "button"
  return <Comp data-sidebar="menu-button" data-active={isActive} className={cn("flex w-full items-center gap-2 overflow-hidden rounded-md px-2.5 py-2 text-left text-[12px] text-white/60 outline-none transition-colors hover:bg-white/[0.06] hover:text-white data-[active=true]:bg-[rgba(249,115,22,0.13)] data-[active=true]:text-[#ff9a52]", className)} {...props} />
}

export function SidebarMenuBadge({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-sidebar="menu-badge" className={cn("pointer-events-none absolute right-2 top-2 flex min-w-5 items-center justify-center rounded px-1 text-[10px] text-white/40", className)} {...props} />
}

export function SidebarMenuAction({ className, ...props }: React.ComponentProps<"button">) {
  return <button data-sidebar="menu-action" className={cn("absolute right-1 top-1.5 flex size-6 items-center justify-center rounded text-white/40 opacity-0 transition-opacity hover:bg-white/10 hover:text-white group-hover/menu-item:opacity-100", className)} {...props} />
}

export function SidebarSeparator({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-sidebar="separator" className={cn("mx-3 h-px bg-white/10", className)} {...props} />
}
