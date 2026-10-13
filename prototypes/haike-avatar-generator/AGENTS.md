# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

## Accepted Haike design and scope (2026-10-13)

- Company is 海客科技. Reuse the official logo, orange/yellow brand tokens and native shared navigation copied into src/vendor. The sidebar stays 242px; its five entries are 图文视频、数字人口播、我的作品、发布日历、API设置. Match menu geometry across every route.
- User selected the first redesign on 2026-10-13: ../../docs/ui/component-redesign-20261013/selected-design.png. Use the compact content editor on the left, reference preview on the right, and sticky bottom actions. Keep actual functionality and three avatar templates; reuse buttons, fields, uploads, empty states and native modal dialogs across every route. On narrow viewports the reference preview is a disclosure.
- Sound sources are mutually exclusive. Uploaded audio triggers no TTS; switching source/template preserves assets. Template1/2 posters are layout illustrations, template3 plays an existing real sample, never a newly generated user result.
- This is now the frontend of the actual workbench at 14754, backed by /api/studio/*. Drafts/assets persist on the server; browser IndexedDB only remembers the last avatar project. Paid quotes, budget caps and native queue production are connected. No supplier or customer Key belongs in browser storage.
- Keep original template3 baseline immutable. New parameterized avatar rendering belongs to templates/studio-avatar-v1 with its own version. Graphic uses the native safe_v2 nine-second/three-scene layout.
- Publication is through real CreatorHub receipts: future times, Beijing display, approved final version, owned/authorized sources, title/description/cover and live account checks. Save a draft first, activate only on explicit user confirmation. Unknown results reuse the original idempotency key; partial cancellation stays visible and recoverable.
- No real paid call or external publish during automated validation. Local outputs remain pending user review. Unconfirmed procurement prices must block the relevant capability.

## Accepted unified avatar flow (2026-10-13)

- Use one「选择模板」dialog for basic3 and ADu styles, preserving script, voice/audio, portrait and uploaded materials. The professional manual editor remains an optional deeper entry.
- User materials have must/prefer/reference intent and an explicit usage/AI-analysis rights checkbox. AI previews are content suggestions, with no invented seconds. Final timing uses original ASR sentence timestamps; display subtitle wrapping must not become the storyboard clock.
- New gpt-6-luna / gpt-image-2 features are currently merchant-sponsored trials, with customer charge0 and unknown procurement cost. Keep supplier credentials exclusively in ignored backend configuration; do not package them for customers. Native TTS/avatar/ASR keep their separate commercial quotes and caps.
- Douyin/MediaCrawler precedes Pexels. Login and content authorization are visible pauses; explicit skip resumes the original task. Network failure never authorizes image generation. Image fallback is capped and requires supplier acceptance before enabling it.
