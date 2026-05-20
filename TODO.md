# TODO

## Recently Shipped

### v0.2.2 (2026-05-20)
- ✅ **Windows GUI silent launch failure FIXED** — root cause was `isGUIContext()` had no Windows production detection; binary fell through to Bubble Tea TUI which tried to open console input with no console attached → exit code 1, `open CONIN$: The handle is invalid.`
- ✅ Fix detects PE Subsystem field via `debug/pe`: Wails `-H windowsgui` → Subsystem=2 (GUI) routes to Wails; default `go build` → Subsystem=3 (Console) routes to TUI. Platform-agnostic, no env-var sniffing.
- ✅ Project dashboard rebuilt with dates-formatter style (IBM Plex, navy-orange, light/dark, live GitHub stats, downloads grid, roadmap)
- ✅ User manual stub at `project-dashboard/user-manual.html`
- ✅ Counting display improvements in scan progress (ContentList.tsx)

### v0.2.0 – v0.2.1 (2026-05-18 – 2026-05-19)
- ✅ Wails Windows GUI build via CI (no Windows host required)
- ✅ App icon set (svg + icns + multi-resolution ico)
- ✅ CI matrix: macOS, Linux, Windows GUI amd64/arm64, Windows portable, Windows python source
- ✅ Tag-driven publish pipeline (push `v*` tag → GitHub Release auto-attached)
- ✅ Python deploy strategy: exact-pin requirements.txt + runtime drift banner
- ✅ Dependabot tuned (no major-bump noise; security alerts still flow)
- ✅ Docs: `docs/github-setup-guide.md`, `docs/windows-build-checklist.md`, `docs/debug/windows-launch-failure.md`

## Active (priority order)

### 📌 P0 — verify v0.2.2 Windows .exe launches
- Download `content-list-generator-gui-windows-amd64.exe` from v0.2.2 release on the Win11 host
- Confirm GUI window opens (no silent exit)
- Run a small scan end-to-end → CSV written correctly
- If green: close `docs/debug/windows-launch-failure.md` as FIXED + remove the warning banner from dashboard downloads card

### P0 — verify remaining v0.2.x builds on target machines
- macOS `.app` from `content-list-generator-gui-darwin-universal.zip` — verify launch (Gatekeeper bypass per user manual)
- Linux binary smoke test
- Windows portable `.zip` — confirmed working
- Python source bundle on a managed Windows host — verify .bat launchers + drift banner behavior

### P0 — write real user manual content
- Replace stub at `project-dashboard/user-manual.html` with full content
- Cover scan modes, hash algorithms, CSV chunking, email-copy flow, clone-compare verdicts, troubleshooting, FAQ
- Include platform-specific install + first-run guidance
- Cross-link from README

### P0 — capture GUI screenshots
- macOS `.app` (Wails GUI)
- Wails Windows GUI (now unblocked by v0.2.2 fix)
- Python customtkinter GUI (managed Windows path)
- Bubble Tea TUI (Linux/Mac terminal)
- Add to README hero + user manual + dashboard hero
- Suggested resolution: 1600×1000 PNG, light-mode default

### P0 — enable GitHub Pages for the dashboard
- Repo Settings → Pages → Source: Deploy from a branch → main → /project-dashboard
- Dashboard URL: `https://snyderb-de.github.io/content-list-generator/`
- Add the URL to README hero + repo About sidebar

### P1 — finish dependabot sweep (all 4 PRs now CI-green)
- #1 setup-go 5→6 ✅ CI green
- #3 checkout 4→6 ✅ CI green
- #5 setup-node 4→6 ✅ CI green
- #7 download-artifact 4→8 ✅ CI green
- Merge each via web UI (each touches `.github/workflows/release.yml`; gh CLI lacks `workflow` scope)
- Or run `gh auth refresh -s workflow --hostname github.com` in a real terminal to unblock CLI merging

### P2 — release hygiene followups
- `releases/windows-python/` ships both the `.zip` AND its loose `.py`/`.bat`/`.md` files. Tighten `publish_github_release.sh` to upload only the zip.
- Re-enable PR approval rule (or accept solo-dev posture) — branch protection currently allows direct merge without review
- Bump Node version pin in workflow from 20 → 24 LTS (Node 20 GH Actions deprecation 2026-06-02)

### P3 — feature/test work
- Test large scan (>300k rows) — verify CSV chunking visible in GUI progress
- Test Phase 7 (soft compare) — Newark drives CON-P74THY / CON-M4EM1V with soft compare on; verdict should be `Metadata Clone`, 1,831 metadata-only diffs

## Backlog (no order)
- Windows code-signing for Wails .exe (silence SmartScreen)
- macOS code-signing + Apple Developer ID notarization (silence Gatekeeper)
- Auto-update mechanism for Wails app
- Decide the final public GitHub repo URL and replace placeholder links in `python/content_list_generator.py`
- Transfer repo ownership or publishing control to `dpa-snyder`
- Decide the final project license (evaluate GPL vs MIT vs Apache)
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
- Latest release: **v0.2.2** (2026-05-20) — 18 artifacts attached.
