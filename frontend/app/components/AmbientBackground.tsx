/**
 * The layer every glass surface in the app refracts.
 *
 * Rendered once in the root layout, fixed and non-interactive. Three large
 * blurred orbs on slow opposing drifts; a faint grain overlay on top to stop
 * the gradients banding on 8-bit displays.
 *
 * Server component on purpose — it is pure CSS animation, so shipping it as
 * a client component would cost hydration for nothing.
 */
export function AmbientBackground() {
  return (
    <div className="ambient-root" aria-hidden="true">
      <div className="ambient-orb ambient-orb-1" />
      <div className="ambient-orb ambient-orb-2" />
      <div className="ambient-orb ambient-orb-3" />
      <div className="ambient-grain" />
    </div>
  )
}
