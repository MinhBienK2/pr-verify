#!/usr/bin/env python3
"""pr-verify ledger: the single record of repos, criteria, per-round results, issues and reviews.

The ledger is <workspace>/ledger.jsonl, append-only, one JSON object per line. Kinds:

  repo       {"kind":"repo","name":"api","path":"/abs/clone","project":"group/api","mr":12,
              "base":"<sha>","dirty_ok":["appsettings.Development.json"]}
             The canonical repo names. Every other record refers to repos by these names.
             check reads HEAD and dirty state from "path"; "dirty_ok" lists globs that may be
             uncommitted (local env config). A later line with the same name replaces it.
  criterion  {"kind":"criterion","id":"C01","title":"...","oracle":"...","layers":["api","ui:web","db"],
              "repos":["api","web"],"baseline":false}
             layers: api | db | job | log | cli | ui:<app>. baseline:true = needs a before/after run.
             An existing id is rejected unless `add --supersede`.
  result     {"kind":"result","id":"C01","round":1,"verdict":"PASS|FAIL|BLOCKED|SKIP","side":"head|base",
              "evidence":["shots/r1/C01-after-x.png"],"commits":{"api":"abc1234"},"note":"...","mock":false}
             side defaults to head. commits must name every repo of the criterion (>=7 hex chars).
             BLOCKED/SKIP need a note; SKIP counts only with "approved_by_user":"<user's words>".
             For one (id, round, side) the line written last wins.
  issue      {"kind":"issue","id":"B01","criterion":"C03","found_round":1,"repo":"api",
              "status":"open|fixed|needs-decision|decided|out-of-scope","summary":"...",
              "fix_commit":"<sha>","decision":"...","decided_by":"<user's words>","reason":"..."}
             found_round 0 = raised at intake; criterion may be a list or "-". A later line with the
             same id updates the issue (that is how open -> fixed is recorded).
  review     {"kind":"review","round":3,"file":"REVIEW.md","refuted":[]}
             Independent review of the PASSes of that round; refuted lists criterion ids.

Commands (--ws defaults to the current directory and goes BEFORE the subcommand):
  ledger.py --ws W add '<json>' ...         validate and append; `add -f records.jsonl` or `add -` (stdin)
  ledger.py --ws W check                    GREEN/RED; exit 0 only when green (rules in check())
  ledger.py --ws W check --progress         same rules minus "final full round" and "review", for mid-loop
  ledger.py --ws W table [--repo api]       markdown table for the report (optionally one repo's criteria)
  ledger.py --ws W status                   counts per round, issues per status
  ledger.py --ws W coverage --diff api=intake/api-12.diff [...] [--map COVERAGE.md]
                                            files in each diff with no COVERAGE.md row; unknown criterion ids
  ledger.py blank <png> ...                 BLANK/ok per screenshot (exit 1 if any blank/unreadable)
"""
import argparse
import fnmatch
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import zlib

VERDICTS = {"PASS", "FAIL", "BLOCKED", "SKIP"}
ISSUE_STATUS = {"open", "fixed", "needs-decision", "decided", "out-of-scope"}
REQUIRED = {
    "repo": ["name", "path"],
    "criterion": ["id", "title", "oracle", "layers", "repos"],
    "result": ["id", "round", "verdict", "evidence", "commits"],
    "issue": ["id", "criterion", "found_round", "repo", "status", "summary"],
    "review": ["round", "file", "refuted"],
}
LAYER_RE = re.compile(r"^(api|db|job|log|cli|ui:[\w.-]+)$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
EVIDENCE_DIRS = ("shots/", "logs/")
STAMP_ROWS = 32          # evidence.mjs draws its SHA stamp in the top-right corner; blank detection skips
                         # the right half of these rows
MAX_ROWS = 6000          # rows decoded per screenshot for blank detection
MIN_CONTENT_PX = 30      # sampled pixels differing from the background needed to call a shot non-blank


class Rejected(Exception):
    pass


def is_int(v, lo):
    return isinstance(v, int) and not isinstance(v, bool) and v >= lo


# ---------------------------------------------------------------- load / validate

def read_records(ws):
    path = os.path.join(ws, "ledger.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError as e:
                raise Rejected(f"ledger.jsonl:{n}: invalid JSON: {e}")
            if not isinstance(r, dict):
                raise Rejected(f"ledger.jsonl:{n}: record must be a JSON object")
            r["_line"] = n
            out.append(r)
    return out


class Ledger:
    def __init__(self, records):
        self.repos, self.crit, self.issues = {}, {}, {}
        self.results = {}   # (id, side) -> {round -> record}  (last line wins)
        self.reviews = {}   # round -> record
        self.max_round = 0
        for r in records:
            k = r.get("kind")
            if k == "repo":
                self.repos[r["name"]] = r
            elif k == "criterion":
                self.crit[r["id"]] = r
            elif k == "result":
                side = r.get("side", "head")
                self.results.setdefault((r["id"], side), {})[r["round"]] = r
                if side == "head":
                    self.max_round = max(self.max_round, r["round"])
            elif k == "issue":
                self.issues[r["id"]] = r
            elif k == "review":
                self.reviews[r["round"]] = r

    def latest(self, cid, side="head"):
        rs = self.results.get((cid, side), {})
        return rs[max(rs)] if rs else None

    def history(self, cid):
        rs = self.results.get((cid, "head"), {})
        return [rs[k] for k in sorted(rs)]


def evidence_path_error(ws, e):
    if not isinstance(e, str) or not e:
        return f"evidence entries must be non-empty strings, got {e!r}"
    if os.path.isabs(e):
        return f"evidence must be relative to the workspace: {e}"
    real_ws = os.path.realpath(ws)
    real = os.path.realpath(os.path.join(ws, e))
    if os.path.commonpath([real, real_ws]) != real_ws:
        return f"evidence escapes the workspace: {e}"
    rel = os.path.relpath(real, real_ws).replace(os.sep, "/")
    if not rel.startswith(EVIDENCE_DIRS):
        return f"evidence must live under {'/ or '.join(d.rstrip('/') for d in EVIDENCE_DIRS)}/: {e}"
    return None


def validate(r, led, ws, supersede=False):
    if not isinstance(r, dict):
        return "record must be a JSON object"
    k = r.get("kind")
    if k not in REQUIRED:
        return f"kind must be one of {sorted(REQUIRED)}"
    missing = [f for f in REQUIRED[k] if f not in r or r[f] in (None, "")]
    if missing:
        return f"{k} missing {missing}"
    if k == "repo":
        if not os.path.isdir(os.path.join(r["path"], ".git")) and not os.path.isfile(os.path.join(r["path"], ".git")):
            return f"repo path is not a git checkout: {r['path']}"
        if not isinstance(r.get("dirty_ok", []), list):
            return "dirty_ok must be a list of globs"
    elif k == "criterion":
        if r["id"] in led.crit and not supersede:
            return f"criterion {r['id']} already exists (use add --supersede to replace it)"
        if not isinstance(r["layers"], list) or not r["layers"] or not all(isinstance(x, str) and LAYER_RE.match(x) for x in r["layers"]):
            return "layers must be a non-empty list of api|db|job|log|cli|ui:<app>"
        if not isinstance(r["repos"], list) or not r["repos"]:
            return "repos must be a non-empty list of repo names"
        unknown = [x for x in r["repos"] if x not in led.repos]
        if unknown:
            return f"repos {unknown} not declared; add {{'kind':'repo',...}} records first (known: {sorted(led.repos)})"
    elif k == "result":
        c = led.crit.get(r["id"])
        if not c:
            return f"no criterion {r['id']}"
        if not is_int(r["round"], 1):
            return "round must be an integer >= 1"
        if r["verdict"] not in VERDICTS:
            return f"verdict must be one of {sorted(VERDICTS)}"
        if r.get("side", "head") not in ("head", "base"):
            return "side must be head or base"
        if not isinstance(r["evidence"], list):
            return "evidence must be a list of paths relative to the workspace"
        for e in r["evidence"]:
            err = evidence_path_error(ws, e)
            if err:
                return err
        if r["verdict"] == "PASS" and not r["evidence"]:
            return "PASS needs at least one evidence file"
        if r["verdict"] in ("BLOCKED", "SKIP") and not r.get("note"):
            return f"{r['verdict']} needs a note saying why"
        if not isinstance(r["commits"], dict):
            return "commits must be an object {repo: sha}"
        for repo in c["repos"]:
            sha = r["commits"].get(repo, "")
            if not isinstance(sha, str) or not SHA_RE.match(sha):
                return f"commits must give a >=7-char sha for every repo of {r['id']}: {repo}={sha!r}"
    elif k == "issue":
        if not is_int(r["found_round"], 0):
            return "found_round must be an integer >= 0 (0 = raised at intake)"
        if r["status"] not in ISSUE_STATUS:
            return f"status must be one of {sorted(ISSUE_STATUS)}"
        if r["repo"] not in led.repos and r["repo"] != "-":
            return f"repo {r['repo']!r} not declared (known: {sorted(led.repos)}, or '-')"
        crits = r["criterion"] if isinstance(r["criterion"], list) else [r["criterion"]]
        unknown = [x for x in crits if x != "-" and x not in led.crit]
        if unknown:
            return f"criterion {unknown} not in ledger (use '-' for a question not tied to one yet)"
        if r["status"] == "fixed" and not SHA_RE.match(str(r.get("fix_commit", ""))):
            return "fixed needs fix_commit (>=7-char sha)"
        if r["status"] == "decided" and not (r.get("decision") and r.get("decided_by")):
            return "decided needs decision and decided_by (quote the user)"
        if r["status"] == "out-of-scope" and not r.get("reason"):
            return "out-of-scope needs a reason"
    elif k == "review":
        if not is_int(r["round"], 1):
            return "round must be an integer >= 1"
        if not isinstance(r["refuted"], list):
            return "refuted must be a list of criterion ids"
        err = None if os.path.isfile(os.path.join(ws, r["file"])) else f"review file not found: {r['file']}"
        if err:
            return err
    return None


# ---------------------------------------------------------------- png blank detection

def png_blank(path):
    """True when the screenshot is (nearly) one colour, ignoring the stamp corner (top-right).

    Samples every 2nd row and pixel; non-blank once MIN_CONTENT_PX sampled pixels differ from
    the most common colour (so sparse text counts as content, a 3-colour error page is not
    blank: catch those by looking at the shot). Pure stdlib; supports 8-bit, non-interlaced PNG
    (what browsers write) and raises ValueError('unsupported ...') for anything else."""
    with open(path, "rb") as f:
        if f.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError("not a PNG")
        w = h = bpp = ctype = 0
        dec = zlib.decompressobj()
        buf = bytearray()
        prev = None
        y = 0
        counts = {}
        while True:
            head = f.read(8)
            if len(head) < 8:
                break
            ln, typ = struct.unpack(">I4s", head)
            chunk = f.read(ln)
            f.read(4)
            if typ == b"IHDR":
                w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", chunk[:13])
                if depth != 8 or interlace != 0:
                    raise ValueError(f"unsupported PNG (bit depth {depth}, interlace {interlace})")
                bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
                prev = bytearray(w * bpp)
            elif typ == b"IDAT":
                buf += dec.decompress(chunk)
                stride = w * bpp
                last = min(h, MAX_ROWS)
                while len(buf) >= stride + 1 and y < last:
                    line = bytearray(buf[1:stride + 1])
                    unfilter(line, prev, buf[0], bpp)
                    del buf[:stride + 1]
                    prev = line
                    if y % 2 == 0:
                        for x in range(0, stride if y >= STAMP_ROWS else stride // 2, bpp * 2):
                            px = bytes(line[x:x + bpp])
                            counts[px] = counts.get(px, 0) + 1
                        if y % 64 == 0 and content_pixels(counts, ctype) >= MIN_CONTENT_PX:
                            return False
                    y += 1
                if y >= last:
                    break
            elif typ == b"IEND":
                break
    if not counts:
        raise ValueError("no pixel rows decoded")
    return content_pixels(counts, ctype) < MIN_CONTENT_PX


def content_pixels(counts, ctype):
    """Sampled pixels not near the most common colour (palette indices must match exactly)."""
    bg = max(counts, key=counts.get)
    tol = 0 if ctype == 3 else 24
    return sum(n for px, n in counts.items() if max(abs(a - b) for a, b in zip(px, bg)) > tol)


def unfilter(line, prev, ft, bpp):
    if ft == 0:
        return
    if ft == 2:
        for i in range(len(line)):
            line[i] = (line[i] + prev[i]) & 255
        return
    for i in range(len(line)):
        a = line[i - bpp] if i >= bpp else 0
        b = prev[i]
        if ft == 1:
            line[i] = (line[i] + a) & 255
        elif ft == 3:
            line[i] = (line[i] + ((a + b) >> 1)) & 255
        elif ft == 4:
            c = prev[i - bpp] if i >= bpp else 0
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            line[i] = (line[i] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        else:
            raise ValueError(f"bad PNG filter {ft}")


# ---------------------------------------------------------------- git

def git(path, *args):
    p = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise Rejected(f"git {' '.join(args)} in {path}: {p.stderr.strip()}")
    return p.stdout


def repo_state(repo):
    head = git(repo["path"], "rev-parse", "HEAD").strip()
    dirty = []
    for ln in git(repo["path"], "status", "--porcelain").splitlines():
        f = ln[3:].split(" -> ")[-1]
        if not any(fnmatch.fnmatch(f, g) for g in repo.get("dirty_ok", [])):
            dirty.append(f)
    return head, dirty


def is_ancestor(path, a, b):
    return subprocess.run(["git", "-C", path, "merge-base", "--is-ancestor", a, b], capture_output=True).returncode == 0


# ---------------------------------------------------------------- check

def check(ws, progress=False):
    """GREEN means all of:
    - repos: each declared repo's working tree is clean outside dirty_ok;
    - every criterion's latest head-side result: PASS (or SKIP with approved_by_user), taken on the
      repo's current HEAD for every repo it names, with existing, non-empty evidence, screenshots
      not blank (unless note says intentional-blank) and not byte-identical to another criterion's,
      and not mocked;
    - baseline criteria also have a base-side result with evidence;
    - every fixed issue's fix_commit is contained in its repo's HEAD (so, with the rule above, every
      criterion of that repo was re-run after the fix);
    - no issue open or needs-decision;
    - (final, skipped with --progress) every criterion has a head-side result in the last round R, and
      a review record for R exists with nothing refuted."""
    led = Ledger(read_records(ws))
    problems = []
    if not led.repos:
        problems.append("no repo records: add {'kind':'repo','name':...,'path':...} for every repo")
    if not led.crit:
        problems.append("no criteria in ledger")
    heads = {}
    for name, repo in sorted(led.repos.items()):
        head, dirty = repo_state(repo)
        heads[name] = head
        if dirty:
            problems.append(f"repo {name}: uncommitted changes outside dirty_ok: {', '.join(dirty[:8])}")
    img_owner = {}
    R = led.max_round
    for cid, c in sorted(led.crit.items()):
        r = led.latest(cid)
        if not r:
            problems.append(f"{cid}: no result yet")
            continue
        if r["verdict"] != "PASS" and not (r["verdict"] == "SKIP" and r.get("approved_by_user")):
            problems.append(f"{cid}: latest verdict {r['verdict']} (round {r['round']})")
        if r.get("mock") and r["verdict"] == "PASS":
            problems.append(f"{cid}: PASS rests on mocked/stubbed behaviour; mocked evidence cannot accept a criterion")
        if not progress and r["round"] != R:
            problems.append(f"{cid}: latest result is round {r['round']}; the final round {R} must re-run every criterion")
        for repo in c["repos"]:
            got = r["commits"].get(repo, "")
            if repo in heads and not heads[repo].startswith(got):
                problems.append(f"{cid}: result taken on {repo}@{got}, HEAD is {heads[repo][:10]}: re-run on HEAD")
        sides = [("head", r)]
        if c.get("baseline"):
            b = led.latest(cid, "base")
            if not b or not b["evidence"]:
                problems.append(f"{cid}: baseline criterion has no base-side (before) result with evidence")
            else:
                sides.append(("base", b))
        for side, rec in sides:
            for e in rec["evidence"]:
                err = evidence_path_error(ws, e)
                p = os.path.join(ws, e)
                if err:
                    problems.append(f"{cid}: {err}")
                elif not os.path.isfile(p) or os.path.getsize(p) == 0:
                    problems.append(f"{cid}: evidence missing or empty: {e}")
                elif e.lower().endswith(".png"):
                    with open(p, "rb") as fh:
                        digest = hashlib.sha256(fh.read()).hexdigest()
                    other = img_owner.setdefault(digest, cid)
                    if other != cid:
                        problems.append(f"{cid}: screenshot {e} is byte-identical to evidence of {other} (likely an error/redirect page)")
                    if "intentional-blank" in (rec.get("note") or ""):
                        continue
                    try:
                        if png_blank(p):
                            problems.append(f"{cid}: blank screenshot {e} (note 'intentional-blank' if the blank page is the evidence)")
                    except Exception as ex:
                        problems.append(f"{cid}: unreadable image {e}: {ex}")
    for iid, i in sorted(led.issues.items()):
        if i["status"] in ("open", "needs-decision"):
            problems.append(f"{iid}: issue {i['status']}: {i['summary']}")
        if i["status"] == "fixed" and i["repo"] in led.repos:
            if not is_ancestor(led.repos[i["repo"]]["path"], i["fix_commit"], heads.get(i["repo"], "HEAD")):
                problems.append(f"{iid}: fix_commit {i['fix_commit']} is not in {i['repo']} HEAD")
    if not progress:
        rv = led.reviews.get(R)
        if not rv:
            problems.append(f"no independent review recorded for final round {R} (kind: review)")
        elif rv["refuted"]:
            problems.append(f"review of round {R} refuted {rv['refuted']}: triage them")
    return problems


# ---------------------------------------------------------------- table / status / coverage

def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def table(ws, only_repo=None):
    led = Ledger(read_records(ws))
    out = ["| ID | Tiêu chí | Kết quả | Lịch sử vòng | Bằng chứng |", "|---|---|---|---|---|"]
    for cid, c in sorted(led.crit.items()):
        if only_repo and only_repo not in c["repos"]:
            continue
        hist = led.history(cid)
        r = hist[-1] if hist else None
        trail = " → ".join(f"r{x['round']}:{x['verdict']}" for x in hist) or "—"
        ev = list(r["evidence"]) if r else []
        b = led.latest(cid, "base")
        if b:
            ev = [f"before: {e}" for e in b["evidence"]] + ev
        out.append(f"| {cid} | {cell(c['title'])} | **{r['verdict'] if r else '—'}** | {trail} | {', '.join(f'`{cell(e)}`' for e in ev)} |")
    issues = [i for i in led.issues.values() if not only_repo or i["repo"] in (only_repo, "-")]
    if issues:
        out += ["", "| Lỗi | Tiêu chí | Repo | Vòng phát hiện | Trạng thái | Commit sửa / quyết định | Mô tả |", "|---|---|---|---|---|---|---|"]
        for i in sorted(issues, key=lambda x: x["id"]):
            crit = ", ".join(i["criterion"]) if isinstance(i["criterion"], list) else i["criterion"]
            extra = i.get("fix_commit") or i.get("decision") or i.get("reason") or ""
            out.append(f"| {i['id']} | {crit} | {i['repo']} | {i['found_round']} | {i['status']} | {cell(extra)} | {cell(i['summary'])} |")
    return "\n".join(out)


def diff_files(path):
    """Paths changed in a unified diff: `git diff` (diff --git a/x b/y) or `glab mr diff` (--- x / +++ x).
    Hunk bodies are skipped by their line counts, so content lines starting with ---/+++ are not headers."""
    files, old = [], None
    lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    i = 0
    strip = lambda p: re.sub(r"^[ab]/", "", p.split("\t")[0].strip().strip('"'))
    while i < len(lines):
        ln = lines[i]
        m = re.match(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@", ln)
        if m:
            old_n = int(m.group(1) if m.group(1) is not None else 1)
            new_n = int(m.group(2) if m.group(2) is not None else 1)
            i += 1
            while i < len(lines) and (old_n > 0 or new_n > 0):
                c = lines[i][:1]
                if c == "-":
                    old_n -= 1
                elif c == "+":
                    new_n -= 1
                elif c != "\\":
                    old_n -= 1
                    new_n -= 1
                i += 1
            continue
        if ln.startswith("--- "):
            old = strip(ln[4:])
        elif ln.startswith("+++ "):
            new = strip(ln[4:])
            f = old if new == "/dev/null" else new
            if f and f != "/dev/null" and f not in files:
                files.append(f)
        else:
            m = re.match(r"^diff --git a/(.+?) b/(.+)$", ln)
            if m and m.group(2) not in files:
                files.append(m.group(2))  # also catches binary/rename-only entries with no ---/+++
        i += 1
    return files


def coverage(ws, diffs, map_file):
    led = Ledger(read_records(ws))
    rows = []
    with open(os.path.join(ws, map_file), encoding="utf-8") as f:
        lines = f.read().splitlines()
    sep = re.compile(r"^\s*\|[\s|:-]+\|\s*$")
    for n, ln in enumerate(lines):
        if not ln.lstrip().startswith("|") or sep.match(ln):
            continue
        if n + 1 < len(lines) and sep.match(lines[n + 1]):
            continue  # header row
        cells = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(cells) >= 4:
            rows.append((cells[0], re.sub(r":[\d,\- ]+$", "", cells[1].strip("`")), cells[-1]))
    problems = []
    for spec in diffs:
        repo, path = spec.split("=", 1) if "=" in spec else ("", spec)
        for fpath in diff_files(os.path.join(ws, path) if not os.path.isabs(path) else path):
            hit = [r for r in rows if (not repo or r[0] == repo) and (fpath == r[1] or fnmatch.fnmatch(fpath, r[1]))]
            if not hit:
                problems.append(f"{repo or '?'}: {fpath} has no COVERAGE row")
    for repo, fpath, crits in rows:
        ids = re.findall(r"\bC\d+\b", crits)
        for cid in ids:
            if cid not in led.crit:
                problems.append(f"COVERAGE {repo} {fpath}: {cid} not in ledger")
        if not ids and not re.search(r"—\s*\S|-\s+\S", crits):
            problems.append(f"COVERAGE {repo} {fpath}: no criterion and no reason")
    return problems


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ws", default=".", help="workspace directory holding ledger.jsonl (before the subcommand)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("records", nargs="*")
    a.add_argument("-f", dest="file", help="JSONL file of records, '-' for stdin")
    a.add_argument("--supersede", action="store_true", help="allow replacing an existing criterion id")
    c = sub.add_parser("check")
    c.add_argument("--progress", action="store_true", help="mid-loop check: skip final-round and review rules")
    t = sub.add_parser("table")
    t.add_argument("--repo")
    sub.add_parser("status")
    cv = sub.add_parser("coverage")
    cv.add_argument("--diff", action="append", required=True, help="name=path/to/mr.diff")
    cv.add_argument("--map", default="COVERAGE.md")
    b = sub.add_parser("blank")
    b.add_argument("pngs", nargs="+")
    args = ap.parse_args()
    ws = args.ws
    if args.cmd != "blank" and not os.path.isdir(ws):
        sys.exit(f"rejected: workspace {ws} does not exist")

    try:
        if args.cmd == "add":
            lines = list(args.records)
            if args.file:
                src = sys.stdin if args.file == "-" else open(args.file, encoding="utf-8")
                lines += [ln for ln in src.read().splitlines() if ln.strip()]
            if not lines:
                sys.exit("rejected: nothing to add")
            records = read_records(ws)
            recs = []
            for s in lines:
                try:
                    r = json.loads(s)
                except json.JSONDecodeError as e:
                    raise Rejected(f"{s[:80]}: invalid JSON: {e}")
                err = validate(r, Ledger(records + recs), ws, args.supersede)
                if err:
                    raise Rejected(f"{s[:80]}: {err}")
                recs.append(r)
            with open(os.path.join(ws, "ledger.jsonl"), "a", encoding="utf-8") as f:
                for r in recs:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"appended {len(recs)}")
        elif args.cmd == "check":
            problems = check(ws, args.progress)
            label = "progress" if args.progress else "final"
            if problems:
                print(f"RED ({label})")
                for p in problems:
                    print("  -", p)
                sys.exit(1)
            print(f"GREEN ({label}): every criterion PASS on current HEAD with real evidence; no open issue; every fix contained in HEAD"
                  + ("" if args.progress else "; final round re-ran every criterion; independent review refuted nothing"))
        elif args.cmd == "table":
            print(table(ws, args.repo))
        elif args.cmd == "status":
            led = Ledger(read_records(ws))
            rounds = {}
            for (cid, side), rs in led.results.items():
                for r in rs.values():
                    key = f"{r['round']}{'' if side == 'head' else ' (base)'}"
                    rounds.setdefault(key, {}).setdefault(r["verdict"], 0)
                    rounds[key][r["verdict"]] += 1
            for k in sorted(rounds, key=lambda s: (int(s.split()[0]), s)):
                print(f"round {k}: " + ", ".join(f"{v}={n}" for v, n in sorted(rounds[k].items())))
            st = {}
            for i in led.issues.values():
                st[i["status"]] = st.get(i["status"], 0) + 1
            print(f"criteria: {len(led.crit)}; issues: " + (", ".join(f"{k}={v}" for k, v in sorted(st.items())) or "none"))
        elif args.cmd == "coverage":
            problems = coverage(ws, args.diff, args.map)
            for p in problems:
                print("  -", p)
            print(f"{len(problems)} coverage gap(s)")
            sys.exit(1 if problems else 0)
        elif args.cmd == "blank":
            bad = 0
            for p in args.pngs:
                try:
                    blank = png_blank(p)
                except Exception as e:
                    print(f"ERROR {p}: {e}")
                    bad += 1
                    continue
                print(f"{'BLANK' if blank else 'ok   '} {p}")
                bad += blank
            sys.exit(1 if bad else 0)
    except Rejected as e:
        sys.exit(f"rejected: {e}")
    except OSError as e:
        sys.exit(f"rejected: {e}")


if __name__ == "__main__":
    main()
