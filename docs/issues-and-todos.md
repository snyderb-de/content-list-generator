# Issues And TODOs

## Current TODOs

- Decide the final public GitHub repo URL and replace the placeholder link
- Transfer repo ownership or publishing control to `dpa-snyder`
- Decide the final attribution requirement for reuse or redistribution
- Keep polishing both GUIs for non-technical users
- Continue improving folder pickers and long-running progress feedback
- Make packaged releases easier to hand to other people

## Known Rough Edges

- Packaging is still helper-script based, not full installer based
- The Go and Python apps are kept in parity by tests, but they still have separate code paths
- The project docs are still evolving alongside the apps

## Testing Reminder

Before a release:

- run automated checks
- run the smoke test plan
- test content-list output
- test email-copy output
- confirm manifest/report output
