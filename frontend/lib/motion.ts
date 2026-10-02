import type { Transition, Variants } from "framer-motion"

/**
 * Shared motion vocabulary.
 *
 * Every variant here animates only `opacity` and `transform`. Those two are
 * the only properties the compositor can handle without a layout or paint
 * pass, which is what keeps these at 60fps. Animating `height`, `top`,
 * `width` or `box-shadow` would not.
 *
 * Durations/easings mirror the CSS custom properties in globals.css so that
 * CSS-driven and JS-driven motion stay in sync.
 */

export const EASE_OUT = [0.16, 1, 0.3, 1] as const
export const EASE_SPRING = [0.34, 1.56, 0.64, 1] as const

export const DUR = {
  fast: 0.15,
  base: 0.25,
  slow: 0.4,
} as const

export const transition: Transition = {
  duration: DUR.base,
  ease: EASE_OUT,
}

export const springTransition: Transition = {
  type: "spring",
  stiffness: 380,
  damping: 30,
}

/** Standard page/section entrance: rise and fade. */
export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition },
}

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition },
}

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.96 },
  visible: { opacity: 1, scale: 1, transition },
  exit: { opacity: 0, scale: 0.96, transition: { duration: DUR.fast, ease: EASE_OUT } },
}

export const slideInRight: Variants = {
  hidden: { opacity: 0, x: 24 },
  visible: { opacity: 1, x: 0, transition },
  exit: { opacity: 0, x: 24, transition: { duration: DUR.fast, ease: EASE_OUT } },
}

/**
 * Parent for staggered lists.
 *
 * `staggerChildren` is deliberately small and the caller should cap the
 * number of animated children (~8). A 40ms stagger over 50 rows means the
 * last row appears two seconds late, which reads as jank rather than polish.
 */
export function staggerContainer(stagger = 0.04, delay = 0): Variants {
  return {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: { staggerChildren: stagger, delayChildren: delay },
    },
  }
}

/** Child item for `staggerContainer`. */
export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition },
}

/** Props for a one-shot entrance that does not need variants. */
export const entrance = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  transition,
} as const

/** Scroll-triggered reveal. `once` avoids re-animating on every scroll pass. */
export const revealOnScroll = {
  initial: "hidden",
  whileInView: "visible",
  viewport: { once: true, amount: 0.2 },
  variants: fadeUp,
} as const

export const hoverLift = {
  whileHover: { y: -2 },
  whileTap: { y: 0 },
  transition: { duration: DUR.fast, ease: EASE_OUT },
} as const
