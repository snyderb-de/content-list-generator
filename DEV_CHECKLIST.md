# Wails Dev Checklist

## App Shell

- [y] A1 Sidebar nav — all 4 items visible, active highlight works
- [n] A2 Dark mode toggle — switches theme, persists on reload - no toggle exists.
- [y] A3 Window min-size (try shrinking to ~800×600)

## Content List

- [y] C1 Browse buttons open native folder dialog
- [n] C2 Output filename auto-populates from source folder name - it says it will auto populate but it doesn't
- [y] C3 All toggles work (XLSX, preserve zeros, delete CSV — sub-options disable when XLSX off)
- [y] C4 Hash selector has all 4 options
- [y] C5 Start Scan → progress view shows (phase badge, bar, counters, current file)
- C5 note: first scan erroed b/c file name didn't have .csv, this should be automatic and abstracted from the user, also i want a progress bar
- [y] C6 Stop button cancels, returns to form with "Scan was stopped"
- [y] C7 Done view shows stats, top extensions tables, open output button

## Email Copy

- [y] E1 Browse source + dest
- [y] E2 Start → progress spinner
- Email copy has no stop button and no progress bar
- [y] E3 Done view shows manifest path, open dest button

## Clone Compare

- [y] CC1 Can't start with same folder for A and B (client-side guard)
- CC1... this works but it doenst tell you until you scan, it should tell you after drive 2 is chosen.
- [y] CC2 3-phase indicator steps through scan-a → scan-b → diff
- [y] CC3 Live diff table populates during diff phase
- [y] CC4 Done view shows all 6 diff stat categories
- [y] CC5 Open Diff CSV + Open Report buttons work

## About

- [y] AB1 Version shown
- [y] AB2 GitHub link opens in browser (not WebView) - there is no link
