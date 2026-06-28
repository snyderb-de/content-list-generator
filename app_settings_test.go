package main

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func isolateUserConfig(t *testing.T) {
	t.Helper()

	configRoot := t.TempDir()
	switch runtime.GOOS {
	case "darwin":
		t.Setenv("HOME", configRoot)
	case "windows":
		t.Setenv("APPDATA", configRoot)
	default:
		t.Setenv("XDG_CONFIG_HOME", configRoot)
		t.Setenv("HOME", configRoot)
	}
}

func TestSaveSettingsDoesNotPersistAgencyFieldValues(t *testing.T) {
	isolateUserConfig(t)

	app := newApp(filepath.Join(t.TempDir(), "source"))
	app.SaveSettings(ScanOptions{
		HashAlgorithm:  "sha256",
		ExcludeHidden:  true,
		ExcludeSystem:  true,
		CreateXLSX:     true,
		PreserveZeros:  true,
		DeleteCSV:      true,
		ExcludedExts:   "tmp,log",
		AgencyTemplate: true,
		ReleaseFolder:  `\\server\share\Content List Generator`,
		AgencyFields: AgencyTemplateFields{
			RG:               "1325",
			SG:               "987",
			Series:           "654",
			RCSeries:         "GAR-014",
			DeptOrganization: "Department of State",
			Location:         "Old shared drive",
			MaterialType:     "Paper",
			Comments:         "Do not carry this forward",
			RecordLevel:      "Record-Level-Should-Not-Persist",
		},
	})

	defaults := app.GetScanDefaults()
	if !defaults.AgencyTemplate {
		t.Fatalf("expected agency template mode preference to persist")
	}
	if defaults.ReleaseFolder != `\\server\share\Content List Generator` {
		t.Fatalf("expected release folder to persist, got %q", defaults.ReleaseFolder)
	}
	assertAgencyFieldsFresh(t, defaults.AgencyFields)

	settingsPath, err := app.settingsPath()
	if err != nil {
		t.Fatalf("settings path: %v", err)
	}
	settingsBytes, err := os.ReadFile(settingsPath)
	if err != nil {
		t.Fatalf("read settings: %v", err)
	}
	settingsText := string(settingsBytes)
	for _, leaked := range []string{"GAR-014", "1325", "987", "654", "Department of State", "Old shared drive", "Do not carry this forward", "Paper", "Record-Level-Should-Not-Persist"} {
		if strings.Contains(settingsText, leaked) {
			t.Fatalf("settings file leaked agency field value %q: %s", leaked, settingsText)
		}
	}
}

func TestGetScanDefaultsUsesDefaultReleaseFolder(t *testing.T) {
	isolateUserConfig(t)

	app := newApp(filepath.Join(t.TempDir(), "source"))

	defaults := app.GetScanDefaults()
	if defaults.ReleaseFolder != `X:\Apps` {
		t.Fatalf("expected default release folder to be X:\\Apps, got %q", defaults.ReleaseFolder)
	}
}

func TestGetScanDefaultsIgnoresLegacySavedAgencyFieldValues(t *testing.T) {
	isolateUserConfig(t)

	app := newApp(filepath.Join(t.TempDir(), "source"))
	settingsPath, err := app.settingsPath()
	if err != nil {
		t.Fatalf("settings path: %v", err)
	}
	if err := os.MkdirAll(filepath.Dir(settingsPath), 0o755); err != nil {
		t.Fatalf("mkdir settings dir: %v", err)
	}
	if err := os.WriteFile(settingsPath, []byte(`{
  "hashAlgorithm": "sha1",
  "excludeHidden": true,
  "excludeSystem": true,
  "createXLSX": true,
  "preserveZeros": true,
  "deleteCSV": true,
  "agencyTemplate": true,
  "releaseFolder": "\\\\server\\share\\Content List Generator",
  "agencyFields": {
    "rg": "1325",
    "sg": "987",
    "series": "654",
    "rcSeries": "GAR-014",
    "deptOrganization": "Department of State",
    "location": "Old shared drive",
    "materialType": "Paper",
    "comments": "Do not carry this forward",
    "recordLevel": "Record-Level-Should-Not-Persist"
  }
}`), 0o644); err != nil {
		t.Fatalf("write legacy settings: %v", err)
	}

	defaults := app.GetScanDefaults()
	if !defaults.AgencyTemplate {
		t.Fatalf("expected agency template mode preference to persist")
	}
	if defaults.HashAlgorithm != "sha1" {
		t.Fatalf("expected non-agency setting to persist, got %q", defaults.HashAlgorithm)
	}
	if defaults.ReleaseFolder != `\\server\share\Content List Generator` {
		t.Fatalf("expected release folder to persist, got %q", defaults.ReleaseFolder)
	}
	assertAgencyFieldsFresh(t, defaults.AgencyFields)
}

func TestSaveReleaseFolderPersistsWithoutAgencyValues(t *testing.T) {
	isolateUserConfig(t)

	app := newApp(filepath.Join(t.TempDir(), "source"))
	if err := app.SaveReleaseFolder(`\\server\share\Content List Generator`); err != nil {
		t.Fatalf("save release folder: %v", err)
	}

	defaults := app.GetScanDefaults()
	if defaults.ReleaseFolder != `\\server\share\Content List Generator` {
		t.Fatalf("expected release folder to persist, got %q", defaults.ReleaseFolder)
	}
	assertAgencyFieldsFresh(t, defaults.AgencyFields)
}

func assertAgencyFieldsFresh(t *testing.T, fields AgencyTemplateFields) {
	t.Helper()

	if fields.RCSeries != "" {
		t.Fatalf("expected RC Series to be fresh, got %q", fields.RCSeries)
	}
	if fields.RG != "" || fields.SG != "" || fields.Series != "" || fields.DeptOrganization != "" || fields.Location != "" || fields.Comments != "" {
		t.Fatalf("expected agency constants to be blank, got %#v", fields)
	}
	if fields.MaterialType != "Born Digital" {
		t.Fatalf("expected default material type, got %q", fields.MaterialType)
	}
	if fields.RecordLevel != "Item" {
		t.Fatalf("expected default record level, got %q", fields.RecordLevel)
	}
}
