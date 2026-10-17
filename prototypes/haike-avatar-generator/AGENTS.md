# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

## Accepted Haike design and scope (2026-10-13)

- Company is 海客科技. Reuse the official logo, orange/yellow brand tokens and native shared navigation copied into src/vendor. The sidebar stays 242px; its five entries are 图文视频、数字人口播、我的作品、发布日历、API设置. Match menu geometry across every route.
- User selected the first redesign on 2026-10-13: ../../docs/ui/component-redesign-20261013/selected-design.png. Use the compact content editor on the left, reference preview on the right, and sticky bottom actions. Keep actual functionality and three avatar templates; reuse buttons, fields, uploads, empty states and native modal dialogs across every route. On narrow viewports the reference preview is a disclosure.
- Sound sources are mutually exclusive. Uploaded audio triggers no TTS; switching source/template preserves assets. Template1/2 posters are layout illustrations, template3 plays an existing real sample, never a newly generated user result.
- This is the actual workbench frontend, backed by /api/studio/*; the new launcher defaults to 14756. Drafts/assets persist on the server; browser IndexedDB only remembers the last avatar project. Paid quotes, budget caps and native queue production are connected. No supplier or customer Key belongs in browser storage.
- Keep original template3 baseline immutable. New parameterized avatar rendering belongs to templates/studio-avatar-v1 with its own version. Graphic uses the native safe_v2 nine-second/three-scene layout.
- Publication is through real CreatorHub receipts: future times, Beijing display, approved final version, owned/authorized sources, title/description/cover and live account checks. Save a draft first, activate only on explicit user confirmation. Unknown results reuse the original idempotency key; partial cancellation stays visible and recoverable.
- No real paid call or external publish during automated validation. Local outputs remain pending user review. Unconfirmed procurement prices must block the relevant capability.

## Accepted unified avatar flow (2026-10-13)

- Use one「选择模板」dialog for basic3 and ADu styles, preserving script, voice/audio, portrait and uploaded materials. The professional manual editor remains an optional deeper entry.
- User materials have must/prefer/reference intent and an explicit usage/AI-analysis rights checkbox. AI previews are content suggestions, with no invented seconds. Final timing uses original ASR sentence timestamps; display subtitle wrapping must not become the storyboard clock.
- New gpt-6-luna / gpt-image-2 features are currently merchant-sponsored trials, with customer charge0 and unknown procurement cost. Keep supplier credentials exclusively in ignored backend configuration; do not package them for customers. Native TTS/avatar/ASR keep their separate commercial quotes and caps.
- Douyin/MediaCrawler precedes Pexels. Login and content authorization are visible pauses; explicit skip resumes the original task. Network failure never authorizes image generation. Image fallback is capped and requires supplier acceptance before enabling it.

## Accepted Haike account voice flow (2026-10-15)

- Keep the five primary entries. As narrowed by the user on 2026-10-15, “更多制作工具” contains only 项目工作台 (`/legacy/projects`) and 素材库 (`/material-library`). Modernize the preserved project workflow thoroughly; other old tools need no entry.
- “海客配音中心” opens from API settings as a URL-backed dialog (`?panel=audio`); `voice` opens a detail and `audio_job` restores the original operation. Its first level contains recording upload/clone and voice selection; default voice, rate, explicit paid audition and image association belong in details.
- Use only the user's Haike Key. Public voices share their definitions; private voices and per-voice rates/images come from the current account. Never show supplier credentials or keep keys/voice preferences in browser storage.
- Label the settings ASR capability card “海客ASR” with the description “音频识别与字幕提取”. Settings hints use Haike service language, without vendor or implementation names; retain readiness, actual fallback conditions, estimates and billing limits. Internal provider/model identifiers and execution rules remain authoritative.
- Separate `modelId` (the Haike capability) from `voiceId` (the account-visible voice). Public and private voices may use different Haike capabilities. Legacy drafts whose `voiceId` was a capability require an explicit voice selection; uploaded audio still bypasses TTS.
- Both cloning and audition require a quote, an explicit budget confirmation and the quote's durable operation ID. Unknown submission results only query the same operation. Associated gateway images must be explicitly adopted, validated, then uploaded as local Studio portrait assets before production.
- `haike/internal-tts` is an ordinary selectable voice capability. For `mode=internal_local`, show “内部备用服务，按每次报价确认”; no cloud balance or relay-authentication claim. Show provider/model and estimate-only billing notes on internal quote confirmations. Supplier configuration belongs only to a separate local administration app, never ordinary settings or project forms.

## Accepted defaults and progress (2026-10-17)

- The canonical new-workbench entry is `/avatar`, including the root page and launcher. Show the current account preset and its editor directly on that page. New untouched tasks inherit it; explicit parameters win. Restored drafts and submitted jobs keep their original parameters; adopting today's preset from an old draft creates new content.
- Task cards/counts follow existing queue and publication receipts: creation, publication waiting, submitted awaiting verification, and verified completion stay distinct. Interface refresh does not prove an executor is online. Show final media, cover, publishing copy and per-account platform results without restarting work or inventing settled fees. Daily scheduling and new control systems remain outside this change.
- Account rows and the material summary show green for a normal check within eight hours, yellow for unconfirmed/failed/stale evidence, and red for explicit login-required evidence until a new check changes it. Use persisted scope checks and times across restarts and normal Cookie rotation; historical green never approves execution. Keep material and publication separate; search and publishing still verify live login before acting. Manual login checks verify accounts; automatic refresh reads history only. An individual failure leaves other results visible.
