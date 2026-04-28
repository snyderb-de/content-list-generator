package main

import (
	"context"
	"encoding/csv"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

type cloneCompareProgress struct {
	compared    uint64
	total       uint64
	differences uint64
	currentItem string
}

type cloneVerificationDone struct {
	driveA              scanDoneMsg
	driveB              scanDoneMsg
	diffPath            string
	reportPath          string
	hashAlgorithm       hashAlgorithm
	elapsed             time.Duration
	compared            uint64
	differences         uint64
	missingFromDriveB   uint64
	extraOnDriveB       uint64
	sizeMismatches      uint64
	hashMismatches      uint64
	csvDeferredDeletion bool
}

type scanCSVRow struct {
	fileName      string
	extension     string
	size          uint64
	relativePath  string
	hashAlgorithm string
	hashValue     string
}

type scanCSVIterator struct {
	paths       []string
	pathIndex   int
	file        *os.File
	reader      *csv.Reader
	currentPath string
}

func compareProgressFraction(progress cloneCompareProgress) float64 {
	if progress.total == 0 {
		return 0
	}
	value := float64(progress.compared) / float64(progress.total)
	if value < 0 {
		return 0
	}
	if value > 1 {
		return 1
	}
	return value
}

func cloneOutputPathForDriveB(outputPath string) string {
	ext := filepath.Ext(outputPath)
	base := strings.TrimSuffix(outputPath, ext)
	return base + "-clone-b" + ext
}

func cloneDiffCSVPath(outputPath string) string {
	ext := filepath.Ext(outputPath)
	base := strings.TrimSuffix(outputPath, ext)
	return base + "-clone-differences" + ext
}

func cloneDiffReportPath(outputPath string) string {
	ext := filepath.Ext(outputPath)
	base := strings.TrimSuffix(outputPath, ext)
	return base + "-clone-report.txt"
}

func newScanCSVIterator(paths []string) (*scanCSVIterator, error) {
	iter := &scanCSVIterator{
		paths: append([]string{}, paths...),
	}
	if err := iter.openNext(); err != nil {
		return nil, err
	}
	return iter, nil
}

func (it *scanCSVIterator) openNext() error {
	_ = it.closeCurrent()
	for it.pathIndex < len(it.paths) {
		nextPath := it.paths[it.pathIndex]
		it.pathIndex++
		file, err := os.Open(nextPath)
		if err != nil {
			return err
		}
		reader := csv.NewReader(file)
		if _, err := reader.Read(); err != nil {
			file.Close()
			if errors.Is(err, io.EOF) {
				continue
			}
			return err
		}
		it.file = file
		it.reader = reader
		it.currentPath = nextPath
		return nil
	}
	it.file = nil
	it.reader = nil
	it.currentPath = ""
	return io.EOF
}

func (it *scanCSVIterator) closeCurrent() error {
	if it.file == nil {
		return nil
	}
	err := it.file.Close()
	it.file = nil
	it.reader = nil
	it.currentPath = ""
	return err
}

func (it *scanCSVIterator) Close() error {
	return it.closeCurrent()
}

func (it *scanCSVIterator) Next() (*scanCSVRow, error) {
	for {
		if it.reader == nil {
			return nil, io.EOF
		}
		row, err := it.reader.Read()
		if err == nil {
			if len(row) < 7 {
				return nil, fmt.Errorf("scan csv row in %s is missing columns", it.currentPath)
			}
			size, parseErr := strconv.ParseUint(strings.TrimSpace(row[2]), 10, 64)
			if parseErr != nil {
				return nil, fmt.Errorf("scan csv row in %s has invalid size %q: %w", it.currentPath, row[2], parseErr)
			}
			return &scanCSVRow{
				fileName:      row[0],
				extension:     row[1],
				size:          size,
				relativePath:  row[4],
				hashAlgorithm: row[5],
				hashValue:     row[6],
			}, nil
		}
		if errors.Is(err, io.EOF) {
			if openErr := it.openNext(); openErr != nil {
				if errors.Is(openErr, io.EOF) {
					return nil, io.EOF
				}
				return nil, openErr
			}
			continue
		}
		return nil, err
	}
}

func compareScanOutputs(
	ctx context.Context,
	driveA scanDoneMsg,
	driveB scanDoneMsg,
	diffPath string,
	reportPath string,
	progress func(cloneCompareProgress),
) (cloneVerificationDone, error) {
	startedAt := time.Now()
	result := cloneVerificationDone{
		driveA:        driveA,
		driveB:        driveB,
		diffPath:      diffPath,
		reportPath:    reportPath,
		hashAlgorithm: driveA.hashAlgorithm,
	}

	driveAIter, err := newScanCSVIterator(driveA.outputPaths)
	if err != nil {
		return result, err
	}
	defer driveAIter.Close()

	driveBIter, err := newScanCSVIterator(driveB.outputPaths)
	if err != nil {
		return result, err
	}
	defer driveBIter.Close()

	if err := os.MkdirAll(filepath.Dir(diffPath), 0o755); err != nil {
		return result, err
	}
	diffFile, err := os.Create(diffPath)
	if err != nil {
		return result, err
	}
	writer := csv.NewWriter(diffFile)
	writeErr := func(err error) (cloneVerificationDone, error) {
		writer.Flush()
		_ = diffFile.Close()
		cleanupScanArtifacts(diffPath, result.reportPath)
		return result, err
	}

	if err := writer.Write([]string{
		"Difference Type",
		"Path From Root Folder",
		"1st Drive File Name",
		"2nd Drive File Name",
		"1st Drive Size in Bytes",
		"2nd Drive Size in Bytes",
		"1st Drive Hash Algorithm",
		"2nd Drive Hash Algorithm",
		"1st Drive Hash Value",
		"2nd Drive Hash Value",
	}); err != nil {
		return writeErr(err)
	}

	nextProgress := func(currentItem string) {
		if progress == nil {
			return
		}
		total := driveA.files
		if driveB.files > total {
			total = driveB.files
		}
		progress(cloneCompareProgress{
			compared:    result.compared,
			total:       total,
			differences: result.differences,
			currentItem: currentItem,
		})
	}

	nextA, err := driveAIter.Next()
	if err != nil && !errors.Is(err, io.EOF) {
		return writeErr(err)
	}
	if errors.Is(err, io.EOF) {
		nextA = nil
	}
	nextB, err := driveBIter.Next()
	if err != nil && !errors.Is(err, io.EOF) {
		return writeErr(err)
	}
	if errors.Is(err, io.EOF) {
		nextB = nil
	}

	for nextA != nil || nextB != nil {
		select {
		case <-ctx.Done():
			return writeErr(ctx.Err())
		default:
		}

		switch {
		case nextA != nil && nextB != nil && nextA.relativePath == nextB.relativePath:
			result.compared++
			diffType := ""
			sizeMismatch := nextA.size != nextB.size
			hashMismatch := nextA.hashValue != nextB.hashValue || nextA.hashAlgorithm != nextB.hashAlgorithm
			switch {
			case sizeMismatch && hashMismatch:
				diffType = "size and hash mismatch"
				result.sizeMismatches++
				result.hashMismatches++
			case sizeMismatch:
				diffType = "size mismatch"
				result.sizeMismatches++
			case hashMismatch:
				diffType = "hash mismatch"
				result.hashMismatches++
			}
			if diffType != "" {
				result.differences++
				if err := writer.Write([]string{
					diffType,
					nextA.relativePath,
					nextA.fileName,
					nextB.fileName,
					strconv.FormatUint(nextA.size, 10),
					strconv.FormatUint(nextB.size, 10),
					nextA.hashAlgorithm,
					nextB.hashAlgorithm,
					nextA.hashValue,
					nextB.hashValue,
				}); err != nil {
					return writeErr(err)
				}
			}
			nextProgress(nextA.relativePath)
			nextA, err = driveAIter.Next()
			if err != nil && !errors.Is(err, io.EOF) {
				return writeErr(err)
			}
			if errors.Is(err, io.EOF) {
				nextA = nil
			}
			nextB, err = driveBIter.Next()
			if err != nil && !errors.Is(err, io.EOF) {
				return writeErr(err)
			}
			if errors.Is(err, io.EOF) {
				nextB = nil
			}
		case nextB == nil || nextA != nil && nextA.relativePath < nextB.relativePath:
			result.differences++
			result.missingFromDriveB++
			if err := writer.Write([]string{
				"missing from 2nd Drive",
				nextA.relativePath,
				nextA.fileName,
				"",
				strconv.FormatUint(nextA.size, 10),
				"",
				nextA.hashAlgorithm,
				"",
				nextA.hashValue,
				"",
			}); err != nil {
				return writeErr(err)
			}
			nextProgress(nextA.relativePath)
			nextA, err = driveAIter.Next()
			if err != nil && !errors.Is(err, io.EOF) {
				return writeErr(err)
			}
			if errors.Is(err, io.EOF) {
				nextA = nil
			}
		default:
			result.differences++
			result.extraOnDriveB++
			if err := writer.Write([]string{
				"extra on 2nd Drive",
				nextB.relativePath,
				"",
				nextB.fileName,
				"",
				strconv.FormatUint(nextB.size, 10),
				"",
				nextB.hashAlgorithm,
				"",
				nextB.hashValue,
			}); err != nil {
				return writeErr(err)
			}
			nextProgress(nextB.relativePath)
			nextB, err = driveBIter.Next()
			if err != nil && !errors.Is(err, io.EOF) {
				return writeErr(err)
			}
			if errors.Is(err, io.EOF) {
				nextB = nil
			}
		}
	}

	writer.Flush()
	if err := writer.Error(); err != nil {
		return writeErr(err)
	}
	if err := diffFile.Close(); err != nil {
		return writeErr(err)
	}

	result.elapsed = time.Since(startedAt)
	if err := writeCloneVerificationReport(result.reportPath, result); err != nil {
		cleanupScanArtifacts(diffPath, result.reportPath)
		return result, err
	}
	return result, nil
}

func writeCloneVerificationReport(reportPath string, result cloneVerificationDone) error {
	return os.WriteFile(reportPath, []byte(buildCloneVerificationReport(result)), 0o644)
}

func buildCloneVerificationReport(result cloneVerificationDone) string {
	status := "match"
	if result.differences > 0 {
		status = "differences found"
	}
	lines := []string{
		"Clone Verification Report",
		fmt.Sprintf("Verification result: %s", status),
		fmt.Sprintf("1st Drive folder: %s", valueOrDefault(result.driveA.sourceName, "unknown")),
		fmt.Sprintf("2nd Drive folder: %s", valueOrDefault(result.driveB.sourceName, "unknown")),
		fmt.Sprintf("1st Drive content list: %s", filepath.Base(result.driveA.outputPath)),
		fmt.Sprintf("2nd Drive content list: %s", filepath.Base(result.driveB.outputPath)),
		fmt.Sprintf("1st Drive summary report: %s", filepath.Base(result.driveA.reportPath)),
		fmt.Sprintf("2nd Drive summary report: %s", filepath.Base(result.driveB.reportPath)),
		fmt.Sprintf("Differences CSV: %s", filepath.Base(result.diffPath)),
		fmt.Sprintf("Verification hash: %s", result.hashAlgorithm.OptionLabel()),
		fmt.Sprintf("Matched paths checked: %d", result.compared),
		fmt.Sprintf("Missing from 2nd Drive: %d", result.missingFromDriveB),
		fmt.Sprintf("Extra on 2nd Drive: %d", result.extraOnDriveB),
		fmt.Sprintf("Size mismatches: %d", result.sizeMismatches),
		fmt.Sprintf("Hash mismatches: %d", result.hashMismatches),
		fmt.Sprintf("Total differences: %d", result.differences),
		fmt.Sprintf("Finished in: %s", result.elapsed.Round(time.Millisecond)),
	}
	return strings.Join(lines, "\n") + "\n"
}

func buildCloneVerificationSummary(result cloneVerificationDone) string {
	status := "Clone verification passed."
	if result.differences > 0 {
		status = "Clone verification found differences."
	}
	lines := []string{
		status,
		fmt.Sprintf("1st Drive folder: %s", valueOrDefault(result.driveA.sourceName, "unknown")),
		fmt.Sprintf("2nd Drive folder: %s", valueOrDefault(result.driveB.sourceName, "unknown")),
		fmt.Sprintf("1st Drive content list: %s", filepath.Base(result.driveA.outputPath)),
		fmt.Sprintf("2nd Drive content list: %s", filepath.Base(result.driveB.outputPath)),
		fmt.Sprintf("Differences CSV: %s", filepath.Base(result.diffPath)),
		fmt.Sprintf("Clone report: %s", filepath.Base(result.reportPath)),
		fmt.Sprintf("Verification hash: %s", result.hashAlgorithm.OptionLabel()),
		fmt.Sprintf("Missing from 2nd Drive: %d", result.missingFromDriveB),
		fmt.Sprintf("Extra on 2nd Drive: %d", result.extraOnDriveB),
		fmt.Sprintf("Size mismatches: %d", result.sizeMismatches),
		fmt.Sprintf("Hash mismatches: %d", result.hashMismatches),
		fmt.Sprintf("Total differences: %d", result.differences),
		fmt.Sprintf("Finished in: %s", result.elapsed.Round(time.Millisecond)),
	}
	return strings.Join(lines, "\n")
}

func deleteDeferredScanCSVs(done *scanDoneMsg, deleteRequested bool) error {
	if done == nil {
		return nil
	}
	if !deleteRequested || !done.createXLSX {
		done.deleteCSV = deleteRequested
		return nil
	}
	for _, csvPath := range done.outputPaths {
		if err := os.Remove(csvPath); err != nil && !errors.Is(err, os.ErrNotExist) {
			return err
		}
	}
	done.deleteCSV = true
	done.csvDeleted = true
	return writeScanReport(done.reportPath, *done)
}
