package main

import (
	"context"
	"crypto/sha1"
	"crypto/sha256"
	"encoding/hex"
	"hash"
	"io"
	"os"
	"strings"

	"github.com/zeebo/blake3"
)

type hashAlgorithm string

const (
	hashAlgorithmOff    hashAlgorithm = "off"
	hashAlgorithmBLAKE3 hashAlgorithm = "blake3"
	hashAlgorithmSHA1   hashAlgorithm = "sha1"
	hashAlgorithmSHA256 hashAlgorithm = "sha256"
)

func defaultHashAlgorithm() hashAlgorithm {
	return hashAlgorithmBLAKE3
}

func allHashAlgorithms() []hashAlgorithm {
	return []hashAlgorithm{
		hashAlgorithmOff,
		hashAlgorithmBLAKE3,
		hashAlgorithmSHA1,
		hashAlgorithmSHA256,
	}
}

func (a hashAlgorithm) Enabled() bool {
	return a != hashAlgorithmOff
}

func (a hashAlgorithm) CSVName() string {
	switch a {
	case hashAlgorithmBLAKE3:
		return "BLAKE3"
	case hashAlgorithmSHA1:
		return "SHA-1"
	case hashAlgorithmSHA256:
		return "SHA-256"
	default:
		return ""
	}
}

func (a hashAlgorithm) OptionLabel() string {
	switch a {
	case hashAlgorithmBLAKE3:
		return "Fast (BLAKE3)"
	case hashAlgorithmSHA1:
		return "Medium (SHA-1)"
	case hashAlgorithmSHA256:
		return "Strong (SHA-256)"
	default:
		return "Off"
	}
}

func (a hashAlgorithm) ShortLabel() string {
	switch a {
	case hashAlgorithmBLAKE3:
		return "BLAKE3"
	case hashAlgorithmSHA1:
		return "SHA-1"
	case hashAlgorithmSHA256:
		return "SHA-256"
	default:
		return "Off"
	}
}

func (a hashAlgorithm) Next() hashAlgorithm {
	values := allHashAlgorithms()
	for index, value := range values {
		if value == a {
			return values[(index+1)%len(values)]
		}
	}
	return defaultHashAlgorithm()
}

func parseHashAlgorithm(value string) hashAlgorithm {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "", "off", "none":
		return hashAlgorithmOff
	case "blake3", "fast", "fast (blake3)":
		return hashAlgorithmBLAKE3
	case "sha1", "sha-1", "medium", "medium (sha-1)":
		return hashAlgorithmSHA1
	case "sha256", "sha-256", "strong", "strong (sha-256)":
		return hashAlgorithmSHA256
	default:
		return defaultHashAlgorithm()
	}
}

func hashAlgorithmOptionLabels() []string {
	values := allHashAlgorithms()
	labels := make([]string, 0, len(values))
	for _, value := range values {
		labels = append(labels, value.OptionLabel())
	}
	return labels
}

func hashFile(ctx context.Context, path string, algorithm hashAlgorithm) (string, error) {
	if !algorithm.Enabled() {
		return "", nil
	}

	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()

	var digest hash.Hash
	switch algorithm {
	case hashAlgorithmBLAKE3:
		digest = blake3.New()
	case hashAlgorithmSHA1:
		digest = sha1.New()
	default:
		digest = sha256.New()
	}

	buffer := make([]byte, 1<<20)
	for {
		select {
		case <-ctx.Done():
			return "", ctx.Err()
		default:
		}
		count, err := file.Read(buffer)
		if count > 0 {
			if _, writeErr := digest.Write(buffer[:count]); writeErr != nil {
				return "", writeErr
			}
		}
		if err == io.EOF {
			break
		}
		if err != nil {
			return "", err
		}
	}
	return hex.EncodeToString(digest.Sum(nil)), nil
}
