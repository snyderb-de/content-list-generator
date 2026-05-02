# Clone Compare — Single-Drive Mode: Investigation Guide

## What it does

Single-drive mode lets the user scan Drive A, eject it, insert Drive B, then continue —
for machines with only one USB/drive port at a time.

---

## Architecture

### Go backend (`app.go`)

```
StartCloneCompare(opts) — opts.DriveB == ""
  │
  ├─ scan-a: runScanWithContext(ctx, DriveA, ...)
  │   └─ progress ticker emits clone:progress {phase:"scan-a", ...} every 250ms
  │
  ├─ driveB == "" → create cloneDriveBCh (chan string, buf 1)
  │   emit clone:awaiting-drive-b
  │   BLOCK on select { ch receive | ctx.Done }
  │
  ├─ ResumeCloneWithDriveB(path) → sends path to cloneDriveBCh → unblocks
  │
  ├─ scan-b: runScanWithContext(ctx, driveB, ...)
  │   └─ progress ticker emits clone:progress {phase:"scan-b", ...} every 250ms
  │
  └─ diff: compareScanOutputs → emits clone:progress {phase:"diff"} + clone:diff-row
           → emits clone:done | clone:error | clone:canceled
```

**Key state on `App` struct:**
| Field | Lifecycle |
|---|---|
| `cloneCancel func()` | set at scan start, nil'd after each phase |
| `cloneDriveBCh chan string` | non-nil only while blocked waiting for Drive B |

**Cancel path:**
`CancelCloneCompare()` → closes `cloneDriveBCh` (goroutine sees `ok=false` → emits `clone:canceled`) then calls `cloneCancel()`.

---

### Frontend (`CloneCompare.tsx`)

Phase state machine:
```
idle
  └─ start() → running
                 ├─ clone:progress {phase:"scan-a"} → running (scan-a UI)
                 ├─ clone:awaiting-drive-b          → awaiting-drive-b
                 │     └─ resumeWithDriveB()        → running (scan-b UI)
                 ├─ clone:progress {phase:"scan-b"} → running (scan-b UI)
                 ├─ clone:progress {phase:"diff"}   → running (diff UI)
                 ├─ clone:done                      → done
                 ├─ clone:error                     → error
                 └─ clone:canceled                  → canceled
```

Events registered in `start()`, cleaned up in `reset()` and on catch.

---

## Things to investigate

### 1. Drive B prompt never appears

- Check `opts.driveB` is actually empty string when `StartCloneCompare` is called.
  Frontend sends `{ ...opts, driveB: '' }` when `singleDriveMode` is true.
- Check `clone:awaiting-drive-b` is emitted: add `console.log` in the `EventsOn('clone:awaiting-drive-b', ...)` handler.
- Check scan-a didn't error out before reaching the pause block — look for `clone:error` firing instead.

### 2. Continue button does nothing / hangs

- `ResumeCloneWithDriveB(path)` returns an error if `cloneDriveBCh == nil`.
  This means the goroutine is no longer waiting (was canceled, errored, or never reached the pause).
- Check `driveBPath` state is non-empty before Continue is clickable (button disabled if empty).
- Check no prior cancel was called that closed the channel before Resume.

### 3. Cancel during awaiting-drive-b leaves goroutine stuck

- `CancelCloneCompare` closes `cloneDriveBCh` — the goroutine's `select` will hit the closed-channel case (`ok == false`) and emit `clone:canceled` then return.
- If `cloneDriveBCh` was already nil (Resume already consumed the value), the close is skipped — goroutine is in scan-b and `cloneCancel()` will abort it.

### 4. Progress not showing during scans

- Progress ticker is started in `startCloneScanProgressTicker("scan-a")` before `runScanWithContext`.
- Ticker reads `currentProgress()` (global atomic in `scan_progress.go`) every 250ms.
- If `totalFiles == 0` and `totalBytes == 0`, scan is still in counting phase — frontend shows indeterminate bar.
- If scan completes instantly (tiny drive / cached FS), ticker may fire 0 times — that's fine, done event fires.

### 5. Context cancellation races

- Outer `ctx` is created once for scan-a + scan-b. Canceling it aborts whichever scan is active.
- After scan-a completes, if `ctx` is canceled before Drive B is provided, the `select` hits `ctx.Done()` → emits `clone:canceled`. Frontend should show canceled state.
- The ticker goroutine uses its own `context.WithCancel` — independent from scan ctx. `stopTickerX()` blocks until ticker goroutine exits cleanly.

---

## Key files

| File | What to look at |
|---|---|
| `app.go:339` | `StartCloneCompare` — full backend flow |
| `app.go:338` | `startCloneScanProgressTicker` — progress emitter |
| `app.go:477` | `ResumeCloneWithDriveB` — channel send |
| `app.go:486` | `CancelCloneCompare` — channel close + ctx cancel |
| `app_types.go:102` | `CloneProgressPayload` — all fields emitted |
| `frontend/src/screens/CloneCompare.tsx` | full frontend state machine |
| `scan_progress.go` | `globalProgress` struct, `currentProgress()`, `progressFraction()` |

---

## Quick debug checklist

```
[ ] Single drive mode checkbox checked before starting?
[ ] DriveA path set and valid?
[ ] OutputDir set and writable?
[ ] scan-a completes without error? (watch for clone:error event)
[ ] clone:awaiting-drive-b event fires? (add console.log)
[ ] DriveB path set before clicking Continue?
[ ] ResumeCloneWithDriveB returns without error?
[ ] cloneDriveBCh non-nil at time of Resume? (add log in Go)
[ ] scan-b path different from scan-a output path? (cloneOutputPathForDriveB)
```
