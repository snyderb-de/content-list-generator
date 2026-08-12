package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/xuri/excelize/v2"
)

func TestRunScanWritesCSVAndHashes(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	if err := ensureDir(filepath.Join(source, "nested")); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "a.txt"), "hello\n"); err != nil {
		t.Fatalf("write a.txt: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "nested", "b.bin"), "1234567890"); err != nil {
		t.Fatalf("write b.bin: %v", err)
	}
	fixedModified := time.Date(2024, 5, 1, 12, 34, 56, 0, time.Local)
	for _, path := range []string{
		filepath.Join(source, "a.txt"),
		filepath.Join(source, "nested", "b.bin"),
	} {
		if err := os.Chtimes(path, fixedModified, fixedModified); err != nil {
			t.Fatalf("set fixture timestamps: %v", err)
		}
	}

	output := filepath.Join(workspace, "report.csv")
	done, err := runScan(source, output, scanOptions{
		HashAlgorithm: hashAlgorithmSHA256,
		ExcludeHidden: false,
		ExcludeSystem: false,
		ExcludedExts:  map[string]struct{}{},
	})
	if err != nil {
		t.Fatalf("runScan failed: %v", err)
	}
	if done.files != 2 {
		t.Fatalf("expected 2 files, got %d", done.files)
	}
	if filepath.Base(done.outputPath) != "report-001.csv" {
		t.Fatalf("expected first output part to be report-001.csv, got %s", filepath.Base(done.outputPath))
	}
	if done.hashWorkers < 2 {
		t.Fatalf("expected parallel hash workers when hashing is enabled, got %d", done.hashWorkers)
	}
	if done.reportPath == "" {
		t.Fatalf("expected report path to be set")
	}
	reportBytes, err := os.ReadFile(done.reportPath)
	if err != nil {
		t.Fatalf("read report: %v", err)
	}
	reportText := string(reportBytes)
	if !strings.Contains(reportText, "Selected folder: source") {
		t.Fatalf("expected report to include selected folder name, got %q", reportText)
	}
	if !strings.Contains(reportText, "First file in CSV: a.txt") || !strings.Contains(reportText, "Last file in CSV: nested/b.bin") {
		t.Fatalf("expected report to include first/last csv items, got %q", reportText)
	}

	rows := readCSVRows(t, done.outputPath)
	if len(rows) != 3 {
		t.Fatalf("expected 3 rows, got %d", len(rows))
	}
	expectedHeaders := []string{
		"File Name", "Extension", "Size in Bytes", "Size in Human Readable",
		"Path From Root Folder", "Hash Algorithm", "Hash Value",
		"Date Created", "Date Modified",
	}
	assertRowsEqual(t, [][]string{rows[0]}, [][]string{expectedHeaders})
	assertFileTimestampValue(t, rows[1][7], true)
	if rows[1][8] != formatFileTimestamp(fixedModified, true) {
		t.Fatalf("unexpected modified timestamp: %q", rows[1][8])
	}
	if rows[1][0] != "a.txt" {
		t.Fatalf("expected first data row to be a.txt, got %q", rows[1][0])
	}
	if rows[2][4] != "nested/b.bin" {
		t.Fatalf("expected nested relative path, got %q", rows[2][4])
	}
	if rows[1][5] != "SHA-256" || rows[2][5] != "SHA-256" {
		t.Fatalf("expected hash algorithm column to be populated")
	}
	if rows[1][6] == "" || rows[2][6] == "" {
		t.Fatalf("expected hashes to be written")
	}
}

func TestRunScanAppliesFilters(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	if err := ensureDir(filepath.Join(source, ".hidden")); err != nil {
		t.Fatalf("mkdir hidden source: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, ".hidden", "secret.txt"), "secret"); err != nil {
		t.Fatalf("write hidden file: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "visible.log"), "log"); err != nil {
		t.Fatalf("write visible.log: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "Thumbs.db"), "thumbs"); err != nil {
		t.Fatalf("write Thumbs.db: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "keep.txt"), "keep"); err != nil {
		t.Fatalf("write keep.txt: %v", err)
	}

	output := filepath.Join(workspace, "filtered.csv")
	done, err := runScan(source, output, scanOptions{
		HashAlgorithm: hashAlgorithmOff,
		ExcludeHidden: true,
		ExcludeSystem: true,
		ExcludedExts: map[string]struct{}{
			"log": {},
		},
	})
	if err != nil {
		t.Fatalf("runScan failed: %v", err)
	}
	if done.files != 1 {
		t.Fatalf("expected 1 kept file, got %d", done.files)
	}
	if done.filtered != 3 {
		t.Fatalf("expected 3 filtered files/directories, got %d", done.filtered)
	}

	rows := readCSVRows(t, done.outputPath)
	if len(rows) != 2 {
		t.Fatalf("expected header plus one row, got %d rows", len(rows))
	}
	if rows[1][0] != "keep.txt" {
		t.Fatalf("expected keep.txt to remain, got %q", rows[1][0])
	}
}

func TestRunScanCreatesXLSX(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	if err := ensureDir(source); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "report.txt"), "hello"); err != nil {
		t.Fatalf("write report.txt: %v", err)
	}
	fixedModified := time.Date(2024, 5, 1, 12, 34, 56, 0, time.Local)
	if err := os.Chtimes(filepath.Join(source, "report.txt"), fixedModified, fixedModified); err != nil {
		t.Fatalf("set fixture timestamps: %v", err)
	}

	output := filepath.Join(workspace, "report.csv")
	done, err := runScan(source, output, scanOptions{
		CreateXLSX:    true,
		PreserveZeros: true,
		ExcludedExts:  map[string]struct{}{},
	})
	if err != nil {
		t.Fatalf("runScan failed: %v", err)
	}
	if done.xlsxPath == "" {
		t.Fatalf("expected xlsx path to be set")
	}
	if _, err := os.Stat(done.xlsxPath); err != nil {
		t.Fatalf("expected xlsx file to exist: %v", err)
	}

	book, err := excelize.OpenFile(done.xlsxPath)
	if err != nil {
		t.Fatalf("open xlsx: %v", err)
	}
	defer book.Close()

	value, err := book.GetCellValue("Sheet1", "A2")
	if err != nil {
		t.Fatalf("read xlsx cell: %v", err)
	}
	if value != "report.txt" {
		t.Fatalf("expected xlsx to contain report.txt, got %q", value)
	}
	for cell, want := range map[string]string{
		"H1": "Date Created",
		"I1": "Date Modified",
		"I2": formatFileTimestamp(fixedModified, true),
	} {
		value, err := book.GetCellValue("Sheet1", cell)
		if err != nil {
			t.Fatalf("read xlsx cell %s: %v", cell, err)
		}
		if value != want {
			t.Fatalf("unexpected xlsx cell %s: got %q want %q", cell, value, want)
		}
	}
	value, err = book.GetCellValue("Sheet1", "H2")
	if err != nil {
		t.Fatalf("read xlsx cell H2: %v", err)
	}
	assertFileTimestampValue(t, value, true)
}

func TestRunScanDeletesCSVAfterXLSXWhenEnabled(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	if err := ensureDir(source); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "keep.txt"), "hello"); err != nil {
		t.Fatalf("write keep.txt: %v", err)
	}

	output := filepath.Join(workspace, "report.csv")
	done, err := runScan(source, output, scanOptions{
		CreateXLSX:    true,
		PreserveZeros: true,
		DeleteCSV:     true,
		ExcludedExts:  map[string]struct{}{},
	})
	if err != nil {
		t.Fatalf("runScan failed: %v", err)
	}
	if !done.csvDeleted {
		t.Fatalf("expected csvDeleted to be true")
	}
	if _, err := os.Stat(done.outputPath); !os.IsNotExist(err) {
		t.Fatalf("expected csv output to be removed, got err=%v", err)
	}
	if done.xlsxPath == "" {
		t.Fatalf("expected xlsx path to be set")
	}
	if _, err := os.Stat(done.xlsxPath); err != nil {
		t.Fatalf("expected xlsx file to exist: %v", err)
	}
}

func TestRunScanSplitsCSVAndConvertsAllParts(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	if err := ensureDir(source); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}
	for index := 1; index <= 5; index++ {
		name := filepath.Join(source, fmt.Sprintf("file-%d.txt", index))
		if err := writeFixtureFile(name, fmt.Sprintf("value-%d", index)); err != nil {
			t.Fatalf("write fixture file %d: %v", index, err)
		}
	}

	output := filepath.Join(workspace, "report.csv")
	done, err := runScan(source, output, scanOptions{
		CreateXLSX:    true,
		PreserveZeros: true,
		DeleteCSV:     true,
		MaxRowsPerCSV: 2,
		ExcludedExts:  map[string]struct{}{},
	})
	if err != nil {
		t.Fatalf("runScan failed: %v", err)
	}
	if done.csvPartCount != 3 {
		t.Fatalf("expected 3 csv parts, got %d", done.csvPartCount)
	}
	if done.xlsxPartCount != 3 {
		t.Fatalf("expected 3 xlsx parts, got %d", done.xlsxPartCount)
	}
	if !done.csvDeleted {
		t.Fatalf("expected csv parts to be deleted after xlsx conversion")
	}
	if done.maxRowsPerCSV != 2 {
		t.Fatalf("expected max rows per csv to be 2, got %d", done.maxRowsPerCSV)
	}
	if len(done.outputPaths) != 3 || len(done.xlsxPaths) != 3 {
		t.Fatalf("expected three output and xlsx paths, got %d and %d", len(done.outputPaths), len(done.xlsxPaths))
	}
	for _, csvPath := range done.outputPaths {
		if _, err := os.Stat(csvPath); !os.IsNotExist(err) {
			t.Fatalf("expected csv part to be removed: %s (err=%v)", csvPath, err)
		}
	}
	for _, xlsxPath := range done.xlsxPaths {
		if _, err := os.Stat(xlsxPath); err != nil {
			t.Fatalf("expected xlsx part to exist: %s (err=%v)", xlsxPath, err)
		}
	}
}

func TestConvertCSVToXLSXPreservesLeadingZeros(t *testing.T) {
	workspace := t.TempDir()
	csvPath := filepath.Join(workspace, "input.csv")
	xlsxPath := filepath.Join(workspace, "output.xlsx")

	if err := os.WriteFile(csvPath, []byte(
		"File Name,Extension,Size in Bytes,Size in Human Readable,Path From Root Folder,Hash Algorithm,Hash Value\n"+
			"sample.txt,txt,00123,123 B,nested/sample.txt,,\n",
	), 0o644); err != nil {
		t.Fatalf("write csv: %v", err)
	}

	if err := convertCSVToXLSX(csvPath, xlsxPath, true); err != nil {
		t.Fatalf("convert csv to xlsx: %v", err)
	}

	book, err := excelize.OpenFile(xlsxPath)
	if err != nil {
		t.Fatalf("open xlsx: %v", err)
	}
	defer book.Close()

	value, err := book.GetCellValue("Sheet1", "C2")
	if err != nil {
		t.Fatalf("read xlsx cell: %v", err)
	}
	if value != "00123" {
		t.Fatalf("expected leading zeros to be preserved, got %q", value)
	}
}

func TestRunScanWritesAgencyTemplate(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	if err := ensureDir(filepath.Join(source, "contracts")); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "contracts", "vendor.pdf"), "pdf bytes"); err != nil {
		t.Fatalf("write fixture: %v", err)
	}

	done, err := runScan(source, filepath.Join(workspace, "agency.csv"), scanOptions{
		HashAlgorithm:  hashAlgorithmOff,
		ExcludeHidden:  false,
		ExcludeSystem:  false,
		ExcludedExts:   map[string]struct{}{},
		AgencyTemplate: true,
		AgencyFields: agencyTemplateFields{
			RG:               "1325",
			SG:               "1",
			Series:           "35",
			RCSeries:         "GAR-014",
			DeptOrganization: "Department of State",
			RCSeriesName:     "Annual Reports",
			BeginDate:        "2024",
			EndDate:          "2024",
			MaterialType:     "Born Digital",
			Confidential:     "No",
			TDNum:            "3452",
			LocationID:       "Q: Drive",
			RecordLevel:      "Item",
		},
	})
	if err != nil {
		t.Fatalf("runScan failed: %v", err)
	}
	if !done.agencyTemplate {
		t.Fatalf("expected agency template flag on result")
	}

	rows := readCSVRows(t, done.outputPath)
	if len(rows) != 2 {
		t.Fatalf("expected header plus one row, got %d rows", len(rows))
	}
	expectedHeaders := []string{
		"RG", "SubGr", "Series", "Sub_Series", "RC_Series", "Dept_Organization",
		"Division", "Section", "Unit", "RC_Series_Name", "Begin_Date", "End_Date",
		"File_Num", "File_Name", "Description", "Location", "First_Name", "Middle_Name",
		"Last_Name", "Date_Of_Birth", "File_Type", "Material_Type", "File_Format",
		"Comments", "Confidential", "Disposition_Date", "Box_Num", "Barcode", "TD_Num",
		"Location_ID", "Record_Level",
	}
	assertRowsEqual(t, [][]string{rows[0]}, [][]string{expectedHeaders})
	data := rows[1]
	if len(data) != len(expectedHeaders) {
		t.Fatalf("expected %d agency columns, got %d", len(expectedHeaders), len(data))
	}
	if data[0] != "1325" || data[1] != "001" || data[2] != "035" {
		t.Fatalf("expected RG/SG/Series constants in agency row: %#v", data)
	}
	if data[4] != "GAR-014" || data[13] != "vendor.pdf" || data[15] != "contracts" || data[22] != "PDF" {
		t.Fatalf("unexpected agency row: %#v", data)
	}
	if data[28] != "3452" || data[29] != "Q: Drive" || data[30] != "Item" {
		t.Fatalf("expected transfer/location constants in agency row: %#v", data)
	}
}

func TestRunScanRejectsInvalidAgencyTemplateCodes(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	if err := ensureDir(source); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "vendor.pdf"), "pdf bytes"); err != nil {
		t.Fatalf("write fixture: %v", err)
	}

	tests := []struct {
		name    string
		fields  agencyTemplateFields
		wantErr string
	}{
		{
			name:    "RG letters",
			fields:  agencyTemplateFields{RG: "12A4", SG: "1", Series: "35"},
			wantErr: "RG must contain only digits",
		},
		{
			name:    "SG too long",
			fields:  agencyTemplateFields{RG: "1325", SG: "1234", Series: "35"},
			wantErr: "SG must be 3 digits or fewer",
		},
		{
			name:    "Series too long",
			fields:  agencyTemplateFields{RG: "1325", SG: "1", Series: "1234"},
			wantErr: "Series must be 3 digits or fewer",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := runScan(source, filepath.Join(workspace, tt.name+".csv"), scanOptions{
				HashAlgorithm:  hashAlgorithmOff,
				ExcludedExts:   map[string]struct{}{},
				AgencyTemplate: true,
				AgencyFields:   tt.fields,
			})
			if err == nil || !strings.Contains(err.Error(), tt.wantErr) {
				t.Fatalf("expected error containing %q, got %v", tt.wantErr, err)
			}
		})
	}
}

func TestRunScanMatchesGoldenFixture(t *testing.T) {
	workspace := t.TempDir()
	output := filepath.Join(workspace, "report.csv")
	source := filepath.Join("testing", "content-scan", "fixtures", "source")
	fixed := time.Unix(1_714_566_896, 0)
	for _, relative := range []string{
		"keep.txt",
		"mail/archive.pst",
		"mail/inbox.eml",
		"nested/0007.txt",
		"nested/data.bin",
	} {
		path := filepath.Join(source, relative)
		if err := os.Chtimes(path, fixed, fixed); err != nil {
			t.Fatalf("set fixture timestamp for %s: %v", relative, err)
		}
	}

	done, err := runScan(source, output, scanOptions{
		HashAlgorithm: hashAlgorithmSHA256,
		ExcludeHidden: true,
		ExcludeSystem: true,
		ExcludedExts: map[string]struct{}{
			"log": {},
		},
	})
	if err != nil {
		t.Fatalf("runScan failed: %v", err)
	}
	if done.files != 5 || done.filtered != 3 {
		t.Fatalf("unexpected counts: files=%d filtered=%d", done.files, done.filtered)
	}

	actualRows := readCSVRows(t, done.outputPath)
	expectedRows := readCSVRows(t, filepath.Join("testing", "content-scan", "fixtures", "expected-scan-hash.csv"))
	if len(actualRows) != len(expectedRows) {
		t.Fatalf("row count mismatch: got %d want %d", len(actualRows), len(expectedRows))
	}
	for rowIndex, expectedRow := range expectedRows {
		if len(actualRows[rowIndex]) != len(expectedRow) {
			t.Fatalf("column count mismatch at row %d: got %d want %d", rowIndex, len(actualRows[rowIndex]), len(expectedRow))
		}
		for colIndex, expectedValue := range expectedRow {
			switch expectedValue {
			case "<native-or-unknown>":
				assertFileTimestampValue(t, actualRows[rowIndex][colIndex], true)
			case "<fixed-modified>":
				if actualRows[rowIndex][colIndex] != formatFileTimestamp(fixed, true) {
					t.Fatalf("unexpected modified timestamp at row %d: got %q", rowIndex, actualRows[rowIndex][colIndex])
				}
			default:
				if actualRows[rowIndex][colIndex] != expectedValue {
					t.Fatalf("cell mismatch at row %d col %d: got %q want %q", rowIndex, colIndex, actualRows[rowIndex][colIndex], expectedValue)
				}
			}
		}
	}
}

func assertFileTimestampValue(t *testing.T, value string, allowUnknown bool) {
	t.Helper()
	if allowUnknown && value == unknownFileTimestamp {
		return
	}
	if _, err := time.Parse(fileTimestampLayout, value); err != nil {
		t.Fatalf("invalid file timestamp %q: %v", value, err)
	}
}

func TestCompareScanOutputsReportsDifferences(t *testing.T) {
	workspace := t.TempDir()
	driveA := filepath.Join(workspace, "drive-a")
	driveB := filepath.Join(workspace, "drive-b")
	if err := ensureDir(filepath.Join(driveA, "nested")); err != nil {
		t.Fatalf("mkdir drive a: %v", err)
	}
	if err := ensureDir(driveB); err != nil {
		t.Fatalf("mkdir drive b: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(driveA, "match.txt"), "same"); err != nil {
		t.Fatalf("write drive a match: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(driveB, "match.txt"), "same"); err != nil {
		t.Fatalf("write drive b match: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(driveA, "missing.txt"), "only a"); err != nil {
		t.Fatalf("write drive a missing: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(driveB, "extra.txt"), "only b"); err != nil {
		t.Fatalf("write drive b extra: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(driveA, "nested", "diff.txt"), "first"); err != nil {
		t.Fatalf("write drive a diff: %v", err)
	}
	if err := ensureDir(filepath.Join(driveB, "nested")); err != nil {
		t.Fatalf("mkdir drive b nested: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(driveB, "nested", "diff.txt"), "second"); err != nil {
		t.Fatalf("write drive b diff: %v", err)
	}

	driveAResult, err := runScan(driveA, filepath.Join(workspace, "drive-a-report.csv"), scanOptions{
		HashAlgorithm: hashAlgorithmSHA256,
		ExcludedExts:  map[string]struct{}{},
	})
	if err != nil {
		t.Fatalf("runScan drive A failed: %v", err)
	}
	driveBResult, err := runScan(driveB, filepath.Join(workspace, "drive-b-report.csv"), scanOptions{
		HashAlgorithm: hashAlgorithmSHA256,
		ExcludedExts:  map[string]struct{}{},
	})
	if err != nil {
		t.Fatalf("runScan drive B failed: %v", err)
	}

	diffPath := filepath.Join(workspace, "clone-diff.csv")
	reportPath := filepath.Join(workspace, "clone-report.txt")
	result, err := compareScanOutputs(context.Background(), driveAResult, driveBResult, diffPath, reportPath, false, nil, nil)
	if err != nil {
		t.Fatalf("compareScanOutputs failed: %v", err)
	}
	if result.missingNoMatch != 1 {
		t.Fatalf("expected 1 missing file, got %d", result.missingNoMatch)
	}
	if result.extraNoMatch != 1 {
		t.Fatalf("expected 1 extra file, got %d", result.extraNoMatch)
	}
	if result.hashMismatches != 1 {
		t.Fatalf("expected 1 hash mismatch, got %d", result.hashMismatches)
	}
	if result.differences != 3 {
		t.Fatalf("expected 3 total differences, got %d", result.differences)
	}
	if result.verdict != verdictNotAClone {
		t.Fatalf("expected verdict Not a Clone, got %q", result.verdict)
	}

	diffRows := readCSVRows(t, diffPath)
	if len(diffRows) != 4 {
		t.Fatalf("expected 4 diff rows including header, got %d", len(diffRows))
	}
	reportBytes, err := os.ReadFile(reportPath)
	if err != nil {
		t.Fatalf("read clone report: %v", err)
	}
	if !strings.Contains(string(reportBytes), "Missing from 2nd Drive (no hash match): 1") {
		t.Fatalf("expected clone report to include missing count, got %q", string(reportBytes))
	}
}

func TestDeleteDeferredScanCSVsRemovesFilesAfterCompare(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	if err := ensureDir(source); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "keep.txt"), "hello"); err != nil {
		t.Fatalf("write keep.txt: %v", err)
	}

	done, err := runScan(source, filepath.Join(workspace, "report.csv"), scanOptions{
		CreateXLSX:    true,
		PreserveZeros: true,
		DeleteCSV:     false,
		ExcludedExts:  map[string]struct{}{},
	})
	if err != nil {
		t.Fatalf("runScan failed: %v", err)
	}

	if err := deleteDeferredScanCSVs(&done, true); err != nil {
		t.Fatalf("deleteDeferredScanCSVs failed: %v", err)
	}
	if !done.csvDeleted {
		t.Fatalf("expected csvDeleted to be true after deferred cleanup")
	}
	for _, csvPath := range done.outputPaths {
		if _, err := os.Stat(csvPath); !os.IsNotExist(err) {
			t.Fatalf("expected deferred csv to be removed: %s (err=%v)", csvPath, err)
		}
	}
}

func ensureDir(path string) error {
	return os.MkdirAll(path, 0o755)
}

func writeFixtureFile(path, content string) error {
	return os.WriteFile(path, []byte(content), 0o644)
}
