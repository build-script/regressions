package main

import (
	_ "embed"
	"fmt"
	"strings"
)

//go:embed greeting.txt
var greeting string

func main() {
	fmt.Println(strings.TrimSpace(greeting))
}
