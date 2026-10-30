package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"time"

	"ragflow/internal/parser/parser"
)

// This calls the pinned upstream HTML parser, not a reimplementation.
func main() {
	data, err := os.ReadFile(os.Args[1])
	if err != nil {
		panic(err)
	}
	started := time.Now()
	result := parser.NewHTMLParser().ParseWithResult(context.Background(), "source.html", data)
	if result.Err != nil {
		panic(result.Err)
	}
	items := make([]map[string]any, 0, len(result.JSON))
	for _, item := range result.JSON {
		items = append(items, item.ToMap())
	}
	sha := sha256.Sum256(data)
	report := map[string]any{
		"sourceDigest": hex.EncodeToString(sha[:]), "items": items,
		"warnings": result.Warnings, "file": result.File,
		"elapsedMs":      time.Since(started).Milliseconds(),
		"upstreamCommit": "ac29b4b29928ca65d3efca19b6cfae3f86069b81",
		"mode":           "UPSTREAM_HTML_PARSER_NO_CGO_NOT_SERVER",
	}
	if err := json.NewEncoder(os.Stdout).Encode(report); err != nil {
		panic(err)
	}
}
