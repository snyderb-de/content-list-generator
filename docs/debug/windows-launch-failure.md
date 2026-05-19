# Windows GUI .exe — Silent Launch Failure

**Status:** OPEN
**Affected versions:** v0.2.0, v0.2.1
**Reporter:** Bryan (Win11, AMD Ryzen 9 5950X — x64)

## Symptom

Downloading `content-list-generator-gui-windows-amd64.exe` from the GitHub Release and double-clicking it produces:

1. SmartScreen warning ("Microsoft Defender SmartScreen prevented an unrecognized app from starting")
2. User clicks "More info" → "Run anyway"
3. `.exe` appears to run — no error dialog, no console window
4. Nothing else happens — no GUI window, no tray icon, no log file
5. Process exits silently

Running from `cmd.exe` produces no stdout/stderr either.

## What's NOT the issue

- ✅ **WebView2 runtime** — confirmed installed (`webview2 installer reports "already on system"`). Earlier `Get-Package` queries returned empty but that was a query-target issue, not a missing-runtime issue.
- ✅ **Architecture mismatch** — host is AMD Ryzen 5950X (x64), binary is windows-amd64. Match.
- ✅ **Antivirus quarantine** — not flagged in AV logs.
- ✅ **SmartScreen block** — user explicitly unblocked + "Run anyway".
- ✅ **`-webview2 download` build flag (v0.2.1)** — added in PR #18 but is the Wails 2.12 default. No-op. Didn't change behavior.

## What we know about the build

- Built in GitHub Actions `windows-latest` runner
- Wails CLI v2.12.0
- Go 1.26.0
- Node 20 LTS for frontend build
- Workflow: `.github/workflows/release.yml` job `windows-gui`
- Both amd64 and arm64 .exe produced; user tried amd64
- .exe file properties show version `1.0.0` (Wails default — irrelevant to launch)
- File size expected ~22 MB

## Hypotheses to test

### H1 — Missing dependency (DLL)
Wails apps need WebView2 (confirmed present). Could need VC++ Redistributable.
- Event Viewer → Application logs may show "Faulting module" pointing at missing DLL
- Try installing latest VC++ Redist: https://aka.ms/vs/17/release/vc_redist.x64.exe

### H2 — Bundled frontend/dist is empty or malformed
The Wails .exe embeds `frontend/dist/` via `//go:embed all:frontend/dist`. If CI built the frontend incorrectly or the embed is broken, app exits during init.
- Check CI logs of v0.2.1 windows-gui job: confirm `npm run build` succeeded and dist/ has files
- Compare file size of v0.2.1 vs v0.2.0 amd64 .exe — should be similar
- Repro locally on a Windows host with `wails build -platform windows/amd64 -clean` and compare

### H3 — Wails 2.12 + Go 1.26 binding-gen incompatibility
CI log showed `flag provided but not defined: -gui` during binding generation, called non-fatal. Could be producing a half-baked binary.
- Try building with Wails 2.13.x or Go 1.23.x (downgrade one to isolate)

### H4 — Architecture/PE corruption from CI artifact upload
Artifact gets uploaded, downloaded, then attached to release — possible corruption mid-pipe.
- Compare `Get-FileHash` of the local .exe to a fresh re-download
- Rebuild locally on Windows host (per `docs/windows-build-checklist.md`) — does the local-built .exe launch?

## Diagnostics to collect

Run on the affected Windows machine and paste outputs below.

### D1 — Event Viewer entries
1. Win+R → `eventvwr` → Enter
2. Windows Logs → Application
3. Last hour, filter for "Error" level, sources "Application Error" / ".NET Runtime" / "Windows Error Reporting"
4. Open the relevant entry. Paste:
   - Event ID
   - Source
   - Description (full text, especially "Faulting module name" and "Exception code")

```
<paste here>
```

### D2 — PowerShell capture + exit code
```powershell
cd <download folder>
& ".\content-list-generator-gui-windows-amd64.exe" 2>&1 | Out-File wails-stderr.log
$LASTEXITCODE
Get-Content wails-stderr.log
```

Paste output:
```
exit code: <number>
stderr/stdout:
<paste>
```

Exit code decoder:
- `0` — clean exit (most concerning — means app thinks it ran fine)
- `-1073741819` (0xc0000005) — access violation
- `-1073741515` (0xc0000135) — missing DLL
- `-1073740771` (0xc000009d) — bad image (corruption)
- Other negative — Windows status code, look up

### D3 — File integrity
```powershell
Get-FileHash content-list-generator-gui-windows-amd64.exe
Get-Item content-list-generator-gui-windows-amd64.exe | Select-Object Length, LastWriteTime
```
Paste:
```
SHA256: <hash>
Size: <bytes>
```

### D4 — Process-level monitoring (advanced, if above is empty)
Install Sysinternals Process Monitor:
https://learn.microsoft.com/en-us/sysinternals/downloads/procmon

1. Open `procmon.exe`
2. Filter: Process Name → is → content-list-generator-gui-windows-amd64.exe → Include
3. Reset filter, then double-click the .exe
4. Stop capture after 5 seconds
5. File → Save → save as `.PML`
6. Look for the last few entries before process termination

## Workarounds for users while investigating

- **Use the portable .zip instead** — `content-list-generator-windows-portable.zip` confirmed working
- **Don't recommend the .exe externally** until this is resolved

## Resolution log

| Date | Action | Outcome |
|---|---|---|
| 2026-05-19 | v0.2.0 released | Initial bug discovered — silent fail |
| 2026-05-19 | PR #18 added `-webview2 download` flag → v0.2.1 | No change (flag is default) |
| | | |

## Related TODO entries

- 📌 P0 — verify v0.2.x builds work on target machines (this issue)
- Backlog — Windows code-signing for Wails .exe (would skip SmartScreen but not the launch failure)
