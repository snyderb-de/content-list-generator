# Windows Deploy Layout

Use this folder as a copy-ready deployment bundle for Windows users.

## Folder Structure

```text
deploy\windows\
  desktop\
    content-list-generator.bat
  scripts\
    content-list-gen\
      content_list_generator.py
      content_list_core.py
      copy_email_files.py
```

## Copy Targets On User Machine

Copy `deploy\windows\desktop\content-list-generator.bat` to:

`C:\Users\{user}\Desktop\content-list-generator.bat`

Copy `deploy\windows\scripts\content-list-gen\` to:

`C:\Users\{user}\scripts\content-list-gen\`

## Why A Subfolder Under Scripts

The app needs multiple script files, so they are grouped under:

`C:\Users\{user}\scripts\content-list-gen\`

This keeps `%USERPROFILE%\scripts` clean and avoids filename collisions.
