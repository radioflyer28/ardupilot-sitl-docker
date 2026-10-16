# GitHub Automation

## Purpose

Owns GitHub Actions checks for this repository.

## Ownership

- `workflows/checks.yml`: lightweight host regression, syntax and configuration checks.

## Local Contracts

- PR checks run without firmware/image builds, image pulls, or live containers.
  Compose validation is configuration-only and does not require a daemon.
- Use read-only repository permissions, pinned action revisions, bounded job
  duration and cancellation of superseded runs. Checkout credentials are not retained.
- Keep live firmware qualification opt-in and separate from PR checks.

## Work Guidance

- Exercise the workflow commands locally before claiming verification. A local
  pass does not establish that GitHub has executed the workflow.

## Verification

- Run the commands in `workflows/checks.yml` from the repository root.

## Child DOX Index

No child DOX files.
