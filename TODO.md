# TODO

## Active
- **App icon** — create 1024×1024 PNG, convert to `build/darwin/icon.icns`, rebuild releases
- **Test large scan** — verify >300k rows triggers CSV chunking visible in GUI progress
- **Windows build** — run `wails build -platform windows/amd64` on Windows host; copy `.exe` to `releases/windows-go/`
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
