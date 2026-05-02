# Manual Testing Checklist

Run `./run-go-gui.sh` before starting. Check each item and note any failures.

---

## Content List Screen

### Basic scan
- [ ] Browse to a source folder — path populates
- [ ] Browse to an output folder — path populates
- [ ] Output filename auto-suggests based on source folder name
- [ ] Start Scan button disabled until source + output filled

### Progress
- [ ] Progress bar animates during counting phase
- [ ] Progress bar fills during scanning phase
- [ ] Files / Data / Speed / ETA / Elapsed stat blocks update live
- [ ] Current file path scrolls in the current-file box
- [ ] Stop button cancels scan and shows canceled state

### Options
- [ ] Hash algo selector — try BLAKE3, SHA-256, Off
- [ ] Exclude Hidden toggle — hidden files disappear from count
- [ ] Exclude System toggle
- [ ] Exclude Extensions — enter `.tmp,.log`, verify those files excluded
- [ ] Create XLSX — output includes `.xlsx` file
- [ ] Preserve Zeros — zero-byte files included when on
- [ ] Delete CSV after XLSX — CSV removed when XLSX created

### Results screen
- [ ] Files / Dirs / Bytes / Elapsed stats correct
- [ ] Top extensions by count + size shown
- [ ] Open Output button opens the CSV/XLSX in Finder
- [ ] Open Report button opens the `*-report.txt`
- [ ] "New Scan" resets to form

### Large scan (>300k rows)
- [ ] Scan a folder with >300k files
- [ ] Progress shows chunked CSV parts (e.g. `part-001`, `part-002`)
- [ ] All parts present in output folder after completion

---

## Email Copy Screen

- [ ] Browse source and destination — paths populate
- [ ] Start Copy disabled until both filled
- [ ] Progress updates during copy
- [ ] Result shows files copied count
- [ ] Manifest CSV created at destination
- [ ] Open Destination button opens folder in Finder

---

## Clone Compare Screen

### Form
- [ ] 1st Drive Browse works
- [ ] 2nd Drive Browse works (two-drive mode)
- [ ] Same-drive error shown when Drive A = Drive B
- [ ] Output folder Browse works
- [ ] Hash algo selector (no "Off" option — verify it's hidden)
- [ ] Single drive mode checkbox hides Drive B field
- [ ] Soft compare checkbox shows/hides explanation text

### Phase step indicator (during scan)
- [ ] Step 1 (Scanning 1st Drive): box 1 = **blue ▶**, boxes 2+3 = **orange ○**
- [ ] Step 2 (Scanning 2nd Drive): box 1 = **green ✓**, box 2 = **blue ▶**, box 3 = **orange ○**
- [ ] Step 3 (Comparing Drives): boxes 1+2 = **green ✓**, box 3 = **blue ▶**

### Speed graph (during scan)
- [ ] Graph appears after first nonzero speed tick
- [ ] Y axis shows labeled speed ticks (e.g. 10 MB/s, 100 MB/s)
- [ ] X axis shows time marks (5s / 15s / 30s intervals)
- [ ] Current speed dashed line tracks the Speed stat box value
- [ ] Graph fills card width
- [ ] No rogue dot at top-left before data arrives

### Two-drive compare — Exact Clone
- [ ] Scan `/Volumes/F10/clone-a` vs `/Volumes/F10/clone-b`
- [ ] Verdict badge: **✓ EXACT CLONE** (green)
- [ ] Exact matches count correct, all other counters zero
- [ ] System paths excluded > 0

### Two-drive compare — Not a Clone
- [ ] Scan two drives with genuine differences
- [ ] Verdict badge: **✗ NOT A CLONE** (red)
- [ ] Alarming rows section appears (red border) with missing/extra rows
- [ ] Other differences in separate card below
- [ ] Open Diff CSV / Open Report buttons work

### Soft compare — Metadata Clone (Newark drives)
- [ ] Scan CON-P74THY vs CON-M4EM1V with **Soft compare checked**
- [ ] Verdict badge: **≈ METADATA CLONE** (amber)
- [ ] Metadata-only (PDF IDs) stat block shows ~1,831
- [ ] Missing (no match) = 0, Extra (no match) = 0
- [ ] Diff table shows teal `metadata-only (PDF document IDs)` badges
- [ ] Diff rows show both Drive A and Drive B paths

### Not a Clone without soft compare (Newark drives)
- [ ] Same drives with **Soft compare unchecked**
- [ ] Verdict = **✗ NOT A CLONE**
- [ ] Missing (no match) = 1,831, Extra (no match) = 1,831
- [ ] Metadata-only stat block not shown

### Single drive mode
- [ ] Check "Single drive mode" — Drive B field hidden
- [ ] Start Compare with Drive A only
- [ ] After scan A: screen switches to "Swap Drives" prompt
- [ ] Drive B folder picker appears
- [ ] Continue button triggers scan B + compare
- [ ] Cancel during await-drive-b stops correctly
- [ ] Speed graph shows Drive A / Drive B split line after swap

### Cancel
- [ ] Cancel during scan-a emits canceled state
- [ ] Cancel during scan-b emits canceled state
- [ ] Cancel during diff emits canceled state
- [ ] "New Compare" resets form cleanly after cancel

---

## Settings persistence

- [ ] Change hash algo in Content List, close and reopen — setting retained
- [ ] Change XLSX/hidden/system toggles — retained across restart

---

## Dark mode

- [ ] Click theme toggle in sidebar — cycles light → dark → system
- [ ] Dark mode: all cards, text, badges readable
- [ ] Speed graph gradient visible in dark mode
- [ ] Verdict badges readable in dark mode

---

## Windows build (requires Windows host)

- [ ] `wails build -platform windows/amd64` completes without error
- [ ] `.exe` launches on Windows
- [ ] Content List scan produces CSV on Windows paths
- [ ] Clone Compare runs on Windows drives
