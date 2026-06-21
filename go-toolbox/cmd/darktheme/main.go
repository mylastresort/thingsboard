// cmd/darktheme/main.go
// Discovers SCSS files under --path and appends a .dark-theme { } block using
// the bundled Dark Reader JS engine. Requires `node` in PATH.
package main

import (
	_ "embed"
	"flag"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

//go:embed engine.js
var engineJS []byte

func main() {
	root := flag.String("path", ".", "root path to search for *.scss files")
	selector := flag.String("selector", ".dark-theme", "CSS class selector for dark theme block")
	flag.Parse()

	// Write bundled engine to a temp file once (node needs a file path)
	tmp, err := os.CreateTemp("", "dark-engine-*.js")
	if err != nil {
		log.Fatal(err)
	}
	defer os.Remove(tmp.Name())
	if _, err := tmp.Write(engineJS); err != nil {
		log.Fatal(err)
	}
	tmp.Close()

	var processed, skipped int
	err = filepath.WalkDir(*root, func(path string, d os.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return err
		}
		if !strings.HasSuffix(path, ".scss") {
			return nil
		}

		cmd := exec.Command("node", tmp.Name(), path, "--selector", *selector)
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		if runErr := cmd.Run(); runErr != nil {
			fmt.Fprintf(os.Stderr, "⚠ %s: %v\n", path, runErr)
			skipped++
		} else {
			processed++
		}
		return nil
	})
	if err != nil {
		log.Fatal(err)
	}

	fmt.Printf("done: %d files processed, %d skipped\n", processed, skipped)
}
