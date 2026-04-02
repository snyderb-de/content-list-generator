//go:build gui

package main

import (
	"fmt"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/dialog"
	"fyne.io/fyne/v2/layout"
	"fyne.io/fyne/v2/widget"
)

func launchGUI(startDir string) error {
	application := app.NewWithID("content-list-generator.gui")
	window := application.NewWindow("Content List Generator")
	window.Resize(fyne.NewSize(1040, 780))

	tabs := container.NewAppTabs(
		container.NewTabItem("Content List", container.NewVScroll(buildScanTab(window, startDir))),
		container.NewTabItem("Copy Email Files", container.NewVScroll(buildEmailTab(window, startDir))),
		container.NewTabItem("About", container.NewVScroll(buildAboutTab())),
	)
	tabs.SetTabLocation(container.TabLocationTop)

	window.SetContent(tabs)
	window.ShowAndRun()
	return nil
}

func buildScanTab(window fyne.Window, startDir string) fyne.CanvasObject {
	defaultSource := startDir
	defaultOutput := startDir
	defaultFilename := defaultOutputFilename(startDir)

	sourceEntry := widget.NewEntry()
	sourceEntry.SetText(defaultSource)

	outputEntry := widget.NewEntry()
	outputEntry.SetText(defaultOutput)

	fileEntry := widget.NewEntry()
	fileEntry.SetText(defaultFilename)

	excludeEntry := widget.NewEntry()
	excludeEntry.SetPlaceHolder("tmp,log")

	hashCheck := widget.NewCheck("Include SHA-256 hashes", nil)
	hiddenCheck := widget.NewCheck("Exclude hidden files", nil)
	systemCheck := widget.NewCheck("Exclude common system files", nil)
	xlsxCheck := widget.NewCheck("Create XLSX after scan", nil)
	zeroCheck := widget.NewCheck("Preserve leading zeros in XLSX", nil)
	zeroCheck.Disable()
	xlsxCheck.OnChanged = func(checked bool) {
		if checked {
			zeroCheck.Enable()
			return
		}
		zeroCheck.SetChecked(false)
		zeroCheck.Disable()
	}

	statusLabel := widget.NewLabel("Ready.")
	statusLabel.Wrapping = fyne.TextWrapWord
	progressBar := widget.NewProgressBarInfinite()
	progressBar.Hide()
	resultLabel := widget.NewLabel("Run a scan to see the result summary here.")
	resultLabel.Wrapping = fyne.TextWrapWord

	startButton := widget.NewButton("Generate Content List", nil)
	useSourceButton := widget.NewButton("Use Source As Output", func() {
		outputEntry.SetText(sourceEntry.Text)
	})
	resetButton := widget.NewButton("Reset", func() {
		sourceEntry.SetText(defaultSource)
		outputEntry.SetText(defaultOutput)
		fileEntry.SetText(defaultFilename)
		excludeEntry.SetText("")
		hashCheck.SetChecked(false)
		hiddenCheck.SetChecked(false)
		systemCheck.SetChecked(false)
		xlsxCheck.SetChecked(false)
		zeroCheck.SetChecked(false)
		progressBar.Hide()
		statusLabel.SetText("Ready.")
		resultLabel.SetText("Run a scan to see the result summary here.")
	})
	openOutputButton := widget.NewButton("Open Output Folder", func() {
		openPathInFileManager(outputEntry.Text)
	})
	setRunning := func(running bool) {
		if running {
			startButton.Disable()
			useSourceButton.Disable()
			resetButton.Disable()
			progressBar.Show()
			return
		}
		startButton.Enable()
		useSourceButton.Enable()
		resetButton.Enable()
		progressBar.Hide()
	}

	startScan := func() {
		sourceDir := strings.TrimSpace(sourceEntry.Text)
		outputDir := strings.TrimSpace(outputEntry.Text)
		filename := strings.TrimSpace(fileEntry.Text)
		if sourceDir == "" || outputDir == "" || filename == "" {
			dialog.ShowError(fmt.Errorf("source folder, output folder, and file name are required"), window)
			return
		}
		if strings.ToLower(filepath.Ext(filename)) != ".csv" {
			dialog.ShowError(fmt.Errorf("output file name must end in .csv"), window)
			return
		}

		outputPath := filepath.Join(outputDir, filename)
		excluded, err := parseExcludedExtensions(excludeEntry.Text)
		if err != nil {
			dialog.ShowError(err, window)
			return
		}

		run := func() {
			setRunning(true)
			statusLabel.SetText("Collecting files...")
			doneCh := make(chan struct{})
			go func() {
				ticker := time.NewTicker(250 * time.Millisecond)
				defer ticker.Stop()
				for {
					select {
					case <-doneCh:
						return
					case <-ticker.C:
						stats := currentProgress()
						fyne.Do(func() {
							statusLabel.SetText(fmt.Sprintf(
								"Scanning... Files: %d  Dirs: %d  Bytes: %s  Filtered: %d  Elapsed: %s",
								stats.files,
								stats.directories,
								humanBytes(stats.bytes),
								stats.filtered,
								time.Since(stats.startedAt).Round(time.Second),
							))
						})
					}
				}
			}()

			go func() {
				done, err := runScan(sourceDir, outputPath, scanOptions{
					Hashing:       hashCheck.Checked,
					ExcludeHidden: hiddenCheck.Checked,
					ExcludeSystem: systemCheck.Checked,
					CreateXLSX:    xlsxCheck.Checked,
					PreserveZeros: zeroCheck.Checked,
					ExcludedExts:  excluded,
				})
				close(doneCh)
				fyne.Do(func() {
					setRunning(false)
					if err != nil {
						statusLabel.SetText("Scan failed.")
						dialog.ShowError(err, window)
						return
					}
					statusLabel.SetText(fmt.Sprintf("Scan complete. Wrote %d files.", done.files))
					resultLabel.SetText(strings.Join([]string{
						fmt.Sprintf("Output: %s", done.outputPath),
						fmt.Sprintf("XLSX copy: %s", valueOrDefault(done.xlsxPath, "not created")),
						fmt.Sprintf("Files: %d", done.files),
						fmt.Sprintf("Bytes: %s", humanBytes(done.bytes)),
						fmt.Sprintf("Filtered: %d", done.filtered),
						fmt.Sprintf("Hash workers: %d", done.hashWorkers),
						fmt.Sprintf("Elapsed: %s", done.elapsed.Round(time.Millisecond)),
					}, "\n"))
				})
			}()
		}

		exists, err := ensureOutputPath(outputPath)
		if err != nil {
			dialog.ShowError(err, window)
			return
		}
		if exists {
			dialog.ShowConfirm("Overwrite file?", outputPath+"\n\nalready exists. Overwrite it?", func(ok bool) {
				if ok {
					run()
				}
			}, window)
			return
		}
		run()
	}

	startButton.OnTapped = startScan

	form := widget.NewForm(
		widget.NewFormItem("Source folder", pathInputRow(window, sourceEntry, "Choose Source Folder", true)),
		widget.NewFormItem("Output folder", pathInputRow(window, outputEntry, "Choose Output Folder", false)),
		widget.NewFormItem("Output file name", fileEntry),
		widget.NewFormItem("Exclude extensions", excludeEntry),
	)

	options := container.NewVBox(
		widget.NewLabel("Options"),
		hashCheck,
		hiddenCheck,
		systemCheck,
		xlsxCheck,
		zeroCheck,
	)

	actions := container.NewHBox(
		startButton,
		useSourceButton,
		resetButton,
		openOutputButton,
	)

	resultCard := widget.NewCard("Scan Result", "The Go GUI uses the same core engine as the TUI.", resultLabel)

	return container.NewVBox(
		statusLabel,
		progressBar,
		widget.NewSeparator(),
		form,
		widget.NewSeparator(),
		options,
		widget.NewSeparator(),
		actions,
		widget.NewSeparator(),
		resultCard,
	)
}

func buildEmailTab(window fyne.Window, startDir string) fyne.CanvasObject {
	defaultSource := startDir
	defaultDest := startDir
	sourceEntry := widget.NewEntry()
	sourceEntry.SetText(defaultSource)

	destEntry := widget.NewEntry()
	destEntry.SetText(defaultDest)

	statusLabel := widget.NewLabel("Ready.")
	statusLabel.Wrapping = fyne.TextWrapWord
	progressBar := widget.NewProgressBar()
	progressBar.Min = 0
	progressBar.Max = 1
	resultLabel := widget.NewLabel("Run Copy Email Files to see the manifest and destination summary here.")
	resultLabel.Wrapping = fyne.TextWrapWord

	startButton := widget.NewButton("Copy Email Files", nil)
	useSourceButton := widget.NewButton("Use Source As Destination", func() {
		destEntry.SetText(sourceEntry.Text)
	})
	resetButton := widget.NewButton("Reset", func() {
		sourceEntry.SetText(defaultSource)
		destEntry.SetText(defaultDest)
		progressBar.SetValue(0)
		statusLabel.SetText("Ready.")
		resultLabel.SetText("Run Copy Email Files to see the manifest and destination summary here.")
	})
	openDestButton := widget.NewButton("Open Destination", func() {
		openPathInFileManager(destEntry.Text)
	})
	openManifestButton := widget.NewButton("Open Manifest", func() {})
	openManifestButton.Disable()

	latestManifest := ""
	setRunning := func(running bool) {
		if running {
			startButton.Disable()
			useSourceButton.Disable()
			resetButton.Disable()
			return
		}
		startButton.Enable()
		useSourceButton.Enable()
		resetButton.Enable()
	}

	startButton.OnTapped = func() {
		sourceDir := strings.TrimSpace(sourceEntry.Text)
		destDir := strings.TrimSpace(destEntry.Text)
		if sourceDir == "" || destDir == "" {
			dialog.ShowError(fmt.Errorf("source folder and destination folder are required"), window)
			return
		}
		progressBar.SetValue(0)

		setRunning(true)
		statusLabel.SetText("Copying email files...")
		go func() {
			started := time.Now()
			manifestPath, copied, err := copyEmailFilesWithProgress(sourceDir, destDir, func(progress emailCopyProgress) {
				fyne.Do(func() {
					total := float64(max(1, int(progress.Total)))
					progressBar.Max = total
					progressBar.SetValue(float64(progress.Copied))
					if progress.Total == 0 {
						statusLabel.SetText("No supported email files were found in the source folder.")
						return
					}
					if progress.CurrentRel != "" {
						statusLabel.SetText(fmt.Sprintf("Copying %d/%d: %s", progress.Copied, progress.Total, progress.CurrentRel))
						return
					}
					statusLabel.SetText(fmt.Sprintf("Preparing to copy %d email files...", progress.Total))
				})
			})
			fyne.Do(func() {
				setRunning(false)
				if err != nil {
					statusLabel.SetText("Copy Email Files failed.")
					dialog.ShowError(err, window)
					return
				}
				latestManifest = manifestPath
				openManifestButton.Enable()
				statusLabel.SetText(fmt.Sprintf("Copy Email Files complete. Copied %d files.", copied))
				resultLabel.SetText(strings.Join([]string{
					fmt.Sprintf("Source: %s", sourceDir),
					fmt.Sprintf("Destination: %s", destDir),
					fmt.Sprintf("Manifest: %s", manifestPath),
					fmt.Sprintf("Copied: %d", copied),
					fmt.Sprintf("Elapsed: %s", time.Since(started).Round(time.Millisecond)),
					"",
					"Supported extensions:",
					strings.Join(sortedEmailExtensions(), ", "),
				}, "\n"))
			})
		}()
	}

	openManifestButton.OnTapped = func() {
		if latestManifest != "" {
			openPathInFileManager(latestManifest)
		}
	}

	form := widget.NewForm(
		widget.NewFormItem("Source folder", pathInputRow(window, sourceEntry, "Choose Source Folder", true)),
		widget.NewFormItem("Destination folder", pathInputRow(window, destEntry, "Choose Destination Folder", false)),
	)

	actions := container.NewHBox(
		startButton,
		useSourceButton,
		resetButton,
		openDestButton,
		openManifestButton,
	)

	resultCard := widget.NewCard("Copy Email Files Result", "Relative folders are preserved from the chosen source root.", resultLabel)

	return container.NewVBox(
		widget.NewRichTextFromMarkdown("## Copy Email Files\n\nThis desktop flow preserves the original relative folder structure and writes a manifest report in the destination."),
		statusLabel,
		progressBar,
		widget.NewSeparator(),
		form,
		widget.NewSeparator(),
		widget.NewLabel("Extensions"),
		widget.NewLabel(strings.Join(sortedEmailExtensions(), ", ")),
		widget.NewSeparator(),
		actions,
		widget.NewSeparator(),
		resultCard,
	)
}

func buildAboutTab() fyne.CanvasObject {
	body := widget.NewRichTextFromMarkdown(strings.Join([]string{
		"## About This GUI",
		"",
		"- The default Go app is still the Bubble Tea TUI.",
		"- This desktop mode is an additional shell on top of the same `core.go` logic.",
		"- It is intended for macOS/Linux desktop use and is currently built with the `gui` build tag.",
		"",
		"Launch it with:",
		"",
		"```bash",
		"go run -tags gui . --gui",
		"```",
	}, "\n"))
	return container.New(layout.NewCenterLayout(), container.NewPadded(body))
}

func pathInputRow(window fyne.Window, entry *widget.Entry, title string, mustExist bool) fyne.CanvasObject {
	browse := widget.NewButton("Browse", func() {
		openDialog := dialog.NewFolderOpen(func(uri fyne.ListableURI, err error) {
			if err != nil {
				dialog.ShowError(err, window)
				return
			}
			if uri == nil {
				return
			}
			entry.SetText(uri.Path())
		}, window)
		openDialog.Resize(fyne.NewSize(1000, 750))
		openDialog.Show()
	})
	return container.NewBorder(nil, nil, nil, browse, entry)
}

func openPathInFileManager(path string) {
	if strings.TrimSpace(path) == "" {
		return
	}

	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("open", path)
	case "linux":
		cmd = exec.Command("xdg-open", path)
	default:
		return
	}
	_ = cmd.Start()
}
