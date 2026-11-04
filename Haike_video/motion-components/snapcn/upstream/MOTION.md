# snap-cn Motion Direction

The canonical motion direction for **templates** and branded transition presentations. Locked in against a reference product demo roughly ~44s long (the reference timings below are given from the start of that clip). All templates follow these principles; branded presentations on top of `TransitionSeries` implement the named moves from here.

> The timings below have been converted to frames @30fps (our standard).

## The essence of the direction

Shots are not **cut** — a **camera drives through** them. The scene lives in a shared "world," and a virtual camera dollies/pans/cranes across it. Transitions are synchronous (the outgoing and incoming elements ride ONE camera curve, not two independent cross-fades). Camera speed is emphasized with **motion blur**, and sharpness = "in focus / settled."

Five pillars:

1. **The camera is a first-class layer.** A transform wrapper (`scale` + `translateX/Y`) around the scene; children render in world coordinates.
2. **Motion blur is mandatory on fast camera moves.** Directional blur proportional to camera velocity — this is exactly what makes the type zoom feel premium.
3. **Fast travel → strong ease-out into readability.** The camera flies, then brakes hard and "lands." After the stop, text holds for a long time (readability beats pacing).
4. **Progressive disclosure.** Wordmarks type themselves out, inputs use a typewriter effect, numbers count up (34→39→71%), cards fill in line by line, then status checkmarks.
5. **The cursor is an actor.** A scripted cursor travels along a bezier, "clicks," and only after the click does the input/action start.

## Camera model (new core primitive)

`Camera` is a wrapper that drives the parent's transform via spring/interpolate:

```tsx
export function Camera({ x = 0, y = 0, scale = 1, blur = "auto", children }: CameraProps) {
  return (
    <AbsoluteFill style={{ transform: `translate(${x}px, ${y}px) scale(${scale})`, transformOrigin: "center" }}>
      {children}
    </AbsoluteFill>
  );
}
```

- The camera target (`x`, `y`, `scale`) is set by the scene/transition; intermediate values are interpolated with `spring`.
- `blur: "auto"` derives motion blur from the per-frame camera velocity (Δposition between frames).
- Motion-blur implementation: `@remotion/motion-blur` (`<CameraMotionBlur>` / `<Trail>`) — a NEW dependency, pinned to `4.0.473`. Fallback — a directional-blur layer driven by velocity.

## Global motion tokens

| Token | Value | Where |
|---|---|---|
| Camera travel | 8–14f | fast dolly/crane move |
| Settle (arrival) | 10–16f | braking into sharpness |
| Text hold | 30–45f | pause for readability |
| Spring settle | `{ damping: 18, stiffness: 140 }` | camera/card landing |
| Spring pop (card) | `{ damping: 12, stiffness: 180 }` | element scale-in |
| Stagger | 3–6f | cascades of icons/rows |
| Pulse along a wire | 18–24f | data impulse along a connector |

Camera easing: `interpolate(..., { easing: Easing.out(Easing.cubic), extrapolateLeft: "clamp", extrapolateRight: "clamp" })` for the travel; `spring` for the arrival (slight overshoot).

## Named moves (branded presentations)

### 1. `camera-type-flythrough` — zoom drive-through across text
The signature move for hero typography ("By just talking to it", "Talk to your data", "Build with it"). Ref: t≈0.9–3.3s.

- **Start:** the camera is "inside" the text — a single word fills the frame, `scale ≈ 6–10`, noticeable directional motion blur.
- **Travel:** a horizontal pan along the line "as if reading" (translateX), 10–14f, blur at peak velocity.
- **Arrival:** `scale → 1`, `Easing.out(cubic)` + spring settle, blur fades out → the line is sharp, centered. Hold 30–45f.
- Apply to words where the meaning is in the text itself; don't overuse (1 per scene).

### 2. `card-extrude` — a card extrudes out of its parent
Ref: t≈5.5–6.5s (a red card grows out of the command island).

- The card appears **from the edge** of the parent element (command bar/island), with `transformOrigin` at the attachment point.
- A short connector line "extends" along with it (`width` or `stroke-dashoffset` 0→full over 8–10f).
- The card: `spring pop` scale 0.6→1 from the attachment point; a slight settle bounce.

### 3. `wire-constellation` — icons and wires to a card
"Icons slide out of cards" + converging wires. Ref: t≈6.5–9s.

- Platform icons cascade in as a column (`staggered`, stagger 4f, `spring pop` + `soft-blur-in`).
- From each icon a **bezier wire is drawn** to the central product card: `stroke-dashoffset` full→0 over 16–22f, curving toward the center.
- Colored **data impulses** run along the wires (an animated gradient offset along the path, 18–24f, repeating).
- The card's wordmark unfolds progressively (e.g., `Acme`→`Acme MCP`), per character/per word.
- Wires are thin, `theme.accent` at low opacity — **no glow**.

### 4. `camera-crane-up` — camera rise + card entrance
A favorite transition. A synchronous vertical crane. Ref: t≈9.5–12s.

- The outgoing scene travels **up** and out of frame (camera `translateY` upward), while the incoming one (heading + card) **cranes in from below** — both on one curve, simultaneously.
- Soft vertical motion blur during the move → sharpness on arrival (spring settle).
- The arriving card: `spring pop` scale-in + a shadow bloom (the shadow grows `0→full` over 10f, not a glow).
- Variant `camera-crane-down` — mirrored, for going back.

### 5. `kinetic-word-swap` — swapping large words (black↔white acts)
Ref: t≈37–41s ("Talk to your data." on black → "Build with it." on white).

- A large word holds the center; the key word in `theme.accent`.
- An act change = background inversion (`interpolateColors` background black↔white over 12f) synchronized with the word swap.
- The word enters via `mask-reveal-up` / `per-character-rise`; on black — a soft glyph highlight (a sweep across the letter, NOT a glow blob).

### 6. `typewriter-pill` — typing a URL/command inside a pill
Ref: t≈42–43s (e.g., `acme.example/mcp`).

- A pill with monospaced text, `typewriter` with a blinking caret, ~2 frames/character.
- A thin accent outline on the pill; on a dark background — a delicate `shimmer-sweep` along the outline (a single pass).

## Relation to the templates architecture

- These moves are the implementation of the "branded presentations on top of `TransitionSeries`" decision. `camera-crane-up`, `camera-type-flythrough`, `kinetic-word-swap` become presentations; `card-extrude`, `wire-constellation`, `typewriter-pill` are scene-level moves.
- **New infrastructure (one-time, for the first template):** the `Camera` core primitive, the `@remotion/motion-blur@4.0.473` dependency, and the set of easing tokens above as a shared module.
- **Background:** the reference soft blue↔red aurora wash is allowed ONLY as a very subtle backdrop; `mesh-gradient-bg` is forbidden (see the anti-slop rules). No glows — depth comes from blur and shadow, not glow.

## "In the spirit of the reference" checklist for every template

- [ ] At least one camera move (flythrough / crane), not just a fade cut.
- [ ] Motion blur on fast camera moves.
- [ ] Outgoing and incoming are synchronous (one curve).
- [ ] Text stays readable after the move (hold 30–45f).
- [ ] Progressive disclosure (typing / count-up / cards filling in).
- [ ] A cursor-actor wherever there is UI interaction.
- [ ] No glow blobs and no mesh gradients.
