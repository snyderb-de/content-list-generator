//go:build gui

package main

import (
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

func (f *forcedVariantTheme) Color(name fyne.ThemeColorName, _ fyne.ThemeVariant) color.Color {
	return f.Theme.Color(name, f.variant)
}

func launchGUI(startDir string) error {
	application := app.NewWithID("content-list-generator.gui")
	applySavedAppearance(application)

	window := application.NewWindow("Content List Generator")
	window.Resize(fyne.NewSize(1040, 780))

	tabs := container.NewAppTabs(
		container.NewTabItem("Content List", container.NewVScroll(buildScanTab(window, startDir))),
		container.NewTabItem("Copy Email Files", container.NewVScroll(buildEmailTab(window, startDir))),
		container.NewTabItem("About", container.NewVScroll(buildAboutTab())),
	)
	tabs.SetTabLocation(container.TabLocationTop)

	darkMode := widget.NewCheck("Dark mode", nil)
	darkMode.SetChecked(currentAppearanceMode(application) == "dark")
	darkMode.OnChanged = func(enabled bool) {
		mode := "light"
		if enabled {
			mode = "dark"
		}
		applyAppearance(application, mode, true)
	}

	header := container.NewPadded(
		container.NewHBox(
			layout.NewSpacer(),
			widget.NewLabel("Appearance"),
			darkMode,
		),
	)

	window.SetContent(container.NewBorder(header, nil, nil, nil, tabs))
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

	hashCheck := widget.NewCheck("Add SHA-256 hashes (advanced)", nil)
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
	progressBar := widget.NewProgressBarInfinite()
	progressBar.Hide()
	resultLabel := widget.NewLabel("Your results will appear here after the file list is finished.")
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
		statusLabel.SetText("Choose a folder to scan, then click Generate Content List.")
		resultLabel.SetText("Your results will appear here after the file list is finished.")
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
			statusLabel.SetText("Getting everything ready...")
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
								"Working... Files: %d  Folders: %d  Size: %s  Skipped: %d  Time: %s",
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
						statusLabel.SetText("Something went wrong while making the file list.")
						dialog.ShowError(err, window)
						return
					}
					statusLabel.SetText(fmt.Sprintf("Your file list is ready. %d files were included.", done.files))
					resultLabel.SetText(strings.Join([]string{
						fmt.Sprintf("Saved file list: %s", done.outputPath),
						fmt.Sprintf("Excel copy: %s", valueOrDefault(done.xlsxPath, "not created")),
						fmt.Sprintf("Files included: %d", done.files),
						fmt.Sprintf("Total size: %s", humanBytes(done.bytes)),
						fmt.Sprintf("Items skipped: %d", done.filtered),
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

	form := widget.NewForm(
		widget.NewFormItem("Folder to scan", pathInputRow(window, sourceEntry, "Choose Source Folder", true)),
		widget.NewFormItem("Save results to", pathInputRow(window, outputEntry, "Choose Output Folder", false)),
		widget.NewFormItem("Name for the saved list", fileEntry),
		widget.NewFormItem("Skip file types (optional)", excludeEntry),
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

	resultCard := widget.NewCard("Saved File List", "Use this area to review what was created and where it was saved.", resultLabel)

	return container.NewVBox(
		widget.NewRichTextFromMarkdown("## Create a Content List\n\nChoose a folder, choose where to save the results, and click **Generate Content List**. This can create a CSV file and, if you want, an Excel copy too."),
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

	statusLabel := widget.NewLabel("Choose a folder to search, then choose where the copied email files should go.")
	statusLabel.Wrapping = fyne.TextWrapWord
	progressBar := widget.NewProgressBar()
	progressBar.Min = 0
	progressBar.Max = 1
	progressDetails := widget.NewLabel("The app will look for supported email file types first, then copy the matches.")
	progressDetails.Wrapping = fyne.TextWrapWord
	resultLabel := widget.NewLabel("Your copy summary will appear here after the job is finished.")
	resultLabel.Wrapping = fyne.TextWrapWord

	startButton := widget.NewButton("Copy Email Files", nil)
	useSourceButton := widget.NewButton("Use Source As Destination", func() {
		destEntry.SetText(sourceEntry.Text)
	})
	resetButton := widget.NewButton("Reset", func() {
		sourceEntry.SetText(defaultSource)
		destEntry.SetText(defaultDest)
		progressBar.SetValue(0)
		progressBar.Max = 1
		statusLabel.SetText("Choose a folder to search, then choose where the copied email files should go.")
		progressDetails.SetText("The app will look for supported email file types first, then copy the matches.")
		resultLabel.SetText("Your copy summary will appear here after the job is finished.")
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
		progressBar.Max = 1

		setRunning(true)
		statusLabel.SetText("Looking for supported email files...")
		progressDetails.SetText("The app checks each file first, then copies the supported email files.")
		go func() {
			started := time.Now()
			manifestPath, copied, err := copyEmailFilesWithProgress(sourceDir, destDir, func(progress emailCopyProgress) {
				fyne.Do(func() {
					switch progress.Phase {
					case "scanning":
						progressBar.Max = float64(max(1, int(progress.Scanned)))
						progressBar.SetValue(float64(progress.Scanned))
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
					statusLabel.SetText("Something went wrong while copying the email files.")
					dialog.ShowError(err, window)
					return
				}
				latestManifest = manifestPath
				openManifestButton.Enable()
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

	form := widget.NewForm(
		widget.NewFormItem("Folder to search", pathInputRow(window, sourceEntry, "Choose Source Folder", true)),
		widget.NewFormItem("Copy files into", pathInputRow(window, destEntry, "Choose Destination Folder", false)),
	)

	actions := container.NewHBox(
		startButton,
		useSourceButton,
		resetButton,
		openDestButton,
		openManifestButton,
	)

	resultCard := widget.NewCard("Copy Summary", "The copied files keep the same folder layout they had in the original location.", resultLabel)

	return container.NewVBox(
		widget.NewRichTextFromMarkdown("## Copy Email Files\n\nChoose a folder to search, choose where the copied files should go, and the app will save a report of everything that was copied."),
		statusLabel,
		progressBar,
		progressDetails,
		widget.NewSeparator(),
		form,
		widget.NewSeparator(),
		widget.NewLabel("Supported email file types"),
		widget.NewLabel(strings.Join(sortedEmailExtensions(), ", ")),
		widget.NewSeparator(),
		actions,
		widget.NewSeparator(),
		resultCard,
	)
}

func buildAboutTab() fyne.CanvasObject {
	body := widget.NewRichTextFromMarkdown(strings.Join([]string{
		"## About Content List Generator",
		"",
		"Content List Generator helps you create a simple file list from a folder and copy supported email files into a new location.",
		"",
		"Written by Bryan Snyder.",
		"",
		fmt.Sprintf("GitHub: [placeholder link](%s)", placeholderGitHubURL),
		"",
		"Open source note:",
		"",
		"- This project is being prepared for an open source release.",
		"- TODO: decide the final attribution requirement before publishing.",
		"",
		"Helpful notes:",
		"",
		"- The content-list page creates a CSV file and can also make an Excel copy.",
		"- The email-copy page keeps the original folder layout and saves a report of what was copied.",
	}, "\n"))
	return container.New(layout.NewCenterLayout(), container.NewPadded(body))
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
	currentPath := normalizeFolderPath(startPath)
	places := folderPlaces()
	children := folderChildren(currentPath)

	titleLabel := widget.NewLabelWithStyle("Content List Generator", fyne.TextAlignLeading, fyne.TextStyle{Bold: true})
	pathLabel := widget.NewLabel(currentPath)
	pathLabel.Wrapping = fyne.TextWrapWord
	selectedLabel := widget.NewLabel("Current selected folder: " + currentPath)
	selectedLabel.Wrapping = fyne.TextWrapWord
	locationsLabel := widget.NewLabelWithStyle("LOCATIONS", fyne.TextAlignLeading, fyne.TextStyle{Bold: true})
	placesHint := widget.NewLabel("Places")
	placesHint.TextStyle = fyne.TextStyle{Italic: true}
	var placesList *widget.List

	refreshChildren := func() {}
	selectedPlace := -1
	refreshCurrentPath := func(path string) {
		currentPath = normalizeFolderPath(path)
		pathLabel.SetText(currentPath)
		selectedLabel.SetText("Current selected folder: " + currentPath)
		children = folderChildren(currentPath)
		selectedPlace = selectedPlaceIndex(places, currentPath)
		if selectedPlace >= 0 {
			placesList.Select(selectedPlace)
		} else {
			placesList.UnselectAll()
		}
		refreshChildren()
	}

	placesList = widget.NewList(
		func() int { return len(places) },
		func() fyne.CanvasObject {
			return container.NewHBox(
				widget.NewIcon(theme.FolderIcon()),
				widget.NewLabel("Place"),
			)
		},
		func(id widget.ListItemID, obj fyne.CanvasObject) {
			row := obj.(*fyne.Container)
			row.Objects[0].(*widget.Icon).SetResource(placeIcon(places[id].Name))
			row.Objects[1].(*widget.Label).SetText(places[id].Name)
		},
	)
	placesList.OnSelected = func(id widget.ListItemID) {
		if id >= 0 && id < len(places) {
			refreshCurrentPath(places[id].Path)
		}
	}

	childrenList := widget.NewList(
		func() int { return len(children) },
		func() fyne.CanvasObject {
			title := widget.NewLabel("Folder")
			subtitle := widget.NewLabel("")
			subtitle.TextStyle = fyne.TextStyle{Italic: true}
			subtitle.Wrapping = fyne.TextWrapWord
			return container.NewHBox(
				widget.NewIcon(theme.FolderIcon()),
				container.NewVBox(title, subtitle),
			)
		},
		func(id widget.ListItemID, obj fyne.CanvasObject) {
			row := obj.(*fyne.Container)
			row.Objects[0].(*widget.Icon).SetResource(folderChildIcon(children[id]))
			textBlock := row.Objects[1].(*fyne.Container)
			textBlock.Objects[0].(*widget.Label).SetText(children[id].Name)
			textBlock.Objects[1].(*widget.Label).SetText(children[id].Subtitle)
		},
	)
	refreshChildren = func() {
		childrenList.Refresh()
	}
	childrenList.OnSelected = func(id widget.ListItemID) {
		if id >= 0 && id < len(children) {
			refreshCurrentPath(children[id].Path)
		}
	}

	upButton := widget.NewButton("Up", func() {
		parent := filepath.Dir(currentPath)
		if parent == "" || parent == currentPath {
			return
		}
		refreshCurrentPath(parent)
	})

	newFolderButton := widget.NewButton("New Folder", func() {
		nameEntry := widget.NewEntry()
		nameEntry.SetPlaceHolder("Folder name")
		content := container.NewVBox(
			widget.NewLabel("Create a folder inside:"),
			widget.NewLabel(currentPath),
			widget.NewLabel(""),
			widget.NewLabel("Folder name"),
			nameEntry,
		)
		createDialog := dialog.NewCustomConfirm("New Folder", "Create Folder", "Cancel", content, func(ok bool) {
			if !ok {
				return
			}
			name := strings.TrimSpace(nameEntry.Text)
			if name == "" {
				dialog.ShowError(fmt.Errorf("folder name is required"), window)
				return
			}
			target := filepath.Join(currentPath, name)
			if err := os.MkdirAll(target, 0o755); err != nil {
				dialog.ShowError(err, window)
				return
			}
			refreshCurrentPath(target)
		}, window)
		createDialog.Resize(fyne.NewSize(520, 220))
		createDialog.Show()
		window.Canvas().Focus(nameEntry)
	})

	breadcrumb := container.NewHBox(
		widget.NewIcon(theme.FolderIcon()),
		widget.NewLabel(strings.Join(breadcrumbParts(currentPath), "  >  ")),
	)
	headerTop := container.NewBorder(nil, nil, nil, nil, titleLabel)
	headerBar := container.NewBorder(nil, nil, nil, container.NewHBox(upButton, newFolderButton), breadcrumb)
	header := container.NewVBox(headerTop, widget.NewSeparator(), headerBar)
	body := container.NewHSplit(
		container.NewBorder(container.NewVBox(locationsLabel, placesHint), nil, nil, nil, placesList),
		container.NewBorder(nil, nil, nil, nil, childrenList),
	)
	body.SetOffset(0.26)
	footer := container.NewBorder(nil, nil, widget.NewIcon(theme.InfoIcon()), nil, selectedLabel)
	content := container.NewBorder(header, footer, nil, nil, body)

	openDialog := dialog.NewCustomConfirm(title, "Open", "Cancel", content, func(ok bool) {
		if ok {
			onSelect(currentPath)
		}
	}, window)
	openDialog.Resize(fyne.NewSize(1250, 940))
	openDialog.Show()
	refreshCurrentPath(currentPath)
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
