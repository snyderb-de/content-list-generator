# TODO

## Recently Shipped (v0.2.0, 2026-05-18)
- ✅ Wails Windows GUI build via CI (no Windows host required)
- ✅ App icon set (svg + icns + multi-resolution ico)
- ✅ CI matrix: macOS, Linux, Windows GUI amd64/arm64, Windows portable, Windows python source
- ✅ Tag-driven publish pipeline (push `v*` tag → GitHub Release auto-attached)
- ✅ Python deploy strategy: exact-pin requirements.txt + runtime drift banner
- ✅ Dependabot tuned (no major-bump noise; security alerts still flow)
- ✅ Docs: `docs/github-setup-guide.md`, `docs/windows-build-checklist.md`

## Active (priority order)

### 📌 P0 — verify v0.2.0 builds actually work on target machines
- Download `content-list-generator-gui-windows-amd64.exe` from release → run on Windows → verify GUI launches, scan works
- Download `content-list-generator-windows-portable.zip` → unzip → run from USB or local → verify
- Open mac `.app` from `content-list-generator-gui-darwin-universal.zip` → verify
- Linux binary smoke test
- Until verified, treat the release as "built" not "shipped"

### P1 — finish dependabot sweep
- 4 GH Actions bumps still open (#1, #3, #5, #7) — `@dependabot rebase` already requested
- After rebase, CI should pass; merge each via web UI (or via gh CLI once `workflow` scope refresh is done)
- To unblock CLI merge: run `gh auth refresh -s workflow --hostname github.com` in real terminal (browser flow)

### P2 — release hygiene followups
- `releases/windows-python/` ships both the .zip AND its loose .py/.bat/.md files → publish script uploads everything. Tighten so only the .zip lands in the GitHub Release.
- Re-enable PR approval rule (or accept solo-dev posture) — branch protection currently allows direct merge without review
- Node.js 20 actions deprecation: GH Actions runners default to Node 24 on 2026-06-02. Bump `setup-*` actions (covered by pending dependabot PRs).

### P3 — feature/test work (pre-existing)
- Test large scan (>300k rows) — verify CSV chunking visible in GUI progress
- Test Phase 7 (soft compare) — Newark drives CON-P74THY / CON-M4EM1V with soft compare on; verdict should be `Metadata Clone`, 1,831 metadata-only diffs

## Backlog (no order)
- Windows code-signing for Wails .exe (silence SmartScreen)
- Auto-update mechanism for Wails app
- Decide the final public GitHub repo URL and replace placeholder links in `python/content_list_generator.py`
- Transfer repo ownership or publishing control to `dpa-snyder`
- Decide the final project license (evaluate GPL)
- Decide the final attribution requirement for reuse or redistribution
- Smooth ETA behavior for very large scans with long-tail large files
- Investigate MacBook touchpad scrolling in the Python GUI; add proper macOS trackpad scroll handling
- Decide whether release bundles stay portable-only or move toward installer-style distribution
- Package the Linux release from a Linux build host
- Live diff table virtual scrolling (cap at 5000 rows currently — DOM choke risk at 100k+)
- Phase 7 soft compare: extend to same-path hash mismatches (not just path-renamed PDFs)
- Un-gitignore `python/tests/` and `*_test.go` so CI actually runs the parity/unit tests instead of skipping
- CI parity check: fail if `python/*.py` and `deploy/windows/scripts/content-list-gen/*.py` drift apart

## Notes
- Branch protection: review-required rule currently OFF (turned off to allow solo-dev merging). Re-enable when adding collaborators.
- Dependabot config: ignores semver-major for gomod + npm. Security advisories still surface separately via Security tab.
- Workflow file path: `.github/workflows/release.yml`. Triggers: tag push, PR to main, manual dispatch.
