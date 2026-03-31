package main

import (
	"bufio"
	"context"
	"crypto/sha256"
	"encoding/csv"
	"encoding/hex"
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

	"github.com/charmbracelet/bubbles/key"
	"github.com/charmbracelet/bubbles/list"
	"github.com/charmbracelet/bubbles/spinner"
	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/glamour"
	"github.com/charmbracelet/lipgloss"
	"github.com/xuri/excelize/v2"
)

type stage int

const (
	stageHome stage = iota
	stagePickSource
	stagePickOutputDir
	stageSetOutput
	stageConfirmOverwrite
	stageScanning
	stageEmailPickSource
	stageEmailPickDest
	stageEmailCopying
	stageDone
	stageFailed
)

const (
	focusFileName = iota
	focusExcludeExts
	focusHashing
	focusHidden
	focusSystem
	focusXLSX
	focusPreserveZeros
	focusStart
	focusCount
)

type flowMode int

const (
	flowScan flowMode = iota
	flowEmailCopy
)

const introMarkdown = `# Content List Generator

Fast recursive folder tools for very large collections.

- Generate a recursive CSV inventory, with optional XLSX export
- Copy email-related files into a chosen destination while preserving folders
- Choose each workflow from the main app

CSV is the safest default for huge scans because the app never builds the whole table in memory.`

type dirItem struct {
	name string
	path string
}

func (d dirItem) FilterValue() string { return d.name }
func (d dirItem) Title() string       { return d.name }
func (d dirItem) Description() string { return d.path }

type actionItem struct {
	title       string
	description string
	flow        flowMode
}

func (a actionItem) FilterValue() string { return a.title }
func (a actionItem) Title() string       { return a.title }
func (a actionItem) Description() string { return a.description }

type summaryEntry struct {
	Label string
	Count uint64
	Bytes uint64
}

type scanProgressMsg struct {
	files       uint64
	directories uint64
	bytes       uint64
	filtered    uint64
	elapsed     time.Duration
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
	hashing         bool
	excludeHidden   bool
	excludeSystem   bool
	createXLSX      bool
	preserveZeros   bool
	filteredHidden  uint64
	filteredSystem  uint64
	filteredExts    uint64
	filteredSamples []string
}

type scanErrorMsg struct {
	err error
}

type emailCopyDoneMsg struct {
	sourceDir    string
	destDir      string
	manifestPath string
	copied       uint64
	elapsed      time.Duration
}

type scanOptions struct {
	Hashing          bool
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

type model struct {
	stage          stage
	width          int
	height         int
	list           list.Model
	outputInput    textinput.Model
	excludeInput   textinput.Model
	settingsFocus  int
	hashing        bool
	excludeHidden  bool
	excludeSystem  bool
	createXLSX     bool
	preserveZeros  bool
	spinner        spinner.Model
	activeFlow     flowMode
	sourceDir      string
	outputDir      string
	outputPath     string
	emailSourceDir string
	emailDestDir   string
	pendingPath    string
	err            error
	done           scanDoneMsg
	emailDone      emailCopyDoneMsg
	progress       scanProgressMsg
	glamourIntro   string
	quitting       bool
	scanStartedAt  time.Time
}

type scannerStats struct {
	files       atomic.Uint64
	directories atomic.Uint64
	bytes       atomic.Uint64
	errors      atomic.Uint64
	filtered    atomic.Uint64
}

type sourceKeyMap struct {
	Choose key.Binding
	Up     key.Binding
}

var sourceKeys = sourceKeyMap{
	Choose: key.NewBinding(key.WithKeys("enter"), key.WithHelp("enter", "open / choose")),
	Up:     key.NewBinding(key.WithKeys("backspace", "h"), key.WithHelp("backspace", "up")),
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
	".ost":            {},
	".pst":            {},
	".rge":            {},
	".tbb":            {},
	".wdseml":         {},
}

func sortedEmailExtensions() []string {
	values := make([]string, 0, len(emailExtensions))
	for ext := range emailExtensions {
		values = append(values, ext)
	}
	slices.Sort(values)
	return values
}

func main() {
	startDir, err := os.Getwd()
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to get working directory: %v\n", err)
		os.Exit(1)
	}

	intro := renderMarkdown(introMarkdown, 88)

	outputInput := textinput.New()
	outputInput.Placeholder = "content-list.csv"
	outputInput.Prompt = ""
	outputInput.CharLimit = 0
	outputInput.Width = 80

	excludeInput := textinput.New()
	excludeInput.Placeholder = "tmp,log"
	excludeInput.Prompt = ""
	excludeInput.CharLimit = 0
	excludeInput.Width = 80

	spin := spinner.New()
	spin.Spinner = spinner.Dot
	spin.Style = lipgloss.NewStyle().Foreground(lipgloss.Color("205"))

	m := model{
		stage:          stageHome,
		list:           newActionList(),
		outputInput:    outputInput,
		excludeInput:   excludeInput,
		settingsFocus:  focusFileName,
		hashing:        false,
		excludeHidden:  false,
		excludeSystem:  false,
		createXLSX:     false,
		preserveZeros:  false,
		spinner:        spin,
		activeFlow:     flowScan,
		sourceDir:      startDir,
		outputDir:      startDir,
		emailSourceDir: startDir,
		emailDestDir:   startDir,
		glamourIntro:   intro,
	}
	m.syncSettingsFocus()

	p := tea.NewProgram(m, tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "app error: %v\n", err)
		os.Exit(1)
	}
}

func newSourceList(currentDir string) list.Model {
	return newDirectoryList(currentDir, "Source Folder")
}

func newActionList() list.Model {
	items := []list.Item{
		actionItem{
			title:       "Generate Content List",
			description: "Scan a folder to CSV, with optional hashing, filters, and XLSX export.",
			flow:        flowScan,
		},
		actionItem{
			title:       "Copy Email Files",
			description: "Copy supported email files into a chosen destination and save a manifest report.",
			flow:        flowEmailCopy,
		},
	}

	delegate := list.NewDefaultDelegate()
	delegate.ShowDescription = true
	delegate.SetSpacing(1)

	l := list.New(items, delegate, 0, 0)
	l.Title = "Main Menu"
	l.SetShowStatusBar(false)
	l.SetFilteringEnabled(false)
	l.SetShowHelp(true)
	l.SetShowPagination(false)
	l.Styles.Title = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("39"))
	return l
}

func newDirectoryList(currentDir, titlePrefix string) list.Model {
	items := make([]list.Item, 0)
	parent := filepath.Dir(currentDir)
	if parent != currentDir {
		items = append(items, dirItem{name: "..", path: parent})
	}

	entries, err := os.ReadDir(currentDir)
	if err == nil {
		dirs := make([]dirItem, 0, len(entries))
		for _, entry := range entries {
			if !entry.IsDir() {
				continue
			}
			dirs = append(dirs, dirItem{
				name: entry.Name(),
				path: filepath.Join(currentDir, entry.Name()),
			})
		}
		slices.SortFunc(dirs, func(a, b dirItem) int {
			return strings.Compare(strings.ToLower(a.name), strings.ToLower(b.name))
		})
		for _, item := range dirs {
			items = append(items, item)
		}
	}

	delegate := list.NewDefaultDelegate()
	delegate.ShowDescription = true
	delegate.SetSpacing(0)

	l := list.New(items, delegate, 0, 0)
	l.Title = fmt.Sprintf("%s: %s", titlePrefix, currentDir)
	l.SetShowStatusBar(false)
	l.SetFilteringEnabled(false)
	l.SetShowHelp(true)
	l.SetShowPagination(true)
	l.Styles.Title = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("39"))
	return l
}

func (m model) Init() tea.Cmd {
	return nil
}

func (m model) resetToHome() model {
	m.stage = stageHome
	m.activeFlow = flowScan
	m.list = newActionList()
	m.list.SetSize(m.width-8, boundedListHeight(m.height))
	m.err = nil
	m.pendingPath = ""
	return m
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.list.SetSize(msg.Width-8, boundedListHeight(msg.Height))
		m.outputInput.Width = max(20, msg.Width-28)
		m.excludeInput.Width = max(20, msg.Width-28)
		return m, nil
	case tea.KeyMsg:
		switch m.stage {
		case stageHome:
			return m.updateHomeStage(msg)
		case stagePickSource:
			return m.updateSourceStage(msg)
		case stagePickOutputDir:
			return m.updateOutputDirStage(msg)
		case stageSetOutput:
			return m.updateOutputStage(msg)
		case stageConfirmOverwrite:
			return m.updateConfirmOverwriteStage(msg)
		case stageScanning:
			if msg.String() == "ctrl+c" || msg.String() == "q" {
				m.quitting = true
				return m, tea.Quit
			}
		case stageEmailPickSource:
			return m.updateEmailSourceStage(msg)
		case stageEmailPickDest:
			return m.updateEmailDestStage(msg)
		case stageEmailCopying:
			if msg.String() == "ctrl+c" || msg.String() == "q" {
				m.quitting = true
				return m, tea.Quit
			}
		case stageDone, stageFailed:
			if m.activeFlow == flowEmailCopy && msg.String() == "enter" {
				m = m.resetToHome()
				return m, nil
			}
			if msg.String() == "enter" || msg.String() == "q" || msg.String() == "ctrl+c" {
				m.quitting = true
				return m, tea.Quit
			}
		}
	case spinner.TickMsg:
		if m.stage == stageScanning {
			var cmd tea.Cmd
			m.spinner, cmd = m.spinner.Update(msg)
			return m, cmd
		}
	case scanProgressMsg:
		m.progress = msg
		return m, waitForProgress()
	case scanDoneMsg:
		m.activeFlow = flowScan
		m.stage = stageDone
		m.done = msg
		m.outputPath = msg.outputPath
		return m, nil
	case emailCopyDoneMsg:
		m.activeFlow = flowEmailCopy
		m.stage = stageDone
		m.emailDone = msg
		return m, nil
	case scanErrorMsg:
		m.stage = stageFailed
		m.err = msg.err
		return m, nil
	}

	return m, nil
}

func (m model) updateHomeStage(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "enter":
		selected, ok := m.list.SelectedItem().(actionItem)
		if !ok {
			return m, nil
		}
		switch selected.flow {
		case flowScan:
			m.activeFlow = flowScan
			m.stage = stagePickSource
			m.list = newSourceList(m.sourceDir)
			m.list.SetSize(m.width-8, boundedListHeight(m.height))
			return m, nil
		case flowEmailCopy:
			m.activeFlow = flowEmailCopy
			m.stage = stageEmailPickSource
			m.list = newDirectoryList(m.emailSourceDir, "Email Copy Source Folder")
			m.list.SetSize(m.width-8, boundedListHeight(m.height))
			return m, nil
		}
	case "q", "ctrl+c":
		m.quitting = true
		return m, tea.Quit
	}

	var cmd tea.Cmd
	m.list, cmd = m.list.Update(msg)
	return m, cmd
}

func (m model) updateSourceStage(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch {
	case key.Matches(msg, sourceKeys.Up):
		parent := filepath.Dir(m.sourceDir)
		if parent != m.sourceDir {
			m.sourceDir = parent
			m.list = newSourceList(parent)
			m.list.SetSize(m.width-8, boundedListHeight(m.height))
		}
		return m, nil
	case key.Matches(msg, sourceKeys.Choose):
		selected, ok := m.list.SelectedItem().(dirItem)
		if !ok {
			m.outputDir = m.sourceDir
			m.stage = stagePickOutputDir
			m.list = newDirectoryList(m.outputDir, "Output Folder")
			m.list.SetSize(m.width-8, boundedListHeight(m.height))
			return m, nil
		}
		if selected.name == ".." {
			m.sourceDir = selected.path
			m.list = newSourceList(selected.path)
			m.list.SetSize(m.width-8, boundedListHeight(m.height))
			return m, nil
		}
		m.sourceDir = selected.path
		m.list = newSourceList(selected.path)
		m.list.SetSize(m.width-8, boundedListHeight(m.height))
		return m, nil
	case msg.String() == " ":
		m.outputDir = m.sourceDir
		m.stage = stagePickOutputDir
		m.list = newDirectoryList(m.outputDir, "Output Folder")
		m.list.SetSize(m.width-8, boundedListHeight(m.height))
		return m, nil
	case msg.String() == "esc":
		m = m.resetToHome()
		return m, nil
	case msg.String() == "q" || msg.String() == "ctrl+c":
		m.quitting = true
		return m, tea.Quit
	}

	var cmd tea.Cmd
	m.list, cmd = m.list.Update(msg)
	return m, cmd
}

func (m model) updateOutputDirStage(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch {
	case key.Matches(msg, sourceKeys.Up):
		parent := filepath.Dir(m.outputDir)
		if parent != m.outputDir {
			m.outputDir = parent
			m.list = newDirectoryList(parent, "Output Folder")
			m.list.SetSize(m.width-8, boundedListHeight(m.height))
		}
		return m, nil
	case key.Matches(msg, sourceKeys.Choose):
		selected, ok := m.list.SelectedItem().(dirItem)
		if !ok {
			m.stage = stageSetOutput
			m.outputInput.SetValue(defaultOutputFilename(m.sourceDir))
			m.syncSettingsFocus()
			return m, textinput.Blink
		}
		if selected.name == ".." {
			m.outputDir = selected.path
			m.list = newDirectoryList(selected.path, "Output Folder")
			m.list.SetSize(m.width-8, boundedListHeight(m.height))
			return m, nil
		}
		m.outputDir = selected.path
		m.list = newDirectoryList(selected.path, "Output Folder")
		m.list.SetSize(m.width-8, boundedListHeight(m.height))
		return m, nil
	case msg.String() == " ":
		m.stage = stageSetOutput
		m.outputInput.SetValue(defaultOutputFilename(m.sourceDir))
		m.syncSettingsFocus()
		return m, textinput.Blink
	case msg.String() == "esc":
		m.stage = stagePickSource
		m.list = newDirectoryList(m.sourceDir, "Source Folder")
		m.list.SetSize(m.width-8, boundedListHeight(m.height))
		return m, nil
	case msg.String() == "q" || msg.String() == "ctrl+c":
		m.quitting = true
		return m, tea.Quit
	}

	var cmd tea.Cmd
	m.list, cmd = m.list.Update(msg)
	return m, cmd
}

func (m model) updateEmailSourceStage(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch {
	case key.Matches(msg, sourceKeys.Up):
		parent := filepath.Dir(m.emailSourceDir)
		if parent != m.emailSourceDir {
			m.emailSourceDir = parent
			m.list = newDirectoryList(parent, "Email Copy Source Folder")
			m.list.SetSize(m.width-8, boundedListHeight(m.height))
		}
		return m, nil
	case key.Matches(msg, sourceKeys.Choose):
		selected, ok := m.list.SelectedItem().(dirItem)
		if !ok {
			m.emailDestDir = m.emailSourceDir
			m.stage = stageEmailPickDest
			m.list = newDirectoryList(m.emailDestDir, "Email Copy Destination")
			m.list.SetSize(m.width-8, boundedListHeight(m.height))
			return m, nil
		}
		if selected.name == ".." {
			m.emailSourceDir = selected.path
			m.list = newDirectoryList(selected.path, "Email Copy Source Folder")
			m.list.SetSize(m.width-8, boundedListHeight(m.height))
			return m, nil
		}
		m.emailSourceDir = selected.path
		m.list = newDirectoryList(selected.path, "Email Copy Source Folder")
		m.list.SetSize(m.width-8, boundedListHeight(m.height))
		return m, nil
	case msg.String() == " ":
		m.emailDestDir = m.emailSourceDir
		m.stage = stageEmailPickDest
		m.list = newDirectoryList(m.emailDestDir, "Email Copy Destination")
		m.list.SetSize(m.width-8, boundedListHeight(m.height))
		return m, nil
	case msg.String() == "esc":
		m = m.resetToHome()
		return m, nil
	case msg.String() == "q" || msg.String() == "ctrl+c":
		m.quitting = true
		return m, tea.Quit
	}

	var cmd tea.Cmd
	m.list, cmd = m.list.Update(msg)
	return m, cmd
}

func (m model) updateEmailDestStage(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch {
	case key.Matches(msg, sourceKeys.Up):
		parent := filepath.Dir(m.emailDestDir)
		if parent != m.emailDestDir {
			m.emailDestDir = parent
			m.list = newDirectoryList(parent, "Email Copy Destination")
			m.list.SetSize(m.width-8, boundedListHeight(m.height))
		}
		return m, nil
	case key.Matches(msg, sourceKeys.Choose):
		selected, ok := m.list.SelectedItem().(dirItem)
		if !ok {
			return m.beginEmailCopy()
		}
		if selected.name == ".." {
			m.emailDestDir = selected.path
			m.list = newDirectoryList(selected.path, "Email Copy Destination")
			m.list.SetSize(m.width-8, boundedListHeight(m.height))
			return m, nil
		}
		m.emailDestDir = selected.path
		m.list = newDirectoryList(selected.path, "Email Copy Destination")
		m.list.SetSize(m.width-8, boundedListHeight(m.height))
		return m, nil
	case msg.String() == " ":
		return m.beginEmailCopy()
	case msg.String() == "esc":
		m.stage = stageEmailPickSource
		m.list = newDirectoryList(m.emailSourceDir, "Email Copy Source Folder")
		m.list.SetSize(m.width-8, boundedListHeight(m.height))
		return m, nil
	case msg.String() == "q" || msg.String() == "ctrl+c":
		m.quitting = true
		return m, tea.Quit
	}

	var cmd tea.Cmd
	m.list, cmd = m.list.Update(msg)
	return m, cmd
}

func (m model) updateOutputStage(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "ctrl+c", "q":
		m.quitting = true
		return m, tea.Quit
	case "esc":
		m.stage = stagePickOutputDir
		m.list = newDirectoryList(m.outputDir, "Output Folder")
		m.list.SetSize(m.width-8, boundedListHeight(m.height))
		m.syncSettingsFocus()
		return m, nil
	case "tab", "down":
		m.settingsFocus = (m.settingsFocus + 1) % focusCount
		m.syncSettingsFocus()
		return m, textinput.Blink
	case "shift+tab", "up":
		m.settingsFocus = (m.settingsFocus - 1 + focusCount) % focusCount
		m.syncSettingsFocus()
		return m, textinput.Blink
	case " ":
		switch m.settingsFocus {
		case focusHashing:
			m.hashing = !m.hashing
			return m, nil
		case focusHidden:
			m.excludeHidden = !m.excludeHidden
			return m, nil
		case focusSystem:
			m.excludeSystem = !m.excludeSystem
			return m, nil
		case focusXLSX:
			m.createXLSX = !m.createXLSX
			if !m.createXLSX {
				m.preserveZeros = false
			}
			return m, nil
		case focusPreserveZeros:
			if m.createXLSX {
				m.preserveZeros = !m.preserveZeros
			}
			return m, nil
		}
	case "enter":
		switch m.settingsFocus {
		case focusHashing:
			m.hashing = !m.hashing
			return m, nil
		case focusHidden:
			m.excludeHidden = !m.excludeHidden
			return m, nil
		case focusSystem:
			m.excludeSystem = !m.excludeSystem
			return m, nil
		case focusXLSX:
			m.createXLSX = !m.createXLSX
			if !m.createXLSX {
				m.preserveZeros = false
			}
			return m, nil
		case focusPreserveZeros:
			if m.createXLSX {
				m.preserveZeros = !m.preserveZeros
			}
			return m, nil
		case focusFileName, focusExcludeExts:
			m.settingsFocus = (m.settingsFocus + 1) % focusCount
			m.syncSettingsFocus()
			return m, textinput.Blink
		case focusStart:
			filename := strings.TrimSpace(m.outputInput.Value())
			if filename == "" {
				filename = defaultOutputFilename(m.sourceDir)
			}
			outputPath := filepath.Join(m.outputDir, filename)
			if strings.ToLower(filepath.Ext(outputPath)) != ".csv" {
				m.err = fmt.Errorf("output file must end with .csv")
				return m, nil
			}

			excludedMap, err := parseExcludedExtensions(m.excludeInput.Value())
			if err != nil {
				m.err = err
				return m, nil
			}

			exists, err := ensureOutputPath(outputPath)
			if err != nil {
				m.err = err
				return m, nil
			}

			m.pendingPath = outputPath
			m.err = nil
			if exists {
				m.stage = stageConfirmOverwrite
				return m, nil
			}

			return m.beginScan(outputPath, scanOptions{
				Hashing:          m.hashing,
				ExcludeHidden:    m.excludeHidden,
				ExcludeSystem:    m.excludeSystem,
				CreateXLSX:       m.createXLSX,
				PreserveZeros:    m.preserveZeros,
				ExcludedExts:     excludedMap,
				ExcludedExtsText: strings.TrimSpace(m.excludeInput.Value()),
			})
		}
	}

	var cmd tea.Cmd
	switch m.settingsFocus {
	case focusFileName:
		m.outputInput, cmd = m.outputInput.Update(msg)
	case focusExcludeExts:
		m.excludeInput, cmd = m.excludeInput.Update(msg)
	}
	return m, cmd
}

func (m model) updateConfirmOverwriteStage(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "y", "Y":
		excludedMap, err := parseExcludedExtensions(m.excludeInput.Value())
		if err != nil {
			m.err = err
			m.stage = stageSetOutput
			return m, nil
		}
		return m.beginScan(m.pendingPath, scanOptions{
			Hashing:          m.hashing,
			ExcludeHidden:    m.excludeHidden,
			ExcludeSystem:    m.excludeSystem,
			CreateXLSX:       m.createXLSX,
			PreserveZeros:    m.preserveZeros,
			ExcludedExts:     excludedMap,
			ExcludedExtsText: strings.TrimSpace(m.excludeInput.Value()),
		})
	case "n", "N", "esc":
		m.stage = stageSetOutput
		m.pendingPath = ""
		m.syncSettingsFocus()
		return m, textinput.Blink
	case "ctrl+c", "q":
		m.quitting = true
		return m, tea.Quit
	}
	return m, nil
}

func (m model) beginScan(outputPath string, options scanOptions) (tea.Model, tea.Cmd) {
	m.stage = stageScanning
	m.activeFlow = flowScan
	m.err = nil
	m.pendingPath = ""
	m.outputPath = outputPath
	m.scanStartedAt = time.Now()
	return m, tea.Batch(
		m.spinner.Tick,
		startScan(m.sourceDir, outputPath, options),
		waitForProgress(),
	)
}

func (m model) beginEmailCopy() (tea.Model, tea.Cmd) {
	m.stage = stageEmailCopying
	m.activeFlow = flowEmailCopy
	m.err = nil
	m.scanStartedAt = time.Now()
	return m, tea.Batch(
		m.spinner.Tick,
		startEmailCopy(m.emailSourceDir, m.emailDestDir),
	)
}

func (m *model) syncSettingsFocus() {
	if m.settingsFocus == focusFileName {
		m.outputInput.Focus()
	} else {
		m.outputInput.Blur()
	}
	if m.settingsFocus == focusExcludeExts {
		m.excludeInput.Focus()
	} else {
		m.excludeInput.Blur()
	}
}

func (m model) View() string {
	if m.quitting {
		return ""
	}

	switch m.stage {
	case stageHome:
		return m.viewHome()
	case stagePickSource:
		return m.viewSourcePicker()
	case stagePickOutputDir:
		return m.viewOutputDirPicker()
	case stageSetOutput:
		return m.viewOutputForm()
	case stageConfirmOverwrite:
		return m.viewConfirmOverwrite()
	case stageScanning:
		return m.viewScanning()
	case stageEmailPickSource:
		return m.viewEmailSourcePicker()
	case stageEmailPickDest:
		return m.viewEmailDestPicker()
	case stageEmailCopying:
		return m.viewEmailCopying()
	case stageDone:
		if m.activeFlow == flowEmailCopy {
			return m.viewEmailDone()
		}
		return m.viewDone()
	case stageFailed:
		return m.viewError()
	default:
		return ""
	}
}

func (m model) viewHome() string {
	body := lipgloss.JoinVertical(
		lipgloss.Left,
		styleDoc(m.glamourIntro),
		"",
		styleHint("Choose a workflow. Press enter to open it."),
		"",
		renderListWithFade(m.list.View()),
	)
	return styleFrame(body, m.width)
}

func (m model) viewSourcePicker() string {
	body := lipgloss.JoinVertical(
		lipgloss.Left,
		styleDoc(m.glamourIntro),
		"",
		styleHint("Navigate folders with arrows. Press enter to open a folder. Press space to choose the current folder."),
		"",
		renderListWithFade(m.list.View()),
		"",
		styleHint(fmt.Sprintf("Current source folder: %s", m.sourceDir)),
	)
	return styleFrame(body, m.width)
}

func (m model) viewOutputDirPicker() string {
	body := lipgloss.JoinVertical(
		lipgloss.Left,
		styleTitle("Choose Output Folder"),
		"",
		styleLabel(fmt.Sprintf("Source folder: %s", m.sourceDir)),
		styleHint("Navigate folders with arrows. Press enter to open a folder. Press space to choose the current folder."),
		"",
		renderListWithFade(m.list.View()),
		"",
		styleHint(fmt.Sprintf("Current output folder: %s", m.outputDir)),
	)
	return styleFrame(body, m.width)
}

func (m model) viewOutputForm() string {
	body := lipgloss.JoinVertical(
		lipgloss.Left,
		styleTitle("Output Settings"),
		"",
		styleLabel(fmt.Sprintf("Source folder: %s", m.sourceDir)),
		styleLabel(fmt.Sprintf("Output folder: %s", m.outputDir)),
		"",
		focusedLine(m.settingsFocus == focusFileName, "File name", m.outputInput.View()),
		focusedInfo(false, "Format", "Scan writes CSV first. XLSX can be created afterward as a spreadsheet copy."),
		focusedLine(m.settingsFocus == focusExcludeExts, "Exclude extensions", m.excludeInput.View()),
		focusedToggle(m.settingsFocus == focusHashing, "SHA-256 hashing", m.hashing),
		focusedToggle(m.settingsFocus == focusHidden, "Exclude hidden files", m.excludeHidden),
		focusedToggle(m.settingsFocus == focusSystem, "Exclude common system files", m.excludeSystem),
		focusedToggle(m.settingsFocus == focusXLSX, "Create XLSX after scan", m.createXLSX),
		focusedToggle(m.settingsFocus == focusPreserveZeros, "Preserve leading zeros in XLSX", m.preserveZeros && m.createXLSX),
		focusedAction(m.settingsFocus == focusStart, "Start scan"),
		"",
		styleHint("Tab or arrows move between controls. Space toggles a switch. Enter activates the focused control."),
		styleHint(fmt.Sprintf("Preview: %s", filepath.Join(m.outputDir, valueOrDefault(strings.TrimSpace(m.outputInput.Value()), defaultOutputFilename(m.sourceDir))))),
	)

	if m.err != nil {
		body = lipgloss.JoinVertical(lipgloss.Left, body, "", styleError(m.err.Error()))
	}

	return styleFrame(body, m.width)
}

func (m model) viewScanning() string {
	body := lipgloss.JoinVertical(
		lipgloss.Left,
		styleTitle(fmt.Sprintf("%s Scanning...", m.spinner.View())),
		"",
		styleLabel(fmt.Sprintf("Source: %s", m.sourceDir)),
		styleLabel(fmt.Sprintf("Output: %s", m.outputPath)),
		styleLabel(fmt.Sprintf("Hashes: %s", onOff(m.hashing))),
		styleLabel(fmt.Sprintf("Exclude hidden: %s", onOff(m.excludeHidden))),
		styleLabel(fmt.Sprintf("Exclude system: %s", onOff(m.excludeSystem))),
		styleLabel(fmt.Sprintf("Create XLSX: %s", onOff(m.createXLSX))),
		styleLabel(fmt.Sprintf("Preserve zeros in XLSX: %s", onOff(m.preserveZeros && m.createXLSX))),
		styleLabel(fmt.Sprintf("Excluded exts: %s", valueOrDefault(strings.TrimSpace(m.excludeInput.Value()), "none"))),
		"",
		styleStat("Files", formatUint(m.progress.files)),
		styleStat("Directories", formatUint(m.progress.directories)),
		styleStat("Bytes", humanBytes(m.progress.bytes)),
		styleStat("Filtered out", formatUint(m.progress.filtered)),
		styleStat("Elapsed", m.progress.elapsed.Round(time.Second).String()),
		"",
		styleHint("Rows are streamed directly to CSV, so huge scans stay memory-safe."),
	)
	return styleFrame(body, m.width)
}

func (m model) viewEmailSourcePicker() string {
	body := lipgloss.JoinVertical(
		lipgloss.Left,
		styleTitle("Choose Email Copy Source Folder"),
		"",
		styleHint("Navigate folders with arrows. Press enter to open a folder. Press space to choose the current folder."),
		"",
		renderListWithFade(m.list.View()),
		"",
		styleHint(fmt.Sprintf("Current source folder: %s", m.emailSourceDir)),
	)
	return styleFrame(body, m.width)
}

func (m model) viewEmailDestPicker() string {
	body := lipgloss.JoinVertical(
		lipgloss.Left,
		styleTitle("Choose Email Copy Destination"),
		"",
		styleLabel(fmt.Sprintf("Source folder: %s", m.emailSourceDir)),
		styleHint("Navigate folders with arrows. Press enter to open a folder. Press space to choose the current folder as the destination."),
		"",
		renderListWithFade(m.list.View()),
		"",
		styleHint(fmt.Sprintf("Current destination: %s", m.emailDestDir)),
	)
	return styleFrame(body, m.width)
}

func (m model) viewEmailCopying() string {
	body := lipgloss.JoinVertical(
		lipgloss.Left,
		styleTitle(fmt.Sprintf("%s Copying Email Files...", m.spinner.View())),
		"",
		styleLabel(fmt.Sprintf("Source: %s", m.emailSourceDir)),
		styleLabel(fmt.Sprintf("Destination: %s", m.emailDestDir)),
		styleLabel(fmt.Sprintf("Extensions: %s", strings.Join(sortedEmailExtensions(), ", "))),
		"",
		styleHint("Relative folders from the source root are preserved in the destination."),
	)
	return styleFrame(body, m.width)
}

func (m model) viewConfirmOverwrite() string {
	body := lipgloss.JoinVertical(
		lipgloss.Left,
		styleTitle("File Already Exists"),
		"",
		styleLabel("The selected output file already exists:"),
		styleLabel(m.pendingPath),
		"",
		styleHint("Press y to overwrite it, or n to go back and choose another name."),
	)
	return styleFrame(body, m.width)
}

func (m model) viewDone() string {
	countSummary := renderSummaryList("Top extensions by file count", m.done.topByCount, func(entry summaryEntry) string {
		return fmt.Sprintf("%s files, %s", formatUint(entry.Count), humanBytes(entry.Bytes))
	})
	sizeSummary := renderSummaryList("Top extensions by total size", m.done.topBySize, func(entry summaryEntry) string {
		return fmt.Sprintf("%s, %s files", humanBytes(entry.Bytes), formatUint(entry.Count))
	})

	body := lipgloss.JoinVertical(
		lipgloss.Left,
		styleTitle("Scan Complete"),
		"",
		styleStat("Output", m.done.outputPath),
		styleStat("XLSX copy", valueOrDefault(m.done.xlsxPath, "not created")),
		styleStat("Files", formatUint(m.done.files)),
		styleStat("Directories", formatUint(m.done.directories)),
		styleStat("Bytes", humanBytes(m.done.bytes)),
		styleStat("Filtered out", formatUint(m.done.filtered)),
		styleStat("Hidden filtered", formatUint(m.done.filteredHidden)),
		styleStat("System filtered", formatUint(m.done.filteredSystem)),
		styleStat("Extension filtered", formatUint(m.done.filteredExts)),
		styleStat("Errors skipped", formatUint(m.done.errors)),
		styleStat("Elapsed", m.done.elapsed.Round(time.Millisecond).String()),
		styleStat("Hash workers", fmt.Sprintf("%d", m.done.hashWorkers)),
		styleStat("Create XLSX", onOff(m.done.createXLSX)),
		styleStat("Preserve zeros", onOff(m.done.preserveZeros)),
		"",
		countSummary,
		"",
		sizeSummary,
		"",
		renderFilteredSamples(m.done.filteredSamples),
		"",
		styleHint("Press enter to exit."),
	)
	return styleFrame(body, m.width)
}

func (m model) viewEmailDone() string {
	body := lipgloss.JoinVertical(
		lipgloss.Left,
		styleTitle("Email Copy Complete"),
		"",
		styleStat("Source", m.emailDone.sourceDir),
		styleStat("Destination", m.emailDone.destDir),
		styleStat("Manifest", m.emailDone.manifestPath),
		styleStat("Copied", formatUint(m.emailDone.copied)),
		styleStat("Elapsed", m.emailDone.elapsed.Round(time.Millisecond).String()),
		"",
		styleHint("Press enter to return to the main menu."),
	)
	return styleFrame(body, m.width)
}

func (m model) viewError() string {
	hint := "Press enter to exit."
	title := "Scan Failed"
	if m.activeFlow == flowEmailCopy {
		title = "Email Copy Failed"
		hint = "Press enter to return to the main menu."
	}
	body := lipgloss.JoinVertical(
		lipgloss.Left,
		styleTitle(title),
		"",
		styleError(m.err.Error()),
		"",
		styleHint(hint),
	)
	return styleFrame(body, m.width)
}

func startScan(sourceDir, outputPath string, options scanOptions) tea.Cmd {
	return func() tea.Msg {
		done, err := runScan(sourceDir, outputPath, options)
		if err != nil {
			return scanErrorMsg{err: err}
		}
		return done
	}
}

func startEmailCopy(sourceDir, destDir string) tea.Cmd {
	return func() tea.Msg {
		startedAt := time.Now()
		manifestPath, copied, err := copyEmailFiles(sourceDir, destDir)
		if err != nil {
			return scanErrorMsg{err: err}
		}
		return emailCopyDoneMsg{
			sourceDir:    sourceDir,
			destDir:      destDir,
			manifestPath: manifestPath,
			copied:       copied,
			elapsed:      time.Since(startedAt),
		}
	}
}

func waitForProgress() tea.Cmd {
	return tea.Tick(250*time.Millisecond, func(t time.Time) tea.Msg {
		stats := currentProgress()
		return scanProgressMsg{
			files:       stats.files,
			directories: stats.directories,
			bytes:       stats.bytes,
			filtered:    stats.filtered,
			elapsed:     time.Since(stats.startedAt),
		}
	})
}

type globalProgress struct {
	files       uint64
	directories uint64
	bytes       uint64
	filtered    uint64
	startedAt   time.Time
}

var scanProgressState atomic.Value

func currentProgress() globalProgress {
	if value := scanProgressState.Load(); value != nil {
		return value.(globalProgress)
	}
	return globalProgress{startedAt: time.Now()}
}

func setProgress(files, directories, bytes, filtered uint64, startedAt time.Time) {
	scanProgressState.Store(globalProgress{
		files:       files,
		directories: directories,
		bytes:       bytes,
		filtered:    filtered,
		startedAt:   startedAt,
	})
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
		"SHA256 Hash",
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
	if err := w.file.Close(); err != nil {
		return err
	}
	return nil
}

func runScan(sourceDir, outputPath string, options scanOptions) (scanDoneMsg, error) {
	startedAt := time.Now()
	setProgress(0, 0, 0, 0, startedAt)

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
	if options.Hashing {
		hashWorkers = max(2, runtime.NumCPU())
	}

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
				if options.Hashing {
					hashValue, resultErr = hashFile(work.path)
				}
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
					filteredHidden += 1
					filteredSamples = appendFilteredSample(filteredSamples, fmt.Sprintf("%s -> hidden directory", filepath.ToSlash(path)))
					setProgress(stats.files.Load(), stats.directories.Load(), stats.bytes.Load(), stats.filtered.Load(), startedAt)
					return filepath.SkipDir
				}
				stats.directories.Add(1)
				setProgress(stats.files.Load(), stats.directories.Load(), stats.bytes.Load(), stats.filtered.Load(), startedAt)
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

			if reason, skipped := shouldSkipFile(path, d.Name(), options); skipped {
				stats.filtered.Add(1)
				switch reason {
				case "hidden path":
					filteredHidden += 1
				case "system file":
					filteredSystem += 1
				case "excluded extension":
					filteredExts += 1
				}
				filteredSamples = appendFilteredSample(filteredSamples, fmt.Sprintf("%s -> %s", filepath.ToSlash(path), reason))
				setProgress(stats.files.Load(), stats.directories.Load(), stats.bytes.Load(), stats.filtered.Load(), startedAt)
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
				setProgress(stats.files.Load(), stats.directories.Load(), stats.bytes.Load(), stats.filtered.Load(), startedAt)
				continue
			}

			if err := reportWriter.WriteRow([]string{
				ready.work.name,
				ready.work.ext,
				fmt.Sprintf("%d", ready.work.size),
				humanBytes(ready.work.size),
				ready.work.relative,
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

			setProgress(stats.files.Load(), stats.directories.Load(), stats.bytes.Load(), stats.filtered.Load(), startedAt)
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
		hashing:         options.Hashing,
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

func hashFile(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()

	hash := sha256.New()
	if _, err := io.CopyBuffer(hash, file, make([]byte, 1<<20)); err != nil {
		return "", err
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}

func ensureOutputPath(outputPath string) (bool, error) {
	parent := filepath.Dir(outputPath)
	if parent == "." {
		cwd, err := os.Getwd()
		if err != nil {
			return false, err
		}
		parent = cwd
	}

	info, err := os.Stat(outputPath)
	if err == nil && !info.IsDir() {
		return true, nil
	}
	if err == nil && info.IsDir() {
		return false, fmt.Errorf("output path is a directory: %s", outputPath)
	}
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return false, err
	}

	if err := os.MkdirAll(parent, 0o755); err != nil {
		return false, err
	}

	testFile := filepath.Join(parent, fmt.Sprintf(".content-list-generator-%d.tmp", time.Now().UnixNano()))
	f, err := os.Create(testFile)
	if err != nil {
		return false, fmt.Errorf("output folder is not writable: %s", parent)
	}
	f.Close()
	return false, os.Remove(testFile)
}

func isSupportedOutputPath(outputPath string) bool {
	return strings.ToLower(filepath.Ext(outputPath)) == ".csv"
}

func copyEmailFiles(sourceDir, destDir string) (string, uint64, error) {
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

	var copied uint64
	err = filepath.WalkDir(sourceDir, func(path string, d fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return nil
		}
		if d.IsDir() {
			return nil
		}

		ext := strings.ToLower(filepath.Ext(d.Name()))
		if _, ok := emailExtensions[ext]; !ok {
			return nil
		}

		relative, err := filepath.Rel(sourceDir, path)
		if err != nil {
			return nil
		}
		targetPath := filepath.Join(destDir, relative)
		if err := os.MkdirAll(filepath.Dir(targetPath), 0o755); err != nil {
			return err
		}
		if err := copyFile(path, targetPath); err != nil {
			return err
		}

		info, err := os.Stat(path)
		if err != nil {
			return nil
		}

		if err := writer.Write([]string{
			path,
			targetPath,
			filepath.ToSlash(relative),
			filepath.Base(path),
			ext,
			fmt.Sprintf("%d", info.Size()),
		}); err != nil {
			return err
		}

		copied++
		return nil
	})
	if err != nil {
		return "", 0, err
	}
	writer.Flush()
	if err := writer.Error(); err != nil {
		return "", 0, err
	}

	return manifestPath, copied, nil
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

func parseExcludedExtensions(input string) (map[string]struct{}, error) {
	result := make(map[string]struct{})
	if strings.TrimSpace(input) == "" {
		return result, nil
	}

	for _, raw := range strings.Split(input, ",") {
		part := strings.TrimSpace(strings.ToLower(raw))
		part = strings.TrimPrefix(part, ".")
		if part == "" {
			continue
		}
		if strings.ContainsAny(part, `/\ `) {
			return nil, fmt.Errorf("excluded extensions should be comma-separated values like tmp,log")
		}
		result[part] = struct{}{}
	}
	return result, nil
}

func shouldSkipFile(path, name string, options scanOptions) (string, bool) {
	if options.ExcludeHidden && hasHiddenComponent(path) {
		return "hidden path", true
	}
	if options.ExcludeSystem && isSystemFile(name) {
		return "system file", true
	}
	if _, ok := options.ExcludedExts[normalizeExt(filepath.Ext(name))]; ok {
		return "excluded extension", true
	}
	return "", false
}

func hasHiddenComponent(path string) bool {
	for _, part := range strings.Split(filepath.ToSlash(path), "/") {
		if isHiddenName(part) {
			return true
		}
	}
	return false
}

func isHiddenName(name string) bool {
	return strings.HasPrefix(name, ".") && name != "." && name != ".."
}

func isSystemFile(name string) bool {
	switch strings.ToLower(name) {
	case ".ds_store", "thumbs.db", "desktop.ini", "ehthumbs.db":
		return true
	default:
		return false
	}
}

func normalizeExt(ext string) string {
	return strings.TrimPrefix(strings.ToLower(ext), ".")
}

func summaryKey(ext string) string {
	if ext == "" {
		return "[no extension]"
	}
	return "." + ext
}

func appendFilteredSample(samples []string, value string) []string {
	if len(samples) >= 8 {
		return samples
	}
	return append(samples, value)
}

func summarizeByCount(entries map[string]summaryEntry, limit int) []summaryEntry {
	out := make([]summaryEntry, 0, len(entries))
	for _, entry := range entries {
		out = append(out, entry)
	}
	slices.SortFunc(out, func(a, b summaryEntry) int {
		if a.Count != b.Count {
			if a.Count > b.Count {
				return -1
			}
			return 1
		}
		if a.Bytes != b.Bytes {
			if a.Bytes > b.Bytes {
				return -1
			}
			return 1
		}
		return strings.Compare(a.Label, b.Label)
	})
	if len(out) > limit {
		out = out[:limit]
	}
	return out
}

func summarizeBySize(entries map[string]summaryEntry, limit int) []summaryEntry {
	out := make([]summaryEntry, 0, len(entries))
	for _, entry := range entries {
		out = append(out, entry)
	}
	slices.SortFunc(out, func(a, b summaryEntry) int {
		if a.Bytes != b.Bytes {
			if a.Bytes > b.Bytes {
				return -1
			}
			return 1
		}
		if a.Count != b.Count {
			if a.Count > b.Count {
				return -1
			}
			return 1
		}
		return strings.Compare(a.Label, b.Label)
	})
	if len(out) > limit {
		out = out[:limit]
	}
	return out
}

func defaultOutputPath(sourceDir string) string {
	return filepath.Join(sourceDir, defaultOutputFilename(sourceDir))
}

func defaultOutputFilename(sourceDir string) string {
	stamp := time.Now().Format("2006-01-02T15-04-05")
	name := filepath.Base(sourceDir)
	if name == "" || name == "." || name == string(filepath.Separator) {
		name = "content-list"
	}
	return fmt.Sprintf("%s-content-list-%s.csv", name, stamp)
}

func humanBytes(bytes uint64) string {
	units := []string{"B", "KB", "MB", "GB", "TB", "PB"}
	value := float64(bytes)
	idx := 0
	for value >= 1024 && idx < len(units)-1 {
		value /= 1024
		idx++
	}
	if idx == 0 {
		return fmt.Sprintf("%d %s", bytes, units[idx])
	}
	if value >= 10 {
		return fmt.Sprintf("%.1f %s", value, units[idx])
	}
	return fmt.Sprintf("%.2f %s", value, units[idx])
}

func formatUint(v uint64) string {
	return fmt.Sprintf("%d", v)
}

func onOff(v bool) string {
	if v {
		return "on"
	}
	return "off"
}

func renderMarkdown(input string, width int) string {
	renderer, err := glamour.NewTermRenderer(
		glamour.WithAutoStyle(),
		glamour.WithWordWrap(width),
	)
	if err != nil {
		return input
	}
	out, err := renderer.Render(input)
	if err != nil {
		return input
	}
	return strings.TrimSpace(out)
}

func renderSummaryList(title string, items []summaryEntry, formatter func(summaryEntry) string) string {
	lines := []string{styleTitle(title)}
	if len(items) == 0 {
		lines = append(lines, styleHint("No files were written."))
		return lipgloss.JoinVertical(lipgloss.Left, lines...)
	}
	for _, item := range items {
		lines = append(lines, styleStat(item.Label, formatter(item)))
	}
	return lipgloss.JoinVertical(lipgloss.Left, lines...)
}

func renderFilteredSamples(items []string) string {
	lines := []string{styleTitle("Filtered examples")}
	if len(items) == 0 {
		lines = append(lines, styleHint("Nothing was filtered."))
		return lipgloss.JoinVertical(lipgloss.Left, lines...)
	}
	for _, item := range items {
		lines = append(lines, styleHint(item))
	}
	return lipgloss.JoinVertical(lipgloss.Left, lines...)
}

func renderListWithFade(content string) string {
	return lipgloss.JoinVertical(
		lipgloss.Left,
		lipgloss.NewStyle().Foreground(lipgloss.Color("240")).Render("  . . ."),
		content,
		lipgloss.NewStyle().Foreground(lipgloss.Color("240")).Render("  . . ."),
	)
}

func focusedLine(focused bool, label, value string) string {
	return lipgloss.JoinHorizontal(
		lipgloss.Top,
		focusPrefix(focused),
		lipgloss.JoinVertical(
			lipgloss.Left,
			styleLabel(label),
			value,
		),
	)
}

func focusedInfo(focused bool, label, value string) string {
	return lipgloss.JoinHorizontal(
		lipgloss.Top,
		focusPrefix(focused),
		lipgloss.JoinVertical(
			lipgloss.Left,
			styleLabel(label),
			styleHint(value),
		),
	)
}

func focusedToggle(focused bool, label string, value bool) string {
	return lipgloss.JoinHorizontal(
		lipgloss.Top,
		focusPrefix(focused),
		styleLabel(fmt.Sprintf("%s: [%s]", label, checkbox(value))),
	)
}

func focusedAction(focused bool, label string) string {
	return lipgloss.JoinHorizontal(
		lipgloss.Top,
		focusPrefix(focused),
		styleTitle(label),
	)
}

func focusPrefix(focused bool) string {
	if focused {
		return lipgloss.NewStyle().Foreground(lipgloss.Color("39")).Render("> ")
	}
	return "  "
}

func checkbox(v bool) string {
	if v {
		return "x"
	}
	return " "
}

func valueOrDefault(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}

func boundedListHeight(windowHeight int) int {
	height := windowHeight - 28
	if height < 8 {
		return 8
	}
	if height > 14 {
		return 14
	}
	return height
}

func styleFrame(body string, width int) string {
	w := width - 4
	if w < 40 {
		w = 40
	}
	return lipgloss.NewStyle().
		Padding(1, 2).
		Width(w).
		Border(lipgloss.RoundedBorder()).
		BorderForeground(lipgloss.Color("63")).
		Render(body)
}

func styleDoc(s string) string {
	return lipgloss.NewStyle().Foreground(lipgloss.Color("252")).Render(s)
}

func styleTitle(s string) string {
	return lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("39")).Render(s)
}

func styleLabel(s string) string {
	return lipgloss.NewStyle().Foreground(lipgloss.Color("252")).Render(s)
}

func styleHint(s string) string {
	return lipgloss.NewStyle().Foreground(lipgloss.Color("244")).Render(s)
}

func styleError(s string) string {
	return lipgloss.NewStyle().Foreground(lipgloss.Color("196")).Bold(true).Render(s)
}

func styleStat(label, value string) string {
	return lipgloss.JoinHorizontal(
		lipgloss.Top,
		lipgloss.NewStyle().Foreground(lipgloss.Color("244")).Width(22).Render(label+":"),
		lipgloss.NewStyle().Foreground(lipgloss.Color("252")).Render(value),
	)
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
