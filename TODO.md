# TODO

## Active
- **📌 TOP PRIORITY — Windows Wails GUI build** — Wails cannot cross-compile WebView2, so build must run on Windows. Run `wails build -platform windows/amd64 -o content-list-generator-gui.exe` on a Windows host (or GitHub Actions `windows-latest`). Output goes to `releases/windows-go/content-list-generator-gui-windows-amd64.exe`. Without this, Windows users have no native GUI — only the Python bundles.
- **Test large scan** — verify >300k rows triggers CSV chunking visible in GUI progress
- **Test Phase 7 (soft compare)** — run Newark drives (CON-P74THY / CON-M4EM1V) with soft compare checkbox enabled; verify verdict = Metadata Clone, 1,831 metadata-only diffs

## Backlog
- Windows code-signing for Wails exe
- Auto-update mechanism for Wails app
- Decide the final public GitHub repo URL and replace placeholder links
- Transfer repo ownership or publishing control to `dpa-snyder`
- Decide the final project license
- Evaluate GPL as a release candidate and make the final license decision
- Decide the final attribution requirement for reuse or redistribution
- Smooth ETA behavior for very large scans with long-tail large files
- Investigate MacBook touchpad scrolling in the Python GUI and add proper macOS trackpad scroll handling if possible
- Decide whether release bundles stay portable-only or move toward installer-style distribution
- Package the Linux release from a Linux build host
- Live diff table virtual scrolling (cap at 5000 rows currently — DOM choke risk at 100k+)
- Phase 7 soft compare: extend to same-path hash mismatches (not just path-renamed PDFs)
