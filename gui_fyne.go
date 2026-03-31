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
		container.NewTabItem("Content List", buildScanTab(window, startDir)),
		container.NewTabItem("Email Copy", buildEmailTab(window, startDir)),
		container.NewTabItem("About", buildAboutTab()),
	)
	tabs.SetTabLocation(container.TabLocationTop)

	window.SetContent(tabs)
	window.ShowAndRun()
	return nil
}

func buildScanTab(window fyne.Window, startDir string) fyne.CanvasObject {
	sourceEntry := widget.NewEntry()
	sourceEntry.SetText(startDir)

	outputEntry := widget.NewEntry()
	outputEntry.SetText(startDir)

	fileEntry := widget.NewEntry()
	fileEntry.SetText(defaultOutputFilename(startDir))

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
	resultLabel := widget.NewLabel("Run a scan to see the result summary here.")
	resultLabel.Wrapping = fyne.TextWrapWord

	startButton := widget.NewButton("Generate Content List", nil)
	useSourceButton := widget.NewButton("Use Source As Output", func() {
		outputEntry.SetText(sourceEntry.Text)
	})
	openOutputButton := widget.NewButton("Open Output Folder", func() {
		openPathInFileManager(outputEntry.Text)
	})
	openLatestButton := widget.NewButton("Open Latest Result", func() {})
	openLatestButton.Disable()

	latestPath := ""
	setRunning := func(running bool) {
		startButton.Disable()
		useSourceButton.Disable()
		if !running {
			startButton.Enable()
			useSourceButton.Enable()
		}
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
					latestPath = done.outputPath
					if done.xlsxPath != "" {
						latestPath = done.xlsxPath
					}
					openLatestButton.Enable()
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
	openLatestButton.OnTapped = func() {
		if latestPath != "" {
			openPathInFileManager(latestPath)
		}
	}

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
		openOutputButton,
		openLatestButton,
	)

	resultCard := widget.NewCard("Latest Scan Result", "The Go GUI uses the same core engine as the TUI.", container.NewVScroll(resultLabel))

	return container.NewBorder(
		container.NewVBox(
			widget.NewRichTextFromMarkdown("## Go Desktop GUI\n\nUse this mode on macOS/Linux when you want a native window on top of the same scan engine as the TUI."),
			statusLabel,
		),
		nil,
		nil,
		nil,
		container.NewVScroll(container.NewVBox(
			form,
			widget.NewSeparator(),
			options,
			widget.NewSeparator(),
			actions,
			widget.NewSeparator(),
			resultCard,
		)),
	)
}

func buildEmailTab(window fyne.Window, startDir string) fyne.CanvasObject {
	sourceEntry := widget.NewEntry()
	sourceEntry.SetText(startDir)

	destEntry := widget.NewEntry()
	destEntry.SetText(startDir)

	statusLabel := widget.NewLabel("Ready.")
	statusLabel.Wrapping = fyne.TextWrapWord
	resultLabel := widget.NewLabel("Run an email copy to see the manifest and destination summary here.")
	resultLabel.Wrapping = fyne.TextWrapWord

	startButton := widget.NewButton("Copy Email Files", nil)
	useSourceButton := widget.NewButton("Use Source As Destination", func() {
		destEntry.SetText(sourceEntry.Text)
	})
	openDestButton := widget.NewButton("Open Destination", func() {
		openPathInFileManager(destEntry.Text)
	})
	openManifestButton := widget.NewButton("Open Latest Manifest", func() {})
	openManifestButton.Disable()

	latestManifest := ""
	setRunning := func(running bool) {
		startButton.Disable()
		useSourceButton.Disable()
		if !running {
			startButton.Enable()
			useSourceButton.Enable()
		}
	}

	startButton.OnTapped = func() {
		sourceDir := strings.TrimSpace(sourceEntry.Text)
		destDir := strings.TrimSpace(destEntry.Text)
		if sourceDir == "" || destDir == "" {
			dialog.ShowError(fmt.Errorf("source folder and destination folder are required"), window)
			return
		}

		setRunning(true)
		statusLabel.SetText("Copying email files...")
		go func() {
			started := time.Now()
			manifestPath, copied, err := copyEmailFiles(sourceDir, destDir)
			fyne.Do(func() {
				setRunning(false)
				if err != nil {
					statusLabel.SetText("Email copy failed.")
					dialog.ShowError(err, window)
					return
				}
				latestManifest = manifestPath
				openManifestButton.Enable()
				statusLabel.SetText(fmt.Sprintf("Email copy complete. Copied %d files.", copied))
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
		openDestButton,
		openManifestButton,
	)

	resultCard := widget.NewCard("Latest Email Copy Result", "Relative folders are preserved from the chosen source root.", container.NewVScroll(resultLabel))

	return container.NewBorder(
		container.NewVBox(
			widget.NewRichTextFromMarkdown("## Email Copy\n\nThis desktop flow preserves the original relative folder structure and writes a manifest report in the destination."),
			statusLabel,
		),
		nil,
		nil,
		nil,
		container.NewVScroll(container.NewVBox(
			form,
			widget.NewSeparator(),
			widget.NewLabel("Extensions"),
			widget.NewLabel(strings.Join(sortedEmailExtensions(), ", ")),
			widget.NewSeparator(),
			actions,
			widget.NewSeparator(),
			resultCard,
		)),
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
		dialog.ShowFolderOpen(func(uri fyne.ListableURI, err error) {
			if err != nil {
				dialog.ShowError(err, window)
				return
			}
			if uri == nil {
				return
			}
			entry.SetText(uri.Path())
		}, window)
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
