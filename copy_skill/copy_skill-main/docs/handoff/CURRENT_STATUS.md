# Current status

Updated: 2026-10-17.

## Current task

- Guide: 2026-10-17-upload-readiness.md. Test-only network stub preserves cache checks; only second candidate attempted. Offline295 passed; production unchanged.
- Prior full1259 passed/1 optional artifact skip; see release guide.
- Verified snapshots feed runner/single download; ID-only argv, per-account profile/port and UA, unsupported proxy blocked. Runtime duration bridge preserves milliseconds without upstream edits; auto media downloads disabled. Cookie login requires fresh self-profile response; CAPTCHA automation blocked. Single script supports current/legacy extractors and size/duration bounds.
- Default config merges local overrides; explicit paths stay isolated. Root installation/verification: docs/VERIFICATION.md.
- Delivery reports default on; report_doc.py owns format. `--check` exits2 while 二/三/六 have TODO. Audit output/复刻视频 since2026-09-19; older folders legacy. Manifests include report_doc.
- `_inventory` counts unique inodes; direct_delivery's 04 hardlinks duplicate 02/03 bytes. Run material-replication with explicit theme/pool-size/business-date; host delete guard is separate from src.

## Capabilities

- `scripts/download_douyin_mediacrawler.py`: selected verified account/`--account-id`; explicit `--cookies` fallback retained. Account route downloaded/decoded30s and registered through formal library API on2026-10-16.

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
- Script references filter heat top 10%/30–300s, not published_at. Completed/nondegraded volume does not prove relevance or freshness.

### Residual defects

1. `expand_keywords` adds a multi-word head as one phrase, never matching under AND semantics.
2. Subject terms do not separate exact brand terms from category aliases.
3. `max_age_days` is one global key; the five-tier freshness policy needs per-category keys.
4. `direct_delivery.main_min_seconds=60` keeps official 35-53 s sources out of `02-主素材`; the profile's
   source-kind rankings stay dead code while real outlet accounts are unlisted; Bilibili serves 360P only.

## Repository evidence

- `third_party/MediaCrawler` is declared in `.gitmodules` but not recorded as a gitlink.
- Repo-root data loss (LF-only launchers) is fixed and guarded:
  `0341c0e`/`aedcdad`/`47143aa` (RUNTIME_SAFETY).

## Next direction

- MC8f583999/Python3.12.8/90 dependencies verified. Robot3 decoded downloads/2 SHA assets: account3,Studio10 candidates/21.85s,legacy/share30s; samples recycled. Gates unchanged, no paid calls/publishing. Evidence: root .local/mediacrawler-live-20261016 and release-regression-20261016; docs/RELEASE_READINESS_20261016.md.
