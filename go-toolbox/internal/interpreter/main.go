// Package interpreter dispatches `pmtool <unit> [flags]` to the standalone
// cmd/<unit> sources, building each with `go build` on first use (cached
// after) and running it as a real OS process — works against the live
// source tree, no Docker, no sibling images required.
package interpreter

import (
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"runtime"
	"strings"

	"github.com/chzyer/readline"
)

// ponytail: units as a flat table, not a plugin system — add a row here
// when a new cmd/<unit> shows up.
type unit struct {
	name string
	desc string
}

var units = []unit{
    {"load",      "load PdM CSVs into ThingsBoard as devices + timeseries"},
    {"dash",      "simulate devices, publishing telemetry over MQTT"},
    {"alarm",     "create/clear ThingsBoard alarms (subcommands: create, clear)"},
    {"darktheme", "append .dark-theme CSS block to ui-ngx SCSS files (requires node in PATH)"},
}

const binDir = "/tmp/pmtool-bin"

// Run is the entrypoint: pass os.Args[1:]. With no args it loops the
// interactive REPL forever — ponytail: exit/EOF restarts the prompt instead
// of returning, since this process is PID 1 in the container and returning
// would stop it. To actually leave without killing the container, detach
// with Ctrl-P Ctrl-Q (docker attach's detach sequence); exit/Ctrl-D just
// bounces back to a fresh prompt. docker stop / Ctrl-C ends it for real.
func Run(args []string) {
	if len(args) == 0 {
		fmt.Printf("pmtool %s — interactive mode  (type 'help' or 'exit')\n", runtime.Version())
		for {
			runInteractive()
		}
	}
	if args[0] == "help" || args[0] == "-h" || args[0] == "--help" {
		rootHelp()
		return
	}
	runUnit(args[0], args[1:])
}

func runInteractive() {
	rl, err := readline.New("pmtool> ")
	if err != nil {
		log.Fatalf("pmtool: readline: %v", err)
	}
	defer rl.Close()
	for {
		line, err := rl.Readline()
		if err == readline.ErrInterrupt { // Ctrl-C: clear the line, stay in the REPL
			continue
		}
		if err == io.EOF { // Ctrl-D
			return
		}
		if err != nil {
			log.Printf("pmtool: %v", err)
			return
		}
		args := strings.Fields(line)
		if len(args) == 0 {
			continue
		}
		switch args[0] {
		case "exit", "quit":
			return
		case "help", "-h", "--help":
			rootHelp()
		default:
			runUnit(args[0], args[1:])
		}
	}
}

func rootHelp() {
	fmt.Printf("pmtool %s — predictive-maintenance toolbox for ThingsBoard\n\n", runtime.Version())
	fmt.Println("Usage:")
	fmt.Println("  pmtool <unit> [flags]")
	fmt.Println("  pmtool help            this message")
	fmt.Println()
	fmt.Println("Units:")
	for _, u := range units {
		fmt.Printf("  %-10s %s\n", u.name, u.desc)
	}
	fmt.Println()
	fmt.Println("Run 'pmtool <unit> -h' for unit-specific flags.")
}

// runUnit builds cmd/<name> on first use (cached after that) and execs it,
// streaming stdio straight through so unit flags/output behave exactly as
// if you'd run that binary directly.
func runUnit(name string, args []string) {
	found := false
	for _, u := range units {
		if u.name == name {
			found = true
			break
		}
	}
	if !found {
		fmt.Fprintf(os.Stderr, "pmtool: unknown unit %q (try 'help')\n", name)
		return
	}

	bin, err := buildUnit(name)
	if err != nil {
		log.Printf("pmtool: build %s: %v", name, err)
		return
	}

	cmd := exec.Command(bin, args...)
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	if err := cmd.Run(); err != nil {
		log.Printf("pmtool: %s: %v", name, err)
	}
}

func buildUnit(name string) (string, error) {
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		return "", err
	}
	bin := binDir + "/" + name
	if _, err := os.Stat(bin); err == nil {
		return bin, nil // ponytail: cached after first build; rm -rf binDir to force a rebuild
	}
	cmd := exec.Command("go", "build", "-o", bin, "./cmd/"+name)
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return "", err
	}
	return bin, nil
}