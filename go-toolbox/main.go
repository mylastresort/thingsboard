package main

import (
	"os"

	"pmtool/internal/interpreter"
)

func main() {
	interpreter.Run(os.Args[1:])
}