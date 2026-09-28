# UI/UX Revamp Plan

**Status:** proposed plan — not implemented.
**Scope:** all 16 pages + navigation, frontend only. No backend changes.

---

## 1. Audit: why it actually looks basic

This isn't a matter of taste or missing effort. There's a specific architectural
reason the UI is flat, and it has to be fixed before *any* amount of visual work
will stick.

| Finding | Evidence | Consequence |
|---|---|---|
| **501 inline `style={{}}` objects across 18 files** | `grep style={{` | This is the core problem — see below |
| Tailwind installed + configured, **unused in every app page** | Zero `className="p-4"`-style usage in `app/**` | Paying the config cost, getting none of the benefit |
| **`framer-motion@12` installed, zero imports** | No `from "framer-motion"` anywhere in `app/**` | ~50KB shipped for nothing. Also explains "no animations at all" |
| `lucide-react` installed, used in 2 files | Only `dropdown-menu.tsx`, `toast.tsx` | No icons anywhere in the actual product |
| 8 shadcn/ui components exist, **none imported by any page** | `components/ui/*` orphaned | Dead code |
| Fonts loaded **twice** | `@import` in `globals.css` **and** `next/font` in `layout.tsx` | Duplicate network requests, FOUT risk. Already flagged in `CODEBASE_REVIEW.md` |
| Only 3 utility classes total | `.card-surface`, `.btn-primary`, `.btn-secondary` | Everything else is bespoke inline |
| Flat `#090a0f` background, no depth layers | `globals.css` | **Glassmorphism would be invisible on this** — see §3.1 |

### 1.1 The root cause

**Inline styles cannot express `:hover`, `:focus-visible`, `:active`, media
queries, keyframes, or state transitions.** That is a hard limitation of the
`style` attribute, not an oversight.

So the current UI is *structurally incapable* of having:
- hover feedback beyond what's hardcoded per-element
- focus rings that meet accessibility requirements consistently
- responsive layout (there are no breakpoints anywhere — only two `className="hidden md:flex"` escapes in `Navbar`)
- entrance/exit animation
- reduced-motion support

This is why it reads as "basic and minimal with no animations." Adding animation
on top of 501 inline style objects means touching all 501. **The migration to a
real styling layer isn't prep work for the revamp — it *is* the revamp.**

---

## 2. Design direction

Positioning: this is a **hiring platform that makes high-stakes decisions about
people**. The visual language should feel *precise and trustworthy*, not playful.
Glassmorphism here should read as "instrument panel," not "iOS widget."

Three principles:

1. **Depth communicates hierarchy, not decoration.** Elevation maps to
   importance: ambient background → content surface → interactive card → modal.
   A glass panel should mean "this floats above," consistently.
2. **Motion explains state change.** Every animation answers "what just
   happened?" — a stage advancing, a match score resolving, a verdict arriving.
   Nothing moves purely to look alive.
3. **Data stays legible.** Scores, verdicts, and pipeline stages must be
   readable at a glance. Glass never goes between the user and a number.

### 2.1 Keeping what works

The existing foundation is not bad — it's just thin. Retained:
- The **dark, near-black base** (`#090a0f`) — correct for a focus tool
- **Orange as the single accent** (`#f97316`) — distinctive, not another blue SaaS
- **JetBrains Mono for data/labels** — the monospace-for-metadata convention is
  genuinely good and reinforces the "instrument" read
- The semantic color set (success/warning/error) — sound

This is an *amplification*, not a rebrand.

---

## 3. The design system

### 3.1 Layer model — the prerequisite for glassmorphism

**The most common glassmorphism failure is applying `backdrop-filter` over a flat
background.** Blurring a solid color produces the same solid color, so the glass
is invisible and you've paid GPU cost for nothing. The current `#090a0f` flat
background would do exactly this.

So the ambient layer comes first:

```
z-0   Base            near-black
z-1   Ambient mesh    2–3 large, very-low-opacity blurred color orbs (orange /
                      deep indigo), slowly drifting. This is what the glass
                      actually refracts.
z-2   Grain           ~2% noise overlay — kills gradient banding on dark UIs
z-10  Content surface cards, panels (the glass)
z-40  Sticky chrome   navbar — heavier blur, higher opacity
z-50  Overlays        modals, toasts, dropdowns
```

### 3.2 Token extension

Additive to the existing `:root` — nothing removed:

```css
/* Elevation-aware glass */
--glass-bg-low:    rgba(255,255,255,0.03);
--glass-bg-mid:    rgba(255,255,255,0.055);
--glass-bg-high:   rgba(255,255,255,0.08);
--glass-blur-sm:   8px;
--glass-blur-md:   16px;
--glass-blur-lg:   24px;

/* Light catching the top edge — what sells the "pane of glass" read */
--glass-highlight: inset 0 1px 0 rgba(255,255,255,0.08);
--glass-shadow:    0 8px 32px rgba(0,0,0,0.4);

/* Accent glows, for focus and success states */
--glow-primary:    0 0 24px rgba(249,115,22,0.25);
--glow-success:    0 0 24px rgba(34,197,94,0.2);

/* Motion — a real scale, not ad-hoc ms values */
--ease-out:        cubic-bezier(0.16, 1, 0.3, 1);     /* entrances */
--ease-spring:     cubic-bezier(0.34, 1.56, 0.64, 1); /* playful, sparingly */
--dur-fast:        150ms;
--dur-base:        250ms;
--dur-slow:        400ms;

/* Type scale — currently every size is an arbitrary inline number */
--text-xs: 11px;  --text-sm: 13px;  --text-base: 15px;
--text-lg: 18px;  --text-xl: 24px;  --text-2xl: 32px; --text-3xl: 44px;

/* Spacing scale — 4px base */
--space-1: 4px; --space-2: 8px;  --space-3: 12px; --space-4: 16px;
--space-6: 24px; --space-8: 32px; --space-12: 48px; --space-16: 64px;
```

### 3.3 The glass surface

```css
.glass {
  background: var(--glass-bg-mid);
  backdrop-filter: blur(var(--glass-blur-md)) saturate(150%);
  -webkit-backdrop-filter: blur(var(--glass-blur-md)) saturate(150%);
  border: 1px solid var(--color-border);
  border-radius: 14px;
  box-shadow: var(--glass-highlight), var(--glass-shadow);
}
```

`saturate(150%)` is the detail most implementations miss — it makes colors
behind the glass bloom slightly, which is what real frosted glass does. Without
it, glass looks like gray plastic.

**Interactive glass** gets a gradient sheen that sweeps on hover, and lifts
`translateY(-2px)`.

### 3.4 Component library to build

Replacing per-page bespoke markup:

| Component | Replaces | Notes |
|---|---|---|
| `<GlassCard elevation>` | `.card-surface` + ~40 inline variants | `low`/`mid`/`high` |
| `<Button variant size loading>` | `.btn-primary`/`.btn-secondary` + inline overrides | `primary`/`secondary`/`ghost`/`danger` |
| `<Input>` `<Textarea>` `<Select>` | ~30 duplicated inline field styles | One focus-ring treatment everywhere |
| `<StatusPill status>` | `.status-tag-*` | Now with a dot indicator + glow |
| `<ScoreRing value>` | Plain `8.2/10` text | Animated SVG arc — makes scores feel earned |
| `<StageTimeline stages current>` | 3 separate hand-rolled steppers | `jobs`, `interview`, `round` all rebuild this today |
| `<EmptyState icon title action>` | ~8 bare `<p>No X yet.</p>` | Currently the weakest moments in the UI |
| `<Skeleton>` | ~12 `<p>Loading...</p>` | Biggest perceived-performance win available |
| `<Alert variant>` | ~15 duplicated error/success divs | Identical markup copy-pasted everywhere |
| `<PageHeader eyebrow title description>` | Repeated on all 16 pages | |
| `<Toast>` | — (doesn't exist) | `components/ui/toast.tsx` already there, unused |

### 3.5 Icons

`lucide-react` is installed and unused. Icons go in: nav items, empty states,
status pills, stage timelines, buttons. Low effort, disproportionate impact on
"basic" perception.

---

## 4. Motion system

### 4.1 Division of labor

- **CSS transitions** — hover, focus, active. Cheap, no JS.
- **Framer Motion** — orchestrated entrances, list stagger, layout shifts,
  route transitions, shared-element score reveals.

### 4.2 The patterns

| Pattern | Where | Detail |
|---|---|---|
| Page entrance | Every route | `opacity 0→1`, `y 12→0`, 250ms, `--ease-out` |
| List stagger | Jobs, applications, pipeline | 40ms per child, capped at ~8 so long lists don't crawl |
| Card hover | All interactive cards | `translateY(-2px)` + border brighten + sheen sweep |
| Score count-up | Match scores, verdicts | Number tweens + ring arc draws. Makes a score feel computed |
| Stage advance | Application pipeline | `layoutId` shared element slides the active marker |
| Skeleton shimmer | All loading states | Replaces every `Loading...` |
| Modal | Dialogs | Scale `0.96→1` + backdrop blur fade-in |
| Toast | Notifications | Slide + fade from top-right |
| Ambient drift | Background orbs | 20s+ loop, `transform` only |

### 4.3 Non-negotiable constraints

1. **Animate only `transform` and `opacity`.** These are GPU-composited. Animating
   `width`/`height`/`top`/`blur` forces layout/paint per frame and will jank —
   especially layered over `backdrop-filter`.
2. **`prefers-reduced-motion` globally**, not per-component:
   ```css
   @media (prefers-reduced-motion: reduce) {
     *, *::before, *::after {
       animation-duration: 0.01ms !important;
       transition-duration: 0.01ms !important;
       scroll-behavior: auto !important;
     }
   }
   ```
   Framer Motion gets the matching `useReducedMotion()` hook.
3. **Nothing blocks content.** Animations are progressive enhancement; text is
   readable if JS fails.

---

## 5. Accessibility & performance guardrails

Glassmorphism has two well-known failure modes. Both get addressed up front
rather than discovered later.

### 5.1 Contrast

Translucent surfaces make contrast *variable* — text can pass over a dark region
and fail over a bright orb. Mitigations:

- Body text sits on `--glass-bg-mid` or higher, never on the ambient layer
- Ambient orbs capped at very low opacity so worst-case contrast stays ≥ 4.5:1
- Verify every text/surface pairing against WCAG AA at the worst-case background
- **`prefers-reduced-transparency`** → swap glass for solid `--color-bg-muted`

### 5.2 Performance

`backdrop-filter` is GPU-expensive and **compounds when layers stack**.

- Cap at **~8 simultaneous blurred surfaces** per viewport
- Never nest `backdrop-filter` inside `backdrop-filter`
- Lists use solid surfaces; only containers get glass
- Ambient orbs are CSS gradients, not images
- Target: 60fps on mid-tier hardware, verified before sign-off

### 5.3 Focus

The existing 1px focus outline is weak. New treatment: 2px accent ring +
`--glow-primary`, applied through `:focus-visible` — visible for keyboard users,
absent for mouse users.

---

## 6. Migration strategy

Two rules that make this safe:

1. **Foundation first, then pages.** The system has to exist before pages migrate,
   or we get 16 bespoke interpretations again.
2. **Page-by-page, `npm run typecheck` green at every step.** No big-bang rewrite.
   Each page is independently revertable.

### Phase 1 — Foundation *(no visual change yet)*

- Extend tokens in `globals.css`
- Remove the duplicate font `@import` (keeps `next/font`) — fixes a real perf bug
- Ambient background + grain layer
- Glass utilities, reduced-motion block, focus-visible treatment
- Build the component library (§3.4)
- Motion primitives + variants module

**Exit:** components render in isolation; nothing else touched; typecheck green.

### Phase 2 — Global chrome

Navbar → glass, mobile drawer animation, page-transition wrapper, toast host.
Touches every page at once, so it lands early for compounding effect.

### Phase 3 — Candidate surfaces *(highest traffic)*

`page.tsx` (landing), `login`, `register`, `jobs`, `jobs/[id]`, `applications`,
`profile`, `referrals`.

Landing page gets the most attention — hero with layered depth, animated pipeline
visualization, scroll-triggered section reveals, glass audience cards.

### Phase 4 — Recruiter surfaces

`org`, `org/postings/[id]`, `org/analytics`. Denser, more data-heavy: animated
funnel bars, glass pipeline columns, score rings on candidate matches.

### Phase 5 — Legacy sandbox

`interview`, `round/[id]`, `result`, `dashboard`, `dashboard/[id]`. Lower
priority (explicitly labeled sandbox), but must not look abandoned next to the
revamped product.

### Phase 6 — Polish

Responsive audit at 360/768/1024/1440, WCAG AA contrast pass, 60fps verification,
reduced-motion pass, cross-browser check (Safari `-webkit-backdrop-filter`).

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| **501 inline styles = large diff** | Page-by-page, typecheck green each step, each independently revertable |
| **`backdrop-filter` jank on low-end GPUs** | Hard cap on blurred surfaces; no nesting; profile before sign-off |
| **Contrast regressions from translucency** | Worst-case-background audit; `prefers-reduced-transparency` fallback |
| **Over-animation making it feel slow** | Durations ≤400ms; motion must explain a state change or it gets cut |
| **Safari `backdrop-filter` inconsistency** | `-webkit-` prefixes; explicit Safari check in Phase 6 |
| **Scope creep into backend** | Frontend-only. Zero API/contract changes. 176 backend tests must stay untouched |

### Honest limitations

- **There is no frontend test suite** (no Playwright/Vitest — see `TESTING.md`).
  Verification is `npm run typecheck` + manual review. A visual-regression
  suite would be the right tool here and doesn't exist; I'm not going to claim
  coverage I can't provide.
- **`next build` can't run in a network-restricted environment** (Google Fonts
  fetched at build time — `SETUP.md`). Removing the duplicate `@import` in
  Phase 1 helps but doesn't fix it; `next/font/local` would, and that's a
  separate decision.

---

## 8. What I need from you

Four questions, because getting these wrong means redoing work:

1. **Accent color** — keep orange, or shift? Orange is distinctive and currently
   consistent; changing it touches every token.
2. **Intensity** — *subtle* (restrained glass, professional) or *bold* (heavy
   blur, prominent glows, more ambient color)? My read is that a hiring product
   should lean restrained, but it's your call.
3. **Tailwind or CSS modules?** Tailwind is installed and configured but unused.
   I'd use it — it makes hover/focus/responsive variants trivial, which is
   exactly what inline styles can't do. Alternative is expanding `globals.css`
   utilities. Either works; mixing them would be worse than either.
4. **Phase order** — foundation first is non-negotiable, but after that I can
   prioritize the landing page for immediate visual impact, or the
   candidate/recruiter flows for real usage value.

Default if you'd rather I just proceed: **keep orange, restrained intensity,
Tailwind, landing page first.**
