# Visual and motion references

## Open motion extension v002

- Remocn: https://github.com/Remocn/remocn at `7aebcbe6514ed9e54e3a4a6786f83f8425a4a9af`. Unmodified `cloth-reveal`, `mondrian-split`, `parallax-depth` sources in `vendor/remocn/`; MIT license alongside. The integration supplies real media and brand text via children/layers. No upstream sample assets/audio.
- GL Transitions `2.0.0`: https://github.com/gl-transitions/gl-transitions. `FilmBurn` and `CircleOpen` shaders retain their upstream copyright/license headers in the npm distribution; project-level MIT and individual shader notices copied to `licenses/`. Renderer is upstream `gl-transition@2.1.0` with `gl-texture2d@2.1.0`; the project only supplies decoded textures and frame progress.
- PixiJS `8.22.0` and PixiJS Filters `6.1.5`: https://github.com/pixijs/pixijs and https://github.com/pixijs/filters; MIT. Actual `AdjustmentFilter` and `ShockwaveFilter` process decoded video frames. Ticker disabled; time derived solely from video frame. License texts preserved in `licenses/`.
- Exact npm integrity and transitive dependencies are in `../../remotion-composer/package-lock.json`; source/effect inventory in `open-effects-manifest.json`.

This is a project-owned renderer. The original MotionGit package is a visual reference; its packaged player is not modified or redistributed here.

- Hallmark, Nutlope/hallmark, commit `7ec868225c6caa040558c321ee0fefa0e73f83a8`: MIT. Hum and Coral material, palette and composition references. The fixed upstream license is preserved in `../../design/hallmark/LICENSE`. Chinese font assets are supplied per private job, not bundled with this renderer.
- video-shotcraft, Vincentwei1021/video-shotcraft, commit `43bd349a136651865ecfa6ea1cf012f6e957d304`: Apache-2.0, Copyright 2026 Wei Yihao. `card-stack` / `demos/ui-entrance/card-stack/CardStack.tsx` motion grammar is adapted to 3/5 real-media cards on a 1440x1800 canvas. Changes: project props and sources, continuous narration clock, fixed-frame preview semantics, selected-card enlargement, retained entry springs and fan/anticipation timing, project materials and audio events. No upstream music or sampled effects are distributed.
- animated-video, goodnight000/cstack, commit `72c4a9be18c1a7d455ecc3f5a4d4547725970a10`: MIT. Handmade 2D, phrase-cue event timing and logarithmic camera interpolation informed this renderer. The upstream English-only aligner and portrait canvas constants are not used. Chinese timestamps come from the project's ASR.

See `licenses/` for the two newly integrated sources' license texts. The installed skill files remain pinned independently of this renderer. Installation and formula tests do not establish visual approval of a new film.
