package main

import (
	"bufio"
	"context"
	"encoding/csv"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"slices"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/xuri/excelize/v2"
)

type summaryEntry struct {
	Label string
	Count uint64
	Bytes uint64
}

type scanDoneMsg struct {
	files           uint64
	directories     uint64
	bytes           uint64
	errors          uint64
	filtered        uint64
	outputPath      string
	xlsxPath        string
	elapsed         time.Duration
	topByCount      []summaryEntry
	topBySize       []summaryEntry
	hashWorkers     int
	hashAlgorithm   hashAlgorithm
	excludeHidden   bool
	excludeSystem   bool
	createXLSX      bool
	preserveZeros   bool
	filteredHidden  uint64
	filteredSystem  uint64
	filteredExts    uint64
	filteredSamples []string
}

type scanOptions struct {
	HashAlgorithm    hashAlgorithm
	ExcludeHidden    bool
	ExcludeSystem    bool
	CreateXLSX       bool
	PreserveZeros    bool
	ExcludedExts     map[string]struct{}
	ExcludedExtsText string
}

type scanWork struct {
	index    uint64
	path     string
	relative string
	name     string
	ext      string
	size     uint64
}

type scanResult struct {
	index uint64
	work  scanWork
	hash  string
	err   error
}

type scannerStats struct {
	files       atomic.Uint64
	directories atomic.Uint64
	bytes       atomic.Uint64
	errors      atomic.Uint64
	filtered    atomic.Uint64
}

type emailCopyProgress struct {
	Phase       string
	Scanned     uint64
	Matched     uint64
	Copied      uint64
	Total       uint64
	CurrentRel  string
	CurrentName string
}

var emailExtensions = map[string]struct{}{
	".dbx":            {},
	".eml":            {},
	".emlx":           {},
	".emlxpart":       {},
	".mbox":           {},
	".mbx":            {},
	".msg":            {},
	".olk14msgsource": {},
	".olk15message":   {},
	".ost":            {},
	".pst":            {},
	".rge":            {},
	".tbb":            {},
	".wdseml":         {},
}

type scanCountTotals struct {
	files       uint64
	directories uint64
}

func sortedEmailExtensions() []string {
	values := make([]string, 0, len(emailExtensions))
	for ext := range emailExtensions {
		values = append(values, ext)
	}
	slices.Sort(values)
	return values
}

func countScanTargets(sourceDir string, options scanOptions, startedAt time.Time) (scanCountTotals, error) {
	totals := scanCountTotals{}
	err := filepath.WalkDir(sourceDir, func(path string, d fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return nil
		}

		if d.IsDir() {
			if path != sourceDir && options.ExcludeHidden && isHiddenName(d.Name()) {
				setProgress(globalProgress{
					phase:          progressPhaseCounting,
					files:          totals.files,
					directories:    totals.directories,
					startedAt:      startedAt,
					phaseStartedAt: startedAt,
				})
				return filepath.SkipDir
			}
			totals.directories++
			setProgress(globalProgress{
				phase:          progressPhaseCounting,
				files:          totals.files,
				directories:    totals.directories,
				startedAt:      startedAt,
				phaseStartedAt: startedAt,
			})
			return nil
		}

		if _, skipped := shouldSkipFile(path, d.Name(), options); skipped {
			return nil
		}

		info, err := d.Info()
		if err != nil {
			return nil
		}
		if !info.Mode().IsRegular() {
			return nil
		}

		totals.files++
		setProgress(globalProgress{
			phase:          progressPhaseCounting,
			files:          totals.files,
			directories:    totals.directories,
			startedAt:      startedAt,
			phaseStartedAt: startedAt,
		})
		return nil
	})
	return totals, err
}

type reportWriter interface {
	WriteHeader() error
	WriteRow([]string) error
	Finalize(uint64) error
	Close() error
}

type csvReportWriter struct {
	file   *os.File
	buffer *bufio.Writer
	writer *csv.Writer
}

func newReportWriter(outputPath string) (reportWriter, error) {
	if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil {
		return nil, err
	}
	file, err := os.Create(outputPath)
	if err != nil {
		return nil, err
	}
	buffer := bufio.NewWriterSize(file, 1<<20)
	return &csvReportWriter{
		file:   file,
		buffer: buffer,
		writer: csv.NewWriter(buffer),
	}, nil
}

func (w *csvReportWriter) WriteHeader() error {
	return w.writer.Write([]string{
		"File Name",
		"Extension",
		"Size in Bytes",
		"Size in Human Readable",
		"Path From Root Folder",
		"Hash Algorithm",
		"Hash Value",
	})
}

func (w *csvReportWriter) WriteRow(values []string) error {
	return w.writer.Write(values)
}

func (w *csvReportWriter) Finalize(_ uint64) error {
	w.writer.Flush()
	if err := w.writer.Error(); err != nil {
		return err
	}
	return w.buffer.Flush()
}

func (w *csvReportWriter) Close() error {
	return w.file.Close()
}

func runScan(sourceDir, outputPath string, options scanOptions) (scanDoneMsg, error) {
	startedAt := time.Now()
	setProgress(globalProgress{
		phase:          progressPhaseCounting,
		startedAt:      startedAt,
		phaseStartedAt: startedAt,
	})

	counts, err := countScanTargets(sourceDir, options, startedAt)
	if err != nil {
		return scanDoneMsg{}, err
	}

	reportWriter, err := newReportWriter(outputPath)
	if err != nil {
		return scanDoneMsg{}, err
	}
	defer reportWriter.Close()

	if err := reportWriter.WriteHeader(); err != nil {
		return scanDoneMsg{}, err
	}

	stats := &scannerStats{}
	hashWorkers := 1
	if options.HashAlgorithm.Enabled() {
		hashWorkers = max(2, runtime.NumCPU())
	}

	scanStartedAt := time.Now()
	setProgress(globalProgress{
		phase:            progressPhaseScanning,
		totalFiles:       counts.files,
		totalDirectories: counts.directories,
		startedAt:        startedAt,
		phaseStartedAt:   scanStartedAt,
	})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	workCh := make(chan scanWork, hashWorkers*4)
	resultCh := make(chan scanResult, hashWorkers*4)
	walkErrCh := make(chan error, 1)
	typeTotals := make(map[string]summaryEntry)
	pending := make(map[uint64]scanResult)
	filteredHidden := uint64(0)
	filteredSystem := uint64(0)
	filteredExts := uint64(0)
	filteredSamples := make([]string, 0, 8)
	var expected uint64

	var workerWG sync.WaitGroup
	for range hashWorkers {
		workerWG.Add(1)
		go func() {
			defer workerWG.Done()
			for work := range workCh {
				hashValue := ""
				var resultErr error
				hashValue, resultErr = hashFile(work.path, options.HashAlgorithm)
				select {
				case resultCh <- scanResult{index: work.index, work: work, hash: hashValue, err: resultErr}:
				case <-ctx.Done():
					return
				}
			}
		}()
	}

	go func() {
		workerWG.Wait()
		close(resultCh)
	}()

	go func() {
		defer close(workCh)
		var index uint64
		walkErrCh <- filepath.WalkDir(sourceDir, func(path string, d fs.DirEntry, walkErr error) error {
			if walkErr != nil {
				stats.errors.Add(1)
				return nil
			}

			if d.IsDir() {
				if path != sourceDir && options.ExcludeHidden && isHiddenName(d.Name()) {
					stats.filtered.Add(1)
					filteredHidden++
					filteredSamples = appendFilteredSample(filteredSamples, fmt.Sprintf("%s -> hidden directory", filepath.ToSlash(path)))
					setProgress(globalProgress{
						phase:            progressPhaseScanning,
						files:            stats.files.Load(),
						directories:      stats.directories.Load(),
						bytes:            stats.bytes.Load(),
						filtered:         stats.filtered.Load(),
						totalFiles:       counts.files,
						totalDirectories: counts.directories,
						startedAt:        startedAt,
						phaseStartedAt:   scanStartedAt,
					})
					return filepath.SkipDir
				}
				stats.directories.Add(1)
				setProgress(globalProgress{
					phase:            progressPhaseScanning,
					files:            stats.files.Load(),
					directories:      stats.directories.Load(),
					bytes:            stats.bytes.Load(),
					filtered:         stats.filtered.Load(),
					totalFiles:       counts.files,
					totalDirectories: counts.directories,
					startedAt:        startedAt,
					phaseStartedAt:   scanStartedAt,
				})
				return nil
			}

			if reason, skipped := shouldSkipFile(path, d.Name(), options); skipped {
				stats.filtered.Add(1)
				switch reason {
				case "hidden path":
					filteredHidden++
				case "system file":
					filteredSystem++
				case "excluded extension":
					filteredExts++
				}
				filteredSamples = appendFilteredSample(filteredSamples, fmt.Sprintf("%s -> %s", filepath.ToSlash(path), reason))
				setProgress(globalProgress{
					phase:            progressPhaseScanning,
					files:            stats.files.Load(),
					directories:      stats.directories.Load(),
					bytes:            stats.bytes.Load(),
					filtered:         stats.filtered.Load(),
					totalFiles:       counts.files,
					totalDirectories: counts.directories,
					startedAt:        startedAt,
					phaseStartedAt:   scanStartedAt,
				})
				return nil
			}

			info, err := d.Info()
			if err != nil {
				stats.errors.Add(1)
				return nil
			}
			if !info.Mode().IsRegular() {
				return nil
			}

			relative, err := filepath.Rel(sourceDir, path)
			if err != nil {
				stats.errors.Add(1)
				return nil
			}

			work := scanWork{
				index:    index,
				path:     path,
				relative: filepath.ToSlash(relative),
				name:     filepath.Base(path),
				ext:      normalizeExt(filepath.Ext(path)),
				size:     uint64(info.Size()),
			}
			index++

			select {
			case workCh <- work:
				return nil
			case <-ctx.Done():
				return ctx.Err()
			}
		})
	}()

	for result := range resultCh {
		pending[result.index] = result
		for {
			ready, ok := pending[expected]
			if !ok {
				break
			}
			delete(pending, expected)
			expected++

			if ready.err != nil {
				stats.errors.Add(1)
				setProgress(globalProgress{
					phase:            progressPhaseScanning,
					files:            stats.files.Load(),
					directories:      stats.directories.Load(),
					bytes:            stats.bytes.Load(),
					filtered:         stats.filtered.Load(),
					totalFiles:       counts.files,
					totalDirectories: counts.directories,
					startedAt:        startedAt,
					phaseStartedAt:   scanStartedAt,
				})
				continue
			}

			if err := reportWriter.WriteRow([]string{
				ready.work.name,
				ready.work.ext,
				fmt.Sprintf("%d", ready.work.size),
				humanBytes(ready.work.size),
				ready.work.relative,
				options.HashAlgorithm.CSVName(),
				ready.hash,
			}); err != nil {
				cancel()
				return scanDoneMsg{}, err
			}

			stats.files.Add(1)
			stats.bytes.Add(ready.work.size)

			key := summaryKey(ready.work.ext)
			entry := typeTotals[key]
			entry.Label = key
			entry.Count++
			entry.Bytes += ready.work.size
			typeTotals[key] = entry

			setProgress(globalProgress{
				phase:            progressPhaseScanning,
				files:            stats.files.Load(),
				directories:      stats.directories.Load(),
				bytes:            stats.bytes.Load(),
				filtered:         stats.filtered.Load(),
				totalFiles:       counts.files,
				totalDirectories: counts.directories,
				startedAt:        startedAt,
				phaseStartedAt:   scanStartedAt,
			})
		}
	}

	if walkErr := <-walkErrCh; walkErr != nil && !errors.Is(walkErr, context.Canceled) {
		return scanDoneMsg{}, walkErr
	}
	if err := reportWriter.Finalize(stats.files.Load()); err != nil {
		return scanDoneMsg{}, err
	}

	xlsxPath := ""
	if options.CreateXLSX {
		xlsxStartedAt := time.Now()
		setProgress(globalProgress{
			phase:            progressPhaseXLSX,
			files:            stats.files.Load(),
			directories:      stats.directories.Load(),
			bytes:            stats.bytes.Load(),
			filtered:         stats.filtered.Load(),
			totalFiles:       counts.files,
			totalDirectories: counts.directories,
			startedAt:        startedAt,
			phaseStartedAt:   xlsxStartedAt,
		})
		xlsxPath = strings.TrimSuffix(outputPath, filepath.Ext(outputPath)) + ".xlsx"
		if err := convertCSVToXLSX(outputPath, xlsxPath, options.PreserveZeros); err != nil {
			return scanDoneMsg{}, err
		}
	}

	return scanDoneMsg{
		files:           stats.files.Load(),
		directories:     stats.directories.Load(),
		bytes:           stats.bytes.Load(),
		errors:          stats.errors.Load(),
		filtered:        stats.filtered.Load(),
		outputPath:      outputPath,
		xlsxPath:        xlsxPath,
		elapsed:         time.Since(startedAt),
		topByCount:      summarizeByCount(typeTotals, 8),
		topBySize:       summarizeBySize(typeTotals, 8),
		hashWorkers:     hashWorkers,
		hashAlgorithm:   options.HashAlgorithm,
		excludeHidden:   options.ExcludeHidden,
		excludeSystem:   options.ExcludeSystem,
		createXLSX:      options.CreateXLSX,
		preserveZeros:   options.PreserveZeros,
		filteredHidden:  filteredHidden,
		filteredSystem:  filteredSystem,
		filteredExts:    filteredExts,
		filteredSamples: filteredSamples,
	}, nil
}

func copyEmailFiles(sourceDir, destDir string) (string, uint64, error) {
	return copyEmailFilesWithProgress(sourceDir, destDir, nil)
}

func copyEmailFilesWithProgress(sourceDir, destDir string, progress func(emailCopyProgress)) (string, uint64, error) {
	sourceAbs, err := filepath.Abs(sourceDir)
	if err != nil {
		return "", 0, err
	}
	destAbs, err := filepath.Abs(destDir)
	if err != nil {
		return "", 0, err
	}
	if sourceAbs == destAbs {
		return "", 0, fmt.Errorf("destination folder must be different from the source folder")
	}
	if isPathWithin(destAbs, sourceAbs) {
		return "", 0, fmt.Errorf("destination folder cannot be inside the source folder")
	}
	if err := os.MkdirAll(destDir, 0o755); err != nil {
		return "", 0, err
	}

	timestamp := time.Now().Format("2006-01-02T15-04-05")
	manifestPath := filepath.Join(destDir, fmt.Sprintf("email-copy-manifest-%s.csv", timestamp))

	manifestFile, err := os.Create(manifestPath)
	if err != nil {
		return "", 0, err
	}
	defer manifestFile.Close()

	writer := csv.NewWriter(manifestFile)
	defer writer.Flush()

	if err := writer.Write([]string{
		"Source Path",
		"Destination Path",
		"Relative Path",
		"File Name",
		"Extension",
		"Size in Bytes",
	}); err != nil {
		return "", 0, err
	}

	matches := make([]string, 0, 256)
	var scanned uint64
	err = filepath.WalkDir(sourceAbs, func(path string, d fs.DirEntry, walkErr error) error {
		if walkErr != nil || d.IsDir() {
			return nil
		}
		scanned++
		if progress != nil {
			progress(emailCopyProgress{
				Phase:       "scanning",
				Scanned:     scanned,
				Matched:     uint64(len(matches)),
				CurrentName: d.Name(),
			})
		}

		ext := strings.ToLower(filepath.Ext(d.Name()))
		if _, ok := emailExtensions[ext]; !ok {
			return nil
		}

		matches = append(matches, path)
		if progress != nil {
			progress(emailCopyProgress{
				Phase:       "scanning",
				Scanned:     scanned,
				Matched:     uint64(len(matches)),
				CurrentName: d.Name(),
			})
		}
		return nil
	})
	if err != nil {
		return "", 0, err
	}
	if progress != nil {
		progress(emailCopyProgress{
			Phase:   "copying",
			Scanned: scanned,
			Matched: uint64(len(matches)),
			Total:   uint64(len(matches)),
		})
	}

	var copied uint64
	for _, path := range matches {
		relative, err := filepath.Rel(sourceAbs, path)
		if err != nil {
			continue
		}
		ext := strings.ToLower(filepath.Ext(path))
		targetPath := filepath.Join(destAbs, relative)
		if err := os.MkdirAll(filepath.Dir(targetPath), 0o755); err != nil {
			return "", 0, err
		}
		if err := copyFile(path, targetPath); err != nil {
			return "", 0, err
		}

		info, err := os.Stat(path)
		if err != nil {
			continue
		}

		if err := writer.Write([]string{
			path,
			targetPath,
			filepath.ToSlash(relative),
			filepath.Base(path),
			ext,
			fmt.Sprintf("%d", info.Size()),
		}); err != nil {
			return "", 0, err
		}

		copied++
		if progress != nil {
			progress(emailCopyProgress{
				Phase:       "copying",
				Scanned:     scanned,
				Matched:     uint64(len(matches)),
				Copied:      copied,
				Total:       uint64(len(matches)),
				CurrentRel:  filepath.ToSlash(relative),
				CurrentName: filepath.Base(path),
			})
		}
	}
	writer.Flush()
	if err := writer.Error(); err != nil {
		return "", 0, err
	}

	return manifestPath, copied, nil
}

func isPathWithin(candidate, root string) bool {
	rel, err := filepath.Rel(root, candidate)
	if err != nil {
		return false
	}
	return rel != "." && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator))
}

func copyFile(sourcePath, destPath string) error {
	sourceFile, err := os.Open(sourcePath)
	if err != nil {
		return err
	}
	defer sourceFile.Close()

	destFile, err := os.Create(destPath)
	if err != nil {
		return err
	}
	defer destFile.Close()

	if _, err := io.Copy(destFile, sourceFile); err != nil {
		return err
	}
	if err := destFile.Sync(); err != nil {
		return err
	}

	info, err := os.Stat(sourcePath)
	if err == nil {
		_ = os.Chmod(destPath, info.Mode())
	}
	return nil
}

func convertCSVToXLSX(csvPath, xlsxPath string, preserveZeros bool) error {
	file, err := os.Open(csvPath)
	if err != nil {
		return err
	}
	defer file.Close()

	reader := csv.NewReader(file)
	rows, err := reader.ReadAll()
	if err != nil {
		return err
	}

	workbook := excelize.NewFile()
	defer workbook.Close()

	sheet := workbook.GetSheetName(workbook.GetActiveSheetIndex())
	streamWriter, err := workbook.NewStreamWriter(sheet)
	if err != nil {
		return err
	}

	textStyleID := 0
	if preserveZeros {
		textStyleID, err = workbook.NewStyle(&excelize.Style{NumFmt: 49})
		if err != nil {
			return err
		}
	}

	for rowIndex, row := range rows {
		cellName, err := excelize.CoordinatesToCellName(1, rowIndex+1)
		if err != nil {
			return err
		}

		cells := make([]interface{}, 0, len(row))
		for colIndex, value := range row {
			if preserveZeros {
				cells = append(cells, excelize.Cell{StyleID: textStyleID, Value: value})
				continue
			}
			if rowIndex > 0 && colIndex == 2 {
				cells = append(cells, parseUintString(value))
				continue
			}
			cells = append(cells, value)
		}

		if err := streamWriter.SetRow(cellName, cells); err != nil {
			return err
		}
	}

	if err := streamWriter.Flush(); err != nil {
		return err
	}

	if len(rows) > 0 {
		lastCell, err := excelize.CoordinatesToCellName(6, len(rows))
		if err == nil {
			showRows := true
			_ = workbook.AddTable(sheet, &excelize.Table{
				Range:             "A1:" + lastCell,
				Name:              "ContentList",
				StyleName:         "TableStyleMedium2",
				ShowFirstColumn:   false,
				ShowLastColumn:    false,
				ShowRowStripes:    &showRows,
				ShowColumnStripes: false,
			})
		}
	}

	return workbook.SaveAs(xlsxPath)
}

func parseUintString(value string) interface{} {
	var parsed uint64
	for _, char := range value {
		if char < '0' || char > '9' {
			return value
		}
		parsed = parsed*10 + uint64(char-'0')
	}
	return parsed
}
