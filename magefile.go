//go:build mage

// Copyright (c) 2026 Petar Djukic. All rights reserved.
// SPDX-License-Identifier: MIT

// Mage build for writing-skills (GH-219). Two targets:
//
//	mage test   run the release gate: scripts/run-tests.sh — every
//	            discovered test under .claude/ plus the mirrors-match
//	            check; zero tests found is a failure by that script's
//	            own contract
//	mage tag    gated release: refuse off main or a dirty worktree, run
//	            the gate, then create the next v0.YYYYMMDD.N tag,
//	            counting revisions over local AND remote tags so two
//	            machines cannot mint the same one
//
// The scheme and the guards follow the fleet convention
// (declarative-agents magefiles/tag.go is the heavyweight reference;
// this is the minimal shape for a repo whose only gate is its test
// suite).
package main

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const (
	tagPrefix  = "v0."
	baseBranch = "main"
)

// Test runs the release gate: every test plus the mirrors-match check.
func Test() error {
	cmd := exec.Command("bash", "scripts/run-tests.sh")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

// Tag creates the next v0.YYYYMMDD.N release tag from a green, clean main.
func Tag() error {
	branch, err := gitOutput("rev-parse", "--abbrev-ref", "HEAD")
	if err != nil {
		return fmt.Errorf("getting current branch: %w", err)
	}
	if branch != baseBranch {
		return fmt.Errorf("tag must be run from %s (currently on %s)",
			baseBranch, branch)
	}
	status, err := gitOutput("status", "--porcelain")
	if err != nil {
		return fmt.Errorf("checking worktree: %w", err)
	}
	if status != "" {
		return errors.New("release gates require a clean worktree")
	}
	commit, err := gitOutput("rev-parse", "HEAD")
	if err != nil {
		return fmt.Errorf("resolving release commit: %w", err)
	}

	fmt.Printf("release: verifying commit %s\n", commit)
	if err := Test(); err != nil {
		return fmt.Errorf("release gate failed: %w", err)
	}
	// The gate must have run against the commit being tagged.
	after, err := gitOutput("rev-parse", "HEAD")
	if err != nil {
		return fmt.Errorf("verifying release commit after gates: %w", err)
	}
	if after != commit {
		return fmt.Errorf("release commit changed while gates ran: "+
			"started %s, now %s", commit, after)
	}

	date := time.Now().Format("20060102")
	local, err := gitOutput("tag", "-l", tagPrefix+date+".*")
	if err != nil {
		return fmt.Errorf("listing local release tags: %w", err)
	}
	remote, err := remoteTags(date)
	if err != nil {
		return fmt.Errorf("listing remote release tags: %w", err)
	}
	tag := fmt.Sprintf("%s%s.%d", tagPrefix, date,
		nextRevision(date, local+"\n"+remote))

	fmt.Printf("creating release tag %s\n", tag)
	if out, err := exec.Command("git", "tag", tag, commit).CombinedOutput(); err != nil {
		return fmt.Errorf("creating release tag: %s: %w", strings.TrimSpace(string(out)), err)
	}
	fmt.Printf("done — created %s\n", tag)
	return nil
}

func nextRevision(date, tags string) int {
	revRe := regexp.MustCompile(`^` + regexp.QuoteMeta(tagPrefix) +
		regexp.QuoteMeta(date) + `\.(\d+)$`)
	maxRev := -1
	for _, line := range strings.Split(tags, "\n") {
		m := revRe.FindStringSubmatch(strings.TrimSpace(line))
		if len(m) != 2 {
			continue
		}
		if rev, err := strconv.Atoi(m[1]); err == nil && rev > maxRev {
			maxRev = rev
		}
	}
	return maxRev + 1
}

func remoteTags(date string) (string, error) {
	out, err := exec.Command("git", "ls-remote", "--tags", "origin",
		tagPrefix+date+".*").Output()
	if err != nil {
		return "", err
	}
	var tags []string
	for _, line := range strings.Split(string(out), "\n") {
		parts := strings.SplitN(strings.TrimSpace(line), "\t", 2)
		if len(parts) == 2 {
			tags = append(tags, strings.TrimPrefix(parts[1], "refs/tags/"))
		}
	}
	return strings.Join(tags, "\n"), nil
}

func gitOutput(args ...string) (string, error) {
	out, err := exec.Command("git", args...).Output()
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(out)), nil
}
