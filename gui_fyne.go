//go:build gui

package main

import (
	"context"
	"errors"
	"fmt"
	"image/color"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"time"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/dialog"
	"fyne.io/fyne/v2/storage"
	"fyne.io/fyne/v2/layout"
	"fyne.io/fyne/v2/theme"
	"fyne.io/fyne/v2/widget"
)

type folderPlace struct {
	Name string
	Path string
}

type folderChild struct {
	Name     string
	Path     string
	Subtitle string
}

const placeholderGitHubURL = "https://github.com/placeholder/content-list-generator"
const appearancePreferenceKey = "appearance_mode"

type forcedVariantTheme struct {
	fyne.Theme
	variant fyne.ThemeVariant
}

type fixedSidebarLayout struct {
	SidebarWidth float32
	Padding      float32
	Gap          float32
}

func (l *fixedSidebarLayout) Layout(objects []fyne.CanvasObject, size fyne.Size) {
	if len(objects) < 2 {
		return
	}
	sidebar := objects[0]
	content := objects[1]
	innerHeight := maxFloat32(0, size.Height-(l.Padding*2))
	sidebar.Move(fyne.NewPos(l.Padding, l.Padding))
	sidebar.Resize(fyne.NewSize(l.SidebarWidth, innerHeight))

	contentX := l.Padding + l.SidebarWidth + l.Gap
	contentWidth := maxFloat32(0, size.Width-contentX-l.Padding)
	content.Move(fyne.NewPos(contentX, l.Padding))
	content.Resize(fyne.NewSize(contentWidth, innerHeight))
}

func (l *fixedSidebarLayout) MinSize(objects []fyne.CanvasObject) fyne.Size {
	if len(objects) < 2 {
		return fyne.NewSize(0, 0)
	}
	sidebarMin := objects[0].MinSize()
	contentMin := objects[1].MinSize()
	width := l.Padding + l.SidebarWidth + l.Gap + contentMin.Width + l.Padding
	height := maxFloat32(sidebarMin.Height, contentMin.Height) + (l.Padding * 2)
	return fyne.NewSize(width, height)
}

func (f *forcedVariantTheme) Color(name fyne.ThemeColorName, _ fyne.ThemeVariant) color.Color {
	switch f.variant {
	case theme.VariantDark:
		switch name {
		case theme.ColorNameBackground:
			return color.NRGBA{R: 0x18, G: 0x1f, B: 0x27, A: 0xff}
		case theme.ColorNameButton:
			return color.NRGBA{R: 0x26, G: 0x35, B: 0x43, A: 0xff}
		case theme.ColorNameDisabledButton:
			return color.NRGBA{R: 0x21, G: 0x30, B: 0x3d, A: 0xff}
		case theme.ColorNameDisabled:
			return color.NRGBA{R: 0x68, G: 0x7b, B: 0x8d, A: 0xff}
		case theme.ColorNameForeground:
			return color.NRGBA{R: 0xeb, G: 0xf1, B: 0xf7, A: 0xff}
		case theme.ColorNameForegroundOnPrimary:
			return color.NRGBA{R: 0xf8, G: 0xfb, B: 0xff, A: 0xff}
		case theme.ColorNameHeaderBackground:
			return color.NRGBA{R: 0x1b, G: 0x24, B: 0x2e, A: 0xff}
		case theme.ColorNameHover:
			return color.NRGBA{R: 0x2d, G: 0x3f, B: 0x52, A: 0xff}
		case theme.ColorNameInputBackground:
			return color.NRGBA{R: 0x1a, G: 0x23, B: 0x2d, A: 0xff}
		case theme.ColorNameInputBorder:
			return color.NRGBA{R: 0x31, G: 0x42, B: 0x54, A: 0xff}
		case theme.ColorNameMenuBackground, theme.ColorNameOverlayBackground:
			return color.NRGBA{R: 0x1d, G: 0x2a, B: 0x35, A: 0xff}
		case theme.ColorNamePlaceHolder:
			return color.NRGBA{R: 0x9c, G: 0xae, B: 0xbf, A: 0xff}
		case theme.ColorNamePressed:
			return color.NRGBA{R: 0x69, G: 0xa2, B: 0xff, A: 0x66}
		case theme.ColorNamePrimary, theme.ColorNameFocus, theme.ColorNameHyperlink:
			return color.NRGBA{R: 0x4d, G: 0x8e, B: 0xf8, A: 0xff}
		case theme.ColorNameScrollBar:
			return color.NRGBA{R: 0x69, G: 0xa2, B: 0xff, A: 0xbb}
		case theme.ColorNameScrollBarBackground:
			return color.NRGBA{R: 0x18, G: 0x26, B: 0x33, A: 0xff}
		case theme.ColorNameSelection:
			return color.NRGBA{R: 0x17, G: 0x34, B: 0x55, A: 0xff}
		case theme.ColorNameSeparator:
			return color.NRGBA{R: 0x12, G: 0x20, B: 0x2b, A: 0xff}
		case theme.ColorNameShadow:
			return color.NRGBA{R: 0x00, G: 0x00, B: 0x00, A: 0x33}
		}
	default:
		switch name {
		case theme.ColorNameBackground:
			return color.NRGBA{R: 0xe3, G: 0xeb, B: 0xf2, A: 0xff}
		case theme.ColorNameButton:
			return color.NRGBA{R: 0xff, G: 0xff, B: 0xff, A: 0xff}
		case theme.ColorNameDisabledButton:
			return color.NRGBA{R: 0xf4, G: 0xf7, B: 0xfa, A: 0xff}
		case theme.ColorNameDisabled:
			return color.NRGBA{R: 0x92, G: 0xa1, B: 0xae, A: 0xff}
		case theme.ColorNameForeground:
			return color.NRGBA{R: 0x24, G: 0x38, B: 0x49, A: 0xff}
		case theme.ColorNameForegroundOnPrimary:
			return color.NRGBA{R: 0xff, G: 0xff, B: 0xff, A: 0xff}
		case theme.ColorNameHeaderBackground:
			return color.NRGBA{R: 0xea, G: 0xf0, B: 0xf5, A: 0xff}
		case theme.ColorNameHover:
			return color.NRGBA{R: 0xd7, G: 0xe1, B: 0xea, A: 0xff}
		case theme.ColorNameInputBackground:
			return color.NRGBA{R: 0xff, G: 0xff, B: 0xff, A: 0xff}
		case theme.ColorNameInputBorder:
			return color.NRGBA{R: 0xca, G: 0xd6, B: 0xe0, A: 0xff}
		case theme.ColorNameMenuBackground, theme.ColorNameOverlayBackground:
			return color.NRGBA{R: 0xff, G: 0xff, B: 0xff, A: 0xff}
		case theme.ColorNamePlaceHolder:
			return color.NRGBA{R: 0x55, G: 0x67, B: 0x78, A: 0xff}
		case theme.ColorNamePressed:
			return color.NRGBA{R: 0x00, G: 0x70, B: 0xeb, A: 0x44}
		case theme.ColorNamePrimary, theme.ColorNameFocus, theme.ColorNameHyperlink:
			return color.NRGBA{R: 0x00, G: 0x5b, B: 0xc1, A: 0xff}
		case theme.ColorNameScrollBar:
			return color.NRGBA{R: 0x00, G: 0x5b, B: 0xc1, A: 0xbb}
		case theme.ColorNameScrollBarBackground:
			return color.NRGBA{R: 0xf3, G: 0xf6, B: 0xf9, A: 0xff}
		case theme.ColorNameSelection:
			return color.NRGBA{R: 0xd7, G: 0xe7, B: 0xff, A: 0xff}
		case theme.ColorNameSeparator:
			return color.NRGBA{R: 0xf2, G: 0xf4, B: 0xf6, A: 0xff}
		case theme.ColorNameShadow:
			return color.NRGBA{R: 0x19, G: 0x1c, B: 0x1e, A: 0x10}
		}
	}
	return f.Theme.Color(name, f.variant)
}

func launchGUI(startDir string) error {
	application := app.NewWithID("content-list-generator.gui")
	applySavedAppearance(application)

	window := application.NewWindow("Content List Generator")
	window.Resize(fyne.NewSize(1280, 860))

	contentPage := container.NewVScroll(buildScanTab(window, startDir))
	emailPage := container.NewVScroll(buildEmailTab(window, startDir))
	aboutPage := container.NewVScroll(buildAboutTab())
	pages := map[string]fyne.CanvasObject{
		"content": contentPage,
		"email":   emailPage,
		"about":   aboutPage,
	}
	contentStack := container.NewStack(contentPage, emailPage, aboutPage)

	var contentButton, emailButton, aboutButton *widget.Button
	setPage := func(page string) {
		for name, view := range pages {
			if name == page {
				view.Show()
			} else {
				view.Hide()
			}
		}
		for name, button := range map[string]*widget.Button{
			"content": contentButton,
			"email":   emailButton,
			"about":   aboutButton,
		} {
			if button == nil {
				continue
			}
			if name == page {
				button.Importance = widget.HighImportance
			} else {
				button.Importance = widget.LowImportance
			}
			button.Refresh()
		}
	}

	brandTitle := widget.NewLabelWithStyle("Content List Generator", fyne.TextAlignLeading, fyne.TextStyle{Bold: true})
	brandSubtitle := widget.NewLabel("Create file lists, copy email files, and keep a simple record of what was saved.")
	brandSubtitle.Wrapping = fyne.TextWrapWord
	brandCard := widget.NewCard("", "", container.NewVBox(brandTitle, brandSubtitle))

	contentButton = widget.NewButtonWithIcon("Content List", theme.DocumentIcon(), func() {
		setPage("content")
	})
	contentButton.Alignment = widget.ButtonAlignLeading
	contentButton.Importance = widget.HighImportance

	emailButton = widget.NewButtonWithIcon("Copy Email Files", theme.MailComposeIcon(), func() {
		setPage("email")
	})
	emailButton.Alignment = widget.ButtonAlignLeading
	emailButton.Importance = widget.LowImportance

	aboutButton = widget.NewButtonWithIcon("About", theme.InfoIcon(), func() {
		setPage("about")
	})
	aboutButton.Alignment = widget.ButtonAlignLeading
	aboutButton.Importance = widget.LowImportance

	darkMode := widget.NewCheck("Dark mode", nil)
	darkMode.SetChecked(currentAppearanceMode(application) == "dark")
	darkMode.OnChanged = func(enabled bool) {
		mode := "light"
		if enabled {
			mode = "dark"
		}
		applyAppearance(application, mode, true)
	}
	appearanceCard := widget.NewCard(
		"Appearance",
		"The same tools are available in light and dark mode.",
		container.NewVBox(darkMode),
	)

	sidebar := container.NewPadded(
		container.NewBorder(
			brandCard,
			appearanceCard,
			nil,
			nil,
			container.NewVBox(contentButton, emailButton, aboutButton, layout.NewSpacer()),
		),
	)

	mainArea := container.NewPadded(contentStack)
	window.SetContent(container.New(
		&fixedSidebarLayout{
			SidebarWidth: 312,
			Padding:      28,
			Gap:          24,
		},
		sidebar,
		mainArea,
	))
	setPage("content")
	window.ShowAndRun()
	return nil
}

func applySavedAppearance(application fyne.App) {
	mode := strings.ToLower(strings.TrimSpace(application.Preferences().String(appearancePreferenceKey)))
	if mode != "dark" && mode != "light" {
		return
	}
	applyAppearance(application, mode, false)
}

func currentAppearanceMode(application fyne.App) string {
	mode := strings.ToLower(strings.TrimSpace(application.Preferences().String(appearancePreferenceKey)))
	if mode == "dark" || mode == "light" {
		return mode
	}
	if application.Settings().ThemeVariant() == theme.VariantDark {
		return "dark"
	}
	return "light"
}

func applyAppearance(application fyne.App, mode string, persist bool) {
	variant := theme.VariantLight
	if mode == "dark" {
		variant = theme.VariantDark
	}
	application.Settings().SetTheme(&forcedVariantTheme{
		Theme:   theme.DefaultTheme(),
		variant: variant,
	})
	if persist {
		application.Preferences().SetString(appearancePreferenceKey, mode)
	}
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

	hashSelect := widget.NewSelect(hashAlgorithmOptionLabels(), nil)
	hashSelect.SetSelected(defaultHashAlgorithm().OptionLabel())
	hiddenCheck := widget.NewCheck("Skip hidden files", nil)
	systemCheck := widget.NewCheck("Skip common system files", nil)
	xlsxCheck := widget.NewCheck("Also save an Excel copy", nil)
	zeroCheck := widget.NewCheck("Keep leading zeros in Excel", nil)
	zeroCheck.Disable()
	xlsxCheck.OnChanged = func(checked bool) {
		if checked {
			zeroCheck.Enable()
			return
		}
		zeroCheck.SetChecked(false)
		zeroCheck.Disable()
	}

	statusLabel := widget.NewLabel("Choose a folder to scan, then click Generate Content List.")
	statusLabel.Wrapping = fyne.TextWrapWord
	progressBar := widget.NewProgressBar()
	progressBar.Min = 0
	progressBar.Max = 1
	progressBar.Hide()
	resultLabel := widget.NewLabel("Your results will appear here after the file list is finished.")
	resultLabel.Wrapping = fyne.TextWrapWord
	filesMetric := widget.NewLabel("0")
	filesMetric.TextStyle = fyne.TextStyle{Bold: true}
	skippedMetric := widget.NewLabel("0")
	skippedMetric.TextStyle = fyne.TextStyle{Bold: true}
	savedMetric := widget.NewLabel("Waiting")
	savedMetric.TextStyle = fyne.TextStyle{Bold: true}

	startButton := widget.NewButton("Generate Content List", nil)
	startButton.Importance = widget.HighImportance
	stopButton := widget.NewButton("Stop Scan", func() {
		if cancelActiveScan() {
			statusLabel.SetText("Stopping scan...")
		}
	})
	stopButton.Importance = widget.WarningImportance
	stopButton.Disable()
	useSourceButton := widget.NewButton("Use Source As Output", func() {
		outputEntry.SetText(sourceEntry.Text)
	})
	useSourceButton.Importance = widget.LowImportance
	resetButton := widget.NewButton("Reset", func() {
		sourceEntry.SetText(defaultSource)
		outputEntry.SetText(defaultOutput)
		fileEntry.SetText(defaultFilename)
		excludeEntry.SetText("")
		hashSelect.SetSelected(defaultHashAlgorithm().OptionLabel())
		hiddenCheck.SetChecked(false)
		systemCheck.SetChecked(false)
		xlsxCheck.SetChecked(false)
		zeroCheck.SetChecked(false)
		progressBar.Hide()
		progressBar.SetValue(0)
		statusLabel.SetText("Choose a folder to scan, then click Generate Content List.")
		resultLabel.SetText("Your results will appear here after the file list is finished.")
		filesMetric.SetText("0")
		skippedMetric.SetText("0")
		savedMetric.SetText("Waiting")
	})
	resetButton.Importance = widget.LowImportance
	openOutputButton := widget.NewButton("Open Output Folder", func() {
		openPathInFileManager(outputEntry.Text)
	})
	openOutputButton.Importance = widget.LowImportance
	setRunning := func(running bool) {
		if running {
			startButton.Disable()
			stopButton.Enable()
			useSourceButton.Disable()
			resetButton.Disable()
			progressBar.Show()
			progressBar.SetValue(0)
			return
		}
		startButton.Enable()
		stopButton.Disable()
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
			statusLabel.SetText("Getting everything ready...")
			filesMetric.SetText("0")
			skippedMetric.SetText("0")
			savedMetric.SetText("Working")
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
						progressLine := fmt.Sprintf(
							"%s... Files: %d  Folders: %d  Size: %s  Skipped: %d  Time: %s",
							progressPhaseLabel(stats.phase),
							stats.files,
							stats.directories,
							humanBytes(stats.bytes),
							stats.filtered,
							time.Since(stats.startedAt).Round(time.Second),
						)
						if stats.phase == progressPhaseScanning && stats.totalFiles > 0 {
							progressLine = fmt.Sprintf(
								"%s... %s complete  Files: %d/%d  Folders: %d/%d  Size: %s/%s  Skipped: %d  ETA: %s  Current: %s",
								progressPhaseLabel(stats.phase),
								formatPercent(progressFraction(stats)),
								stats.files,
								stats.totalFiles,
								stats.directories,
								stats.totalDirectories,
								humanBytes(stats.bytes),
								humanBytes(stats.totalBytes),
								stats.filtered,
								valueOrDefaultDuration(progressETA(stats, time.Now()), "calculating"),
								valueOrDefault(stats.currentItem, "waiting for first file"),
							)
						}
						fyne.Do(func() {
							if stats.phase == progressPhaseScanning {
								progressBar.SetValue(progressFraction(stats))
							}
							statusLabel.SetText(progressLine)
						})
					}
				}
			}()

			go func() {
				done, err := runScan(sourceDir, outputPath, scanOptions{
					HashAlgorithm: parseHashAlgorithm(hashSelect.Selected),
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
						if errors.Is(err, context.Canceled) {
							statusLabel.SetText("Scan stopped. Partial output was removed.")
							resultLabel.SetText("Scan stopped before completion.")
							savedMetric.SetText("Stopped")
							return
						}
						statusLabel.SetText("Something went wrong while making the file list.")
						dialog.ShowError(err, window)
						return
					}
					filesMetric.SetText(strconv.FormatUint(done.files, 10))
					skippedMetric.SetText(strconv.FormatUint(done.filtered, 10))
					if done.xlsxPath != "" {
						savedMetric.SetText("CSV + Report + Excel")
					} else {
						savedMetric.SetText("CSV + Report")
					}
					progressBar.SetValue(1)
					statusLabel.SetText(fmt.Sprintf("Your file list is ready. %d files were included.", done.files))
					resultLabel.SetText(strings.Join([]string{
						fmt.Sprintf("Selected folder: %s", done.sourceName),
						fmt.Sprintf("Saved file list: %s", filepath.Base(done.outputPath)),
						fmt.Sprintf("Excel copy: %s", baseNameOrFallback(done.xlsxPath, "not created")),
						fmt.Sprintf("Summary report: %s", baseNameOrFallback(done.reportPath, "not created")),
						fmt.Sprintf("Files included: %d", done.files),
						fmt.Sprintf("Total size: %s", humanBytes(done.bytes)),
						fmt.Sprintf("Items skipped: %d", done.filtered),
						fmt.Sprintf("Verification hash: %s", done.hashAlgorithm.OptionLabel()),
						fmt.Sprintf("First file in CSV: %s", valueOrDefault(done.firstCSVItem, "none")),
						fmt.Sprintf("Last file in CSV: %s", valueOrDefault(done.lastCSVItem, "none")),
						fmt.Sprintf("Finished in: %s", done.elapsed.Round(time.Millisecond)),
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

	pathGrid := container.NewGridWithColumns(
		2,
		makeDetailCard(
			"Folder to scan",
			"Choose the folder you want the app to scan.",
			pathInputRow(window, sourceEntry, "Choose Source Folder", true),
		),
		makeDetailCard(
			"Save results to",
			"Choose where the CSV file should be saved.",
			pathInputRow(window, outputEntry, "Choose Output Folder", false),
		),
	)

	outputDetails := widget.NewCard(
		"Output details",
		"Set the saved file name and any file types you want the app to skip.",
		container.NewGridWithColumns(
			2,
			makeLabeledField("Name for the saved list", "The file name should end in .csv.", fileEntry),
			makeLabeledField("Skip file types (optional)", "Example: tmp,log,bak", excludeEntry),
		),
	)

	options := widget.NewCard(
		"Options",
		"Choose any extras you want before you generate the file list.",
		container.NewGridWithColumns(
			2,
			makeSelectCard("Verification hash", "Choose how strongly the app verifies files later.", hashSelect),
			makeCheckCard(hiddenCheck, "Skip hidden files"),
			makeCheckCard(systemCheck, "Skip common system files"),
			makeCheckCard(xlsxCheck, "Also save an Excel copy"),
			makeCheckCard(zeroCheck, "Keep leading zeros in Excel"),
		),
	)

	actions := container.NewHBox(
		startButton,
		stopButton,
		useSourceButton,
		resetButton,
		openOutputButton,
	)

	progressCard := widget.NewCard(
		"Progress",
		"Watch the scan as the app works through the folder.",
		container.NewVBox(
			container.NewGridWithColumns(
				3,
				makeMetricCard("Files Included", filesMetric),
				makeMetricCard("Items Skipped", skippedMetric),
				makeMetricCard("Saved Output", savedMetric),
			),
			progressBar,
			statusLabel,
		),
	)

	resultCard := widget.NewCard("Summary", "Review what was created and where it was saved.", resultLabel)

	return container.NewVBox(
		makeHeroCard(
			"Create a Content List",
			"Choose a folder, choose where to save the results, and click Generate Content List.",
		),
		pathGrid,
		outputDetails,
		options,
		widget.NewCard("", "", actions),
		progressCard,
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

	statusLabel := widget.NewLabel("Choose a folder to search, then choose where the copied email files should go.")
	statusLabel.Wrapping = fyne.TextWrapWord
	scanProgress := widget.NewProgressBarInfinite()
	scanProgress.Hide()
	progressBar := widget.NewProgressBar()
	progressBar.Min = 0
	progressBar.Max = 1
	progressBar.Hide()
	progressDetails := widget.NewLabel("The app will look for supported email file types first, then copy the matches.")
	progressDetails.Wrapping = fyne.TextWrapWord
	resultLabel := widget.NewLabel("Your copy summary will appear here after the job is finished.")
	resultLabel.Wrapping = fyne.TextWrapWord
	phaseMetric := widget.NewLabel("Idle")
	phaseMetric.TextStyle = fyne.TextStyle{Bold: true}
	scannedMetric := widget.NewLabel("0")
	scannedMetric.TextStyle = fyne.TextStyle{Bold: true}
	copiedMetric := widget.NewLabel("0")
	copiedMetric.TextStyle = fyne.TextStyle{Bold: true}

	startButton := widget.NewButton("Copy Email Files", nil)
	startButton.Importance = widget.HighImportance
	useSourceButton := widget.NewButton("Use Source As Destination", func() {
		destEntry.SetText(sourceEntry.Text)
	})
	useSourceButton.Importance = widget.LowImportance
	resetButton := widget.NewButton("Reset", func() {
		sourceEntry.SetText(defaultSource)
		destEntry.SetText(defaultDest)
		progressBar.SetValue(0)
		progressBar.Max = 1
		progressBar.Hide()
		scanProgress.Hide()
		statusLabel.SetText("Choose a folder to search, then choose where the copied email files should go.")
		progressDetails.SetText("The app will look for supported email file types first, then copy the matches.")
		resultLabel.SetText("Your copy summary will appear here after the job is finished.")
		phaseMetric.SetText("Idle")
		scannedMetric.SetText("0")
		copiedMetric.SetText("0")
	})
	resetButton.Importance = widget.LowImportance
	openDestButton := widget.NewButton("Open Destination", func() {
		openPathInFileManager(destEntry.Text)
	})
	openDestButton.Importance = widget.LowImportance
	openManifestButton := widget.NewButton("Open Manifest", func() {})
	openManifestButton.Importance = widget.LowImportance
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
		progressBar.Max = 1

		setRunning(true)
		statusLabel.SetText("Looking for supported email files...")
		progressDetails.SetText("The app checks each file first, then copies the supported email files.")
		phaseMetric.SetText("Scanning")
		scannedMetric.SetText("0")
		copiedMetric.SetText("0")
		progressBar.Hide()
		scanProgress.Show()
		go func() {
			started := time.Now()
			manifestPath, copied, err := copyEmailFilesWithProgress(sourceDir, destDir, func(progress emailCopyProgress) {
				fyne.Do(func() {
					switch progress.Phase {
					case "scanning":
						phaseMetric.SetText("Scanning")
						scannedMetric.SetText(strconv.FormatUint(progress.Scanned, 10))
						copiedMetric.SetText(strconv.FormatUint(progress.Copied, 10))
						progressBar.Hide()
						scanProgress.Show()
						statusLabel.SetText(fmt.Sprintf(
							"Checking files... Looked at: %d  Matches found: %d",
							progress.Scanned,
							progress.Matched,
						))
						if progress.CurrentName != "" {
							progressDetails.SetText("Checking: " + progress.CurrentName)
						} else {
							progressDetails.SetText("Looking for supported email file types...")
						}
					case "copying":
						phaseMetric.SetText("Copying")
						scannedMetric.SetText(strconv.FormatUint(progress.Scanned, 10))
						copiedMetric.SetText(strconv.FormatUint(progress.Copied, 10))
						scanProgress.Hide()
						progressBar.Show()
						total := float64(max(1, int(progress.Total)))
						progressBar.Max = total
						progressBar.SetValue(float64(progress.Copied))
						if progress.Total == 0 {
							statusLabel.SetText(fmt.Sprintf("Finished checking %d files. No supported email files were found.", progress.Scanned))
							progressDetails.SetText("Nothing matched the supported email file types.")
							return
						}
						statusLabel.SetText(fmt.Sprintf(
							"Copying files... %d of %d finished after checking %d files",
							progress.Copied,
							progress.Total,
							progress.Scanned,
						))
						if progress.CurrentRel != "" {
							progressDetails.SetText("Current file: " + progress.CurrentRel)
						} else {
							progressDetails.SetText(fmt.Sprintf("Found %d supported email files. Starting the copy now.", progress.Total))
						}
					}
				})
			})
			fyne.Do(func() {
				setRunning(false)
				if err != nil {
					scanProgress.Hide()
					progressBar.Hide()
					phaseMetric.SetText("Error")
					statusLabel.SetText("Something went wrong while copying the email files.")
					dialog.ShowError(err, window)
					return
				}
				latestManifest = manifestPath
				openManifestButton.Enable()
				scanProgress.Hide()
				progressBar.Show()
				progressBar.Max = 1
				progressBar.SetValue(1)
				phaseMetric.SetText("Complete")
				copiedMetric.SetText(strconv.FormatUint(copied, 10))
				statusLabel.SetText(fmt.Sprintf("Done. Copied %d email files.", copied))
				progressDetails.SetText("A report was saved and the original folder layout was kept.")
				resultLabel.SetText(strings.Join([]string{
					fmt.Sprintf("Searched folder: %s", sourceDir),
					fmt.Sprintf("Copied files to: %s", destDir),
					fmt.Sprintf("Report saved to: %s", manifestPath),
					fmt.Sprintf("Email files copied: %d", copied),
					fmt.Sprintf("Finished in: %s", time.Since(started).Round(time.Millisecond)),
					"",
					"Supported email file types:",
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

	pathGrid := container.NewGridWithColumns(
		2,
		makeDetailCard(
			"Folder to search",
			"Choose the folder the app should check for supported email files.",
			pathInputRow(window, sourceEntry, "Choose Source Folder", true),
		),
		makeDetailCard(
			"Copy files into",
			"Choose where the copied files and the report should be saved.",
			pathInputRow(window, destEntry, "Choose Destination Folder", false),
		),
	)
	extensionCard := widget.NewCard(
		"Supported email file types",
		"The app checks for these file types before it starts copying.",
		widget.NewLabel(strings.Join(sortedEmailExtensions(), ", ")),
	)

	actions := container.NewHBox(
		startButton,
		useSourceButton,
		resetButton,
		openDestButton,
		openManifestButton,
	)

	progressCard := widget.NewCard(
		"Progress",
		"Watch the search first, then the copy.",
		container.NewVBox(
			container.NewGridWithColumns(
				3,
				makeMetricCard("Current phase", phaseMetric),
				makeMetricCard("Files checked", scannedMetric),
				makeMetricCard("Files copied", copiedMetric),
			),
			scanProgress,
			progressBar,
			statusLabel,
			progressDetails,
		),
	)
	resultCard := widget.NewCard("Copy Summary", "The copied files keep the same folder layout they had in the original location.", resultLabel)

	return container.NewVBox(
		makeHeroCard(
			"Copy Email Files",
			"Choose a folder to search, choose where the copied files should go, and the app will save a report of everything that was copied.",
		),
		pathGrid,
		extensionCard,
		widget.NewCard("", "", actions),
		progressCard,
		resultCard,
	)
}

func buildAboutTab() fyne.CanvasObject {
	description := widget.NewLabel("Content List Generator helps you create a simple file list from a folder and copy supported email files into a new location.")
	description.Wrapping = fyne.TextWrapWord
	githubLabel := widget.NewLabel("GitHub: " + placeholderGitHubURL)
	githubLabel.Wrapping = fyne.TextWrapWord
	openGitHub := widget.NewButton("Open GitHub Link", func() {
		openURLInBrowser(placeholderGitHubURL)
	})
	openGitHub.Importance = widget.LowImportance
	aboutCard := widget.NewCard(
		"About Content List Generator",
		"",
		container.NewVBox(
			description,
			widget.NewLabel("Written by Bryan Snyder"),
			githubLabel,
			openGitHub,
		),
	)
	openSourceNote := widget.NewCard(
		"Open source note",
		"",
		container.NewVBox(
			widget.NewLabel("This project is being prepared for an open source release."),
			widget.NewLabel("TODO: decide the final attribution requirement before publishing."),
		),
	)
	return container.NewVBox(aboutCard, openSourceNote)
}

func makeHeroCard(title, subtitle string) fyne.CanvasObject {
	titleLabel := widget.NewLabelWithStyle(title, fyne.TextAlignLeading, fyne.TextStyle{Bold: true})
	subtitleLabel := widget.NewLabel(subtitle)
	subtitleLabel.Wrapping = fyne.TextWrapWord
	return widget.NewCard("", "", container.NewVBox(titleLabel, subtitleLabel))
}

func makeDetailCard(title, subtitle string, content fyne.CanvasObject) fyne.CanvasObject {
	return widget.NewCard(title, subtitle, content)
}

func makeLabeledField(title, hint string, field fyne.CanvasObject) fyne.CanvasObject {
	hintLabel := widget.NewLabel(hint)
	hintLabel.Wrapping = fyne.TextWrapWord
	return container.NewVBox(
		widget.NewLabelWithStyle(title, fyne.TextAlignLeading, fyne.TextStyle{Bold: true}),
		field,
		hintLabel,
	)
}

func makeCheckCard(check *widget.Check, subtitle string) fyne.CanvasObject {
	hintLabel := widget.NewLabel(subtitle)
	hintLabel.Wrapping = fyne.TextWrapWord
	return widget.NewCard("", "", container.NewVBox(check, hintLabel))
}

func makeSelectCard(title, subtitle string, selectWidget *widget.Select) fyne.CanvasObject {
	hintLabel := widget.NewLabel(subtitle)
	hintLabel.Wrapping = fyne.TextWrapWord
	return widget.NewCard("", "", container.NewVBox(
		widget.NewLabelWithStyle(title, fyne.TextAlignLeading, fyne.TextStyle{Bold: true}),
		selectWidget,
		hintLabel,
	))
}

func makeMetricCard(title string, value *widget.Label) fyne.CanvasObject {
	return widget.NewCard(title, "", value)
}

func valueOrDefaultDuration(value time.Duration, fallback string) string {
	if value <= 0 {
		return fallback
	}
	return value.Round(time.Second).String()
}

func pathInputRow(window fyne.Window, entry *widget.Entry, title string, mustExist bool) fyne.CanvasObject {
	browse := widget.NewButton("Browse", func() {
		showFolderPicker(window, title, entry.Text, mustExist, func(path string) {
			entry.SetText(path)
		})
	})
	return container.NewBorder(nil, nil, nil, browse, entry)
}

func showFolderPicker(window fyne.Window, title, startPath string, _ bool, onSelect func(string)) {
	openDialog := dialog.NewFolderOpen(func(uri fyne.ListableURI, err error) {
		if err != nil {
			dialog.ShowError(err, window)
			return
		}
		if uri == nil {
			return
		}
		selected := strings.TrimPrefix(uri.String(), "file://")
		onSelect(normalizeFolderPath(selected))
	}, window)
	openDialog.SetTitle(title)
	start := normalizeFolderPath(startPath)
	if start != "" {
		startURI, err := storage.ListerForURI(storage.NewFileURI(start))
		if err == nil {
			openDialog.SetLocation(startURI)
		}
	}
	openDialog.Show()
}

func normalizeFolderPath(path string) string {
	clean := strings.TrimSpace(path)
	if clean == "" {
		if home, err := os.UserHomeDir(); err == nil {
			return home
		}
		return string(filepath.Separator)
	}
	abs, err := filepath.Abs(clean)
	if err != nil {
		return clean
	}
	if info, err := os.Stat(abs); err == nil && info.IsDir() {
		return abs
	}
	parent := filepath.Dir(abs)
	if info, err := os.Stat(parent); err == nil && info.IsDir() {
		return parent
	}
	return abs
}

func folderChildren(currentPath string) []folderChild {
	parent := filepath.Dir(currentPath)
	children := make([]folderChild, 0, 32)
	if parent != "" && parent != currentPath {
		children = append(children, folderChild{
			Name:     "(Parent)",
			Path:     parent,
			Subtitle: "Back to " + filepath.Base(parent),
		})
	}

	entries, err := os.ReadDir(currentPath)
	if err != nil {
		return children
	}
	for _, item := range entries {
		if !item.IsDir() {
			continue
		}
		name := item.Name()
		if strings.HasPrefix(name, ".") {
			continue
		}
		children = append(children, folderChild{
			Name:     name,
			Path:     filepath.Join(currentPath, name),
			Subtitle: folderDirectorySubtitle(filepath.Join(currentPath, name)),
		})
	}
	sort.Slice(children, func(i, j int) bool {
		return strings.ToLower(children[i].Name) < strings.ToLower(children[j].Name)
	})
	return children
}

func folderDirectorySubtitle(path string) string {
	entries, err := os.ReadDir(path)
	if err != nil {
		return "Restricted access"
	}
	count := 0
	for _, entry := range entries {
		if strings.HasPrefix(entry.Name(), ".") {
			continue
		}
		count++
	}
	label := "items"
	if count == 1 {
		label = "item"
	}
	return strconv.Itoa(count) + " " + label
}

func folderPlaces() []folderPlace {
	places := make([]folderPlace, 0, 12)
	addPlace := func(name, path string) {
		if strings.TrimSpace(path) == "" {
			return
		}
		info, err := os.Stat(path)
		if err != nil || !info.IsDir() {
			return
		}
		for _, existing := range places {
			if existing.Path == path {
				return
			}
		}
		places = append(places, folderPlace{Name: name, Path: path})
	}

	if home, err := os.UserHomeDir(); err == nil {
		addPlace("Home", home)
		addPlace("Desktop", filepath.Join(home, "Desktop"))
		addPlace("Documents", filepath.Join(home, "Documents"))
		addPlace("Downloads", filepath.Join(home, "Downloads"))
	}
	addPlace("Computer", string(filepath.Separator))

	for _, drive := range mountedDrivePlaces() {
		addPlace(drive.Name, drive.Path)
	}

	return places
}

func mountedDrivePlaces() []folderPlace {
	places := make([]folderPlace, 0, 8)
	switch runtime.GOOS {
	case "darwin":
		entries, err := os.ReadDir("/Volumes")
		if err != nil {
			return places
		}
		for _, entry := range entries {
			if !entry.IsDir() {
				continue
			}
			name := entry.Name()
			if strings.HasPrefix(name, ".") {
				continue
			}
			places = append(places, folderPlace{
				Name: name,
				Path: filepath.Join("/Volumes", name),
			})
		}
	case "linux":
		for _, root := range []string{"/media", "/run/media", "/mnt"} {
			entries, err := os.ReadDir(root)
			if err != nil {
				continue
			}
			for _, entry := range entries {
				if !entry.IsDir() {
					continue
				}
				full := filepath.Join(root, entry.Name())
				if root == "/media" || root == "/run/media" {
					subEntries, err := os.ReadDir(full)
					if err == nil {
						for _, sub := range subEntries {
							if sub.IsDir() {
								places = append(places, folderPlace{
									Name: sub.Name(),
									Path: filepath.Join(full, sub.Name()),
								})
							}
						}
						continue
					}
				}
				places = append(places, folderPlace{
					Name: entry.Name(),
					Path: full,
				})
			}
		}
	}
	sort.Slice(places, func(i, j int) bool {
		return strings.ToLower(places[i].Name) < strings.ToLower(places[j].Name)
	})
	return places
}

func breadcrumbParts(path string) []string {
	clean := filepath.Clean(path)
	parts := make([]string, 0, 8)
	if runtime.GOOS == "darwin" && strings.HasPrefix(clean, "/Volumes/") {
		parts = append(parts, "Volumes")
	}
	for _, part := range strings.Split(clean, string(filepath.Separator)) {
		if strings.TrimSpace(part) == "" {
			continue
		}
		if runtime.GOOS == "darwin" && part == "Volumes" && len(parts) > 0 && parts[0] == "Volumes" {
			continue
		}
		parts = append(parts, part)
	}
	if len(parts) == 0 {
		return []string{string(filepath.Separator)}
	}
	return parts
}

func selectedPlaceIndex(places []folderPlace, currentPath string) int {
	bestIdx := -1
	bestLen := -1
	for i, place := range places {
		if currentPath == place.Path || isPathWithin(currentPath, place.Path) {
			if len(place.Path) > bestLen {
				bestIdx = i
				bestLen = len(place.Path)
			}
		}
	}
	return bestIdx
}

func placeIcon(name string) fyne.Resource {
	switch strings.ToLower(name) {
	case "home":
		return theme.HomeIcon()
	case "desktop":
		return theme.ComputerIcon()
	case "documents", "downloads":
		return theme.DocumentIcon()
	case "computer":
		return theme.StorageIcon()
	default:
		return theme.StorageIcon()
	}
}

func folderChildIcon(child folderChild) fyne.Resource {
	if child.Name == "(Parent)" {
		return theme.NavigateBackIcon()
	}
	return theme.FolderIcon()
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

func openURLInBrowser(url string) {
	if strings.TrimSpace(url) == "" {
		return
	}

	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("open", url)
	case "linux":
		cmd = exec.Command("xdg-open", url)
	default:
		return
	}
	_ = cmd.Start()
}

func maxFloat32(a, b float32) float32 {
	if a > b {
		return a
	}
	return b
}
