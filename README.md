# pr-verify

An agent skill for acceptance testing ("nghiệm thu") a change by running every flow it touches against a real environment, with evidence. It works for a new feature, a requirement, a bug fix or a refactor; for a web UI, an API, a background job, a CLI or a library; whether the input is a merge request, a branch, or a requirement in plain words.

The skill is a testing method, not a harness. It walks the agent through one flow:

1. **Understand the requirement**: what the change must do, for whom, and what "correct" means; split it into checkable items, surface requirements the code does not implement yet, ask about ambiguities.
2. **Map the flows**: actors/roles × entry points (UI, API, CLI, job, webhook, import…) × data states → outcome and side effects, including callers outside the diff that the change affects.
3. **Design test cases** layer by layer: main flow, branches, bad input and boundaries, permissions, lifecycle and state transitions, concurrency and idempotency, async work, dependency failures, data integrity, legacy data and migrations, configuration, time zones, regressions, security, non-functional limits. Bug fixes are reproduced on the base first; refactors are compared with the base.
4. **Run for real** on the pinned SHA, with representative test data, touching only test hosts; every case has an oracle drawn from a source of truth and shown able to fail.
5. **Triage failures** (product bug, pre-existing, harness, environment, needs a decision). Code is changed only when the user asked for fixes.
6. **Look for what is missing**: explore the running product, and for large features have a fresh subagent list flows from the requirement and diff alone, until no new flow turns up.
7. **Report honestly**: requirement → flow → case → result → evidence; nothing unrun is called passing.

Results live in a plain Markdown file (`VERIFY.md`) in the workspace. Publishing to a GitLab MR is an optional extra.

The skill's instructions are written in Vietnamese; the scripts and their `--help` are in English.

## Requirements

- git, bash ≥ 3, python3 ≥ 3.8 (scripts use the standard library only)
- Optional: Node + Playwright in the project that holds your test harness, for `scripts/evidence.mjs`
- Optional: [`glab`](https://gitlab.com/gitlab-org/cli) authenticated to your GitLab host, recent enough to support `glab api --form`, to publish to a merge request
- Linux recommended: the environment guide uses `systemd-run --user` and `fuser`; `capture.sh` uses GNU `date -Iseconds`

## Install

```bash
# Claude Code
git clone https://github.com/MinhBienK2/pr-verify ~/.claude/skills/pr-verify
# other agents: clone into their skills directory (e.g. ~/.agents/skills/pr-verify)
```

In the docs, `<skill-dir>` means this folder.

## Use

Ask your agent, for example:

> nghiệm thu tính năng mã giảm giá trên nhánh feat/discount

> kiểm tra bản fix bug job gửi email nhắc hạn bị gửi trùng

> verify MR group/api!12 end to end

The workspace defaults to `$HOME/.pr-verify/<slug>/`; override it with `PR_VERIFY_HOME`.

## Layout

| Path | What |
|---|---|
| `SKILL.md` | The method: seven steps, each with a completion criterion, and the hard rules |
| `references/test-design.md` | Flow map, test layers, case design techniques, oracles, bug fixes and refactors, examples |
| `references/environment.md` | Pinning SHAs, data safety, long-running processes, health checks |
| `references/evidence.md` | What evidence looks like for UI, API, DB, jobs, CLIs and libraries |
| `references/triage.md` | Classifying failures, fixing (when asked), re-running |
| `references/publish-gitlab.md` | Optional: reading a GitLab MR, posting results with screenshots |
| `scripts/capture.sh` | Optional: run a command and keep stamped, secret-masked output as evidence |
| `scripts/evidence.mjs` | Optional Playwright helpers: `settle`, `shot` (SHA stamp), `card` (text output as image) |
| `scripts/gl_evidence.py` | Optional: check the MR head SHA, upload workspace images, create or update one note or description block |
| `agents/openai.yaml` | Codex UI metadata |

See [CREDITS.md](CREDITS.md) for the ideas this builds on.
