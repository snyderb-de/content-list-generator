# Wails GUI Rewrite Plan

Replacing `gui_fyne.go` with a Wails v2 app (React + Go). TUI (`main.go`) stays untouched.
Targets: macOS (arm64 + amd64), Windows (amd64). Linux users → Python/CLI.

## Screens

1. **Content List** — folder scan to CSV/XLSX
2. **Email Copy** — copy email files to destination
3. **Clone Compare** — scan two drives, diff the CSVs
4. **About** — version, links

## Phases

### Phase 1 — Wails Scaffolding
- `wails init` into repo (Vite + React + TypeScript template)
- Add `wails.io/v2` to `go.mod`
- Create `wails.json` (app name, identifier, window size)
- Move Fyne launch path: `--gui` flag → `wails.Run` instead of `launchGUI`
- Build tag strategy: drop `//go:build gui` on Fyne files, Wails is unconditional on `--gui`
- Update `run-go-gui.sh` → `wails dev`

### Phase 2 — Go Backend (`app.go`)
App struct bound to Wails runtime. All scan logic delegates to existing `core.go` / `scan_*.go` / `clone_compare.go`.

**Bound methods:**
- `PickFolder(title string) string` — native OS folder dialog
- `OpenPath(path string)` — open in Finder / Explorer
- `GetScanDefaults() ScanOptions` — load from settings JSON
- `StartScan(opts ScanOptions) error` — runs in goroutine, emits events
- `CancelScan()`
- `StartEmailCopy(source, dest string) error` — runs in goroutine, emits events
- `StartCloneCompare(opts CloneCompareOptions) error` — runs in goroutine, emits events
- `CancelCloneCompare()`
- `GetAppVersion() string`
- `SaveSettings(opts ScanOptions)` — persist hash algo, toggles, etc.

**Events emitted (frontend listens):**
- `scan:progress` → `ScanProgressPayload`
- `scan:done` → `ScanDonePayload`
- `scan:error` → `string`
- `email:progress` → `EmailProgressPayload`
- `email:done` → `EmailDonePayload`
- `clone:progress` → `CloneProgressPayload`
- `clone:diff-row` → `DiffRowPayload` (emitted per difference found — live stream)
- `clone:done` → `CloneDonePayload`
- `clone:error` → `string`

### Phase 3 — React Frontend

**Design system:** port tokens from `design/go-gui/app_stylesheet_css.txt` into CSS custom properties. Inter font via Google Fonts or bundled. Light/dark mode via `data-theme` attribute on `<html>`.

**App shell:**
- Fixed sidebar (256px) with nav items: Content List, Email Copy, Clone Compare, About
- Dark mode toggle in sidebar footer
- Main content panel, scrollable

**Screen 1 — Content List:**
- Source folder field + Browse button (native dialog)
- Output folder field + Browse button
- Output filename field (auto-suggested)
- Options card: hash algo selector, exclude extensions input, hidden/system toggles, XLSX toggle + sub-options (preserve zeros, delete CSV)
- Start Scan button
- Progress view: animated bar, phase label, files/dirs/bytes counters, ETA, current file, cancel button
- Results view: all stats, top extensions by count/size, filtered samples, open output button

**Screen 2 — Email Copy:**
- Source folder field + Browse button
- Destination folder field + Browse button
- Start Copy button
- Progress view: spinner + counters
- Results view: stats, manifest path, open destination button

**Screen 3 — Clone Compare:**
- Drive A folder + Browse
- Drive B folder + Browse
- Output folder + Browse
- Hash algo selector (must match between both scans)
- Start Compare button
- Progress view: three-phase (scan A → scan B → diff), progress bar per phase
- Live diff table: rows stream in during diff phase, auto-scrolls, columns = diff type / path / sizes / hashes
- Results view: diff stats summary (missing, extra, size mismatches, hash mismatches) + open diff CSV button
- Backend change required: add `diffRow func(DiffRow)` callback to `compareScanOutputs` in `clone_compare.go`; called at each diff write site (3 locations); Wails emits `clone:diff-row` per call

**Screen 4 — About:**
- App name, version
- Description
- GitHub link (opens in browser)
- License

### Phase 4 — Build Pipeline ✅
- ✅ `wails build -platform darwin/universal` (fat binary arm64+amd64) — in `scripts/build_releases.sh`
- ✅ `wails build -platform windows/amd64` — noted in script; requires Windows host (can't cross-compile WebView2)
- ✅ Update `scripts/build_releases.sh` to call `wails build` instead of `go build -tags gui`
- ✅ Remove `fyne.io/fyne/v2` from `go.mod` — done via `go mod tidy` after deleting `gui_fyne.go`
- ✅ Delete Fyne files — `gui_fyne.go` deleted (1827 lines)

### Phase 5 — Polish
- Light/dark mode verified on both platforms
- Error states: scan failure, unwritable output dir, bad path
- Overwrite confirmation dialog (existing output file)
- Settings persist between launches (hash algo, toggle state)
- Window min-size enforced (800×600)
- Test large scan (>300k rows, CSV chunking visible in progress)
- Test email copy, clone compare end-to-end

## File Map

| New file | Purpose |
|---|---|
| `app.go` | Wails App struct + bound methods |
| `app_types.go` | Shared payload structs for frontend binding |
| `wails.json` | Wails project config |
| `frontend/` | Vite + React + TypeScript app |
| `frontend/src/screens/` | ContentList, EmailCopy, CloneCompare, About |
| `frontend/src/components/` | FolderPicker, ProgressBar, ResultsPanel, Sidebar |
| `frontend/src/styles/tokens.css` | Design system CSS vars (light + dark) |

| Removed after validation |
|---|
| `gui_fyne.go` |
| `fyne.io/fyne/v2` from `go.mod` |

## Open Questions / Decisions Deferred
- Windows code-signing for the exe
- Auto-update mechanism (out of scope for now)
- Live diff table row cap: if 100k+ diffs stream in, DOM will choke — need virtual scrolling or a row limit with "X more..." indicator
