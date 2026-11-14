# pr-verify

An agent skill for end-to-end acceptance testing ("nghiệm thu") of a feature that spans one or more **GitLab** merge requests.

Give it the feature's goal and the MRs. The agent then:

1. derives acceptance criteria from the goal, the diffs and linked issues, covering every flow the change touches (main flow, roles/permissions, bad input, dependency failures, data integrity, legacy data, config modes, regressions, security);
2. runs them against a real environment on the pinned head SHA, plus the base SHA for before/after on criteria that change existing behaviour;
3. records every result with real evidence (screenshots, API and SQL captures) in an append-only ledger;
4. triages failures, fixes product bugs with a regression test that is red first, and re-runs in rounds until `ledger.py check` reports **GREEN (final)**. Green requires a final round that re-runs every criterion on the final HEAD, plus an independent review that refutes nothing;
5. posts a description block and one evidence comment, with screenshots uploaded to the right project, on each MR. Pushing and posting happen only when you say so.

The skill's instructions are written in Vietnamese; the scripts and their `--help` are in English.

> GitLab only: publishing uses `glab`. GitHub pull requests are not supported.

## Requirements

- git, bash, python3 ≥ 3.8 (scripts use the standard library only)
- [`glab`](https://gitlab.com/gitlab-org/cli) authenticated to your GitLab host (`glab auth login --hostname <host>`), recent enough to support `glab api --form`
- Node + Playwright in the project that holds your test harness, for `scripts/evidence.mjs`
- Linux recommended: the environment guide uses `systemd-run --user`, `journalctl` and `fuser`; `capture.sh` uses GNU `date -Iseconds`
- An agent that can spawn a subagent (for the independent review step)

## Install

```bash
# Claude Code
git clone https://github.com/MinhBienK2/pr-verify ~/.claude/skills/pr-verify
# other agents: clone into their skills directory (e.g. ~/.agents/skills/pr-verify)
```

In the docs, `<skill-dir>` means this folder.

## Use

Ask your agent, for example:

> nghiệm thu MR group/api!12 và group/web!34: admins can restrict each menu by role

or

> verify feature X end to end with evidence

The workspace defaults to `$HOME/.pr-verify/<slug>/`; override it with `PR_VERIFY_HOME`.

## Layout

| Path | What |
|---|---|
| `SKILL.md` | The process: 9 steps, each with a completion criterion |
| `references/criteria.md` | Deriving criteria, flow classes, `COVERAGE.md` |
| `references/environment.md` | Pinning SHAs, data safety, long-running processes |
| `references/evidence.md` | Evidence standards for UI, API, DB |
| `references/triage.md` | Classifying failures, the fix loop, the final round, independent review |
| `references/report.md` | MR description and evidence comment templates, publishing |
| `scripts/ledger.py` | Ledger: `add`, `check` (GREEN/RED), `table`, `status`, `coverage`, `blank` |
| `scripts/capture.sh` | Run a command and keep stamped, secret-masked output as evidence |
| `scripts/evidence.mjs` | Playwright helpers: `settle`, `shot` (SHA stamp), `card` (API/SQL as image) |
| `scripts/gl_evidence.py` | Check the MR head SHA, upload images, create or update one note or description block |
| `agents/openai.yaml` | Codex UI metadata |

See [CREDITS.md](CREDITS.md) for the ideas this builds on.
