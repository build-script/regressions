package main

import (
	"fmt"
	"runtime"
)

func main() {
	fmt.Println("built for", runtime.GOOS, runtime.GOARCH)
}
