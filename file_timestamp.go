package main

import "time"

const (
	fileTimestampLayout  = "2006-01-02 15:04:05 -07:00"
	unknownFileTimestamp = "unknown"
)

func formatFileTimestamp(value time.Time, available bool) string {
	if !available || value.IsZero() || value.Year() < 1 || value.Year() > 9999 {
		return unknownFileTimestamp
	}
	localValue := value.Local()
	if localValue.Year() < 1 || localValue.Year() > 9999 {
		return unknownFileTimestamp
	}
	return localValue.Format(fileTimestampLayout)
}
