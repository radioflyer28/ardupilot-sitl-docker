# GitHub Automation

## Purpose

Owns GitHub Actions checks for this repository.

## Ownership

- `workflows/checks.yml`: lightweight host regression, syntax, line-ending and
  configuration checks.

## Local Contracts

- PR checks run without firmware/image builds, image pulls, or live containers.
  Compose validation is configuration-only and does not require a daemon.
- Use read-only repository permissions, pinned action revisions, bounded job
  duration and cancellation of superseded runs. Checkout credentials are not retained.
- Keep live firmware qualification opt-in and separate from PR checks.
- The line-ending check fails on any `i/crlf` or `w/crlf` entry for
  copied-then-executed files; `.gitattributes` is the fix, not a per-file cleanup.

## Work Guidance

- Exercise the workflow commands locally before claiming verification. A local
  pass does not establish that GitHub has executed the workflow.

## Verification

- Run the commands in `workflows/checks.yml` from the repository root.

## Child DOX Index

No child DOX files.
