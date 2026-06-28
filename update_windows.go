//go:build windows

package main

import (
	"encoding/base64"
	"encoding/binary"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"unicode/utf16"
	"unsafe"

	"golang.org/x/sys/windows"
)

func readExecutableVersion(path string) (string, error) {
	var zero windows.Handle
	size, err := windows.GetFileVersionInfoSize(path, &zero)
	if err != nil {
		return "", err
	}
	if size == 0 {
		return "", fmt.Errorf("no version resource in %s", path)
	}
	versionInfo := make([]byte, size)
	if err := windows.GetFileVersionInfo(path, 0, size, unsafe.Pointer(&versionInfo[0])); err != nil {
		return "", err
	}

	if version, ok := queryVersionString(versionInfo, "ProductVersion"); ok {
		return version, nil
	}
	if version, ok := queryVersionString(versionInfo, "FileVersion"); ok {
		return version, nil
	}

	var fixedInfo *windows.VS_FIXEDFILEINFO
	var fixedInfoLen uint32
	if err := windows.VerQueryValue(unsafe.Pointer(&versionInfo[0]), `\`, unsafe.Pointer(&fixedInfo), &fixedInfoLen); err != nil {
		return "", err
	}
	if fixedInfo == nil || fixedInfoLen == 0 {
		return "", fmt.Errorf("no fixed version info in %s", path)
	}

	return fmt.Sprintf(
		"%d.%d.%d.%d",
		(fixedInfo.FileVersionMS>>16)&0xffff,
		fixedInfo.FileVersionMS&0xffff,
		(fixedInfo.FileVersionLS>>16)&0xffff,
		fixedInfo.FileVersionLS&0xffff,
	), nil
}

type versionTranslation struct {
	Language uint16
	CodePage uint16
}

func queryVersionString(versionInfo []byte, key string) (string, bool) {
	var translationPtr *versionTranslation
	var translationLen uint32
	if err := windows.VerQueryValue(
		unsafe.Pointer(&versionInfo[0]),
		`\VarFileInfo\Translation`,
		unsafe.Pointer(&translationPtr),
		&translationLen,
	); err != nil || translationPtr == nil || translationLen == 0 {
		return "", false
	}

	count := int(translationLen) / int(unsafe.Sizeof(versionTranslation{}))
	translations := unsafe.Slice(translationPtr, count)
	for _, translation := range translations {
		subBlock := fmt.Sprintf(`\StringFileInfo\%04x%04x\%s`, translation.Language, translation.CodePage, key)
		var valuePtr *uint16
		var valueLen uint32
		if err := windows.VerQueryValue(
			unsafe.Pointer(&versionInfo[0]),
			subBlock,
			unsafe.Pointer(&valuePtr),
			&valueLen,
		); err != nil || valuePtr == nil || valueLen == 0 {
			continue
		}
		value := strings.TrimSpace(windows.UTF16PtrToString(valuePtr))
		if value != "" {
			return value, true
		}
	}
	return "", false
}

func verifyExecutableSignature(path, trustedPath string) error {
	script := fmt.Sprintf(`$ErrorActionPreference = 'Stop'
$UpdateSignature = Get-AuthenticodeSignature -LiteralPath %s
$TrustedSignature = Get-AuthenticodeSignature -LiteralPath %s
if ($UpdateSignature.Status -ne 'Valid') {
    $Status = [string]$UpdateSignature.Status
    $Message = [string]$UpdateSignature.StatusMessage
    if ([string]::IsNullOrWhiteSpace($Message)) { $Message = 'No status message.' }
    throw ('Update executable signature is ' + $Status + ': ' + $Message)
}
if ($TrustedSignature.Status -ne 'Valid') {
    $Status = [string]$TrustedSignature.Status
    $Message = [string]$TrustedSignature.StatusMessage
    if ([string]::IsNullOrWhiteSpace($Message)) { $Message = 'No status message.' }
    throw ('Installed executable signature is ' + $Status + ': ' + $Message)
}
if ($null -eq $UpdateSignature.SignerCertificate -or $null -eq $TrustedSignature.SignerCertificate) {
    throw 'Signer certificate is missing.'
}
if ($UpdateSignature.SignerCertificate.Subject -ne $TrustedSignature.SignerCertificate.Subject) {
    throw 'Update executable publisher does not match the installed app publisher.'
}
`, powershellString(path), powershellString(trustedPath))

	cmd := exec.Command(
		"powershell.exe",
		"-NoProfile",
		"-NonInteractive",
		"-ExecutionPolicy", "Bypass",
		"-EncodedCommand", encodedPowerShell(script),
	)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	output, err := cmd.CombinedOutput()
	if err != nil {
		message := strings.TrimSpace(string(output))
		if message != "" {
			return fmt.Errorf("%w: %s", err, message)
		}
		return err
	}
	return nil
}

func launchPreparedUpdate(update preparedUpdate, processID int) error {
	scriptPath := filepath.Join(os.TempDir(), updateScriptName())
	script := fmt.Sprintf(`$ErrorActionPreference = 'Stop'
$ProcessIdToWait = %d
$Source = %s
$Target = %s
$ExpectedHash = '%s'
try {
    Wait-Process -Id $ProcessIdToWait -Timeout 60 -ErrorAction SilentlyContinue
} catch {}
Start-Sleep -Milliseconds 500
$ActualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Source).Hash.ToLowerInvariant()
if ($ActualHash -ne $ExpectedHash) { exit 2 }
$Signature = Get-AuthenticodeSignature -LiteralPath $Source
if ($Signature.Status -ne 'Valid') { exit 3 }
Copy-Item -LiteralPath $Source -Destination $Target -Force
Start-Process -FilePath $Target
Remove-Item -LiteralPath $Source -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
`, processID, powershellString(update.StagedPath), powershellString(update.TargetPath), strings.ToLower(update.SHA256))

	if err := os.WriteFile(scriptPath, []byte(script), 0o600); err != nil {
		return err
	}
	return exec.Command(
		"powershell.exe",
		"-NoProfile",
		"-ExecutionPolicy", "Bypass",
		"-WindowStyle", "Hidden",
		"-File", scriptPath,
	).Start()
}

func encodedPowerShell(script string) string {
	encoded := utf16.Encode([]rune(script))
	bytes := make([]byte, len(encoded)*2)
	for i, value := range encoded {
		binary.LittleEndian.PutUint16(bytes[i*2:], value)
	}
	return base64.StdEncoding.EncodeToString(bytes)
}

func powershellString(value string) string {
	return "'" + strings.ReplaceAll(value, "'", "''") + "'"
}
