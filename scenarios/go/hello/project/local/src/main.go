package main

import (
	"fmt"
	"runtime"
)

func main() {
	fmt.Println("built with", runtime.Version())
}
