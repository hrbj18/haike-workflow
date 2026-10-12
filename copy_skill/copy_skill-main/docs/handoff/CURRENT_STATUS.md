# Current status

Updated: 2026-10-12.

## Current task

- `docs/tasks/2026-10-12-monorepo.md`: default config merges ignored local overrides; explicit paths stay isolated. Install/release from workspace root; verification in root docs/VERIFICATION.md.
- Report delivery remains opt-in/default true across five publish paths; report_doc.py owns format and scripts/build_report_doc.py is its wrapper.
- Gate: `--check <交付目录>` exits 2 until 二/三/六 lose the TODO marker; batch audit
  `--all --root output/复刻视频 --since 2026-09-19` exits 2 while any in-scope delivery is short.
  Effective date 2026-09-19; 34 earlier folders report `legacy`.
- `_inventory` dedups by `(st_dev, st_ino)`: under `direct_delivery` the `04-原片` entries are hard links
  to `02/03`, so summing `st_size` double-counted them (`9.19AI巨头冲刺IPO` read 200.1 MiB, not 100.2).
- 9.19 five are gate-green: 74.2 / 100.2 / 96.0 / 83.5 / 76.8 MiB. Their manifests predate the wiring
  (no `report_doc` block); confirm it on the next batch.
- Command: `material-replication run --theme <T> --pool-size <N> --business-date <YYYY-MM-DD>`;
  disable the host bulk-delete guard first (`src/` never reads it).

## Capabilities

- `scripts/download_douyin_mediacrawler.py`: 2026-09-24 real 1080p download/decode passed; workspace Cookie or `--cookies`. Videohub runbook: 下载抖音视频.md.

- Collect Douyin/Bilibili account and keyword metadata; expose heat and delivery rankings on preserved
  raw interaction evidence.
- Bounded OCR/ASR enrichment; dated packages, material manifests, `00-素材目录.json`, `00-交付说明.md`
  + `汇报文档.md`, OpenMontage snapshots.
- Themed replication publishing an atomic `MM.DD<主题>复刻视频/` folder; downloads resolve via
  `CompositeMediaResolver` (Douyin / yt-dlp / bilibili).
- Shipped config enables `sources: ["bilibili"]`, `direct_delivery`, `relevance_gate`, `visual_verify`,
  `max_age_days=90`, the per-theme `theme_keywords`/`theme_subject_terms` and the episode research pack.

## Product limitations

- Autonomous daily-news discovery is not a reliable product (2026-09-03: zero strict cards).
- Douyin is attention evidence, not factual evidence.
- Script-reference picking ignores freshness: `script_candidate_pool()` filters on heat top 10% and
  30-300 s only; `replication_script.py` never reads `published_at`. Three 9.19 references were off-topic
  (a 2023 English song, a 2025 cabin-SoC explainer).
- The 2026-09-14 batch proved `status=done` + `degraded=false` + correct volume can still mean
  off-topic or stale content.

### Residual defects

1. `expand_keywords` adds a multi-word head as one phrase, never matching under AND semantics.
2. Subject terms do not separate exact brand terms from category aliases.
3. `max_age_days` is one global key; the five-tier freshness policy needs per-category keys.
4. `direct_delivery.main_min_seconds=60` keeps official 35-53 s sources out of `02-主素材`; the profile's
   source-kind rankings stay dead code while real outlet accounts are unlisted; Bilibili serves 360P only.

## Repository evidence

- `third_party/MediaCrawler` is declared in `.gitmodules` but not recorded as a gitlink.
- Full suite 2026-09-20: 1128 tests, 0 failures.
- Repo-root data loss (LF-only launchers, 10 files, 3x) is fixed and guarded:
  `0341c0e`/`aedcdad`/`47143aa` (RUNTIME_SAFETY).

## Next direction

- Confirm the next batch's `清单.json` carries a `report_doc` block, then settle defect 4's three open
  items. Keep news discovery frozen.
