#!/usr/bin/env bash
# pr-verify capture: run one command and keep its full, stamped output as evidence.
#
#   capture.sh <out-file> [--repo name=/path ...] [--expect-exit N] [--max-bytes N] -- <command...>
#
# <out-file> gets:
#   # evidence  time=<iso>  cwd=<dir>
#   # repo <name> sha=<short> dirty=<0|1>     (one line per --repo)
#   # cmd: <command as typed>
#   <stdout+stderr, secrets masked, truncated at --max-bytes (default 2000000) with a marker>
#   exit=<N>
# Exit status: 0 when the command's exit equals --expect-exit (default 0); 1 when it differs;
# 2 when capture.sh itself failed (bad usage, cannot write) and the command may not have run.
#
# Pass secrets through environment variables ("$TOKEN"), never as literal flags: the cmd line is
# recorded as typed, so "-H \"Authorization: Bearer $TOKEN\"" records the variable name, while a
# literal value is only masked when it matches a known shape (header, key=value, URL user:pass,
# -p<pw>, glpat-, AKIA, JWT, PEM, "Bearer <value>"). The values of environment variables whose name
# contains a secret word (PASS, PWD, TOKEN, SECRET, KEY, CRED, AUTH, COOKIE, SESSION, JWT, PAT -
# matched case-insensitively) are replaced with their name wherever they appear. A value that only
# looks like a credential (long, mixed with digits or punctuation) is masked even under an unknown
# name; ordinary words are left alone, so a log line stays readable.
# The command's stdin is /dev/null. The raw output is kept in a private temp directory and removed
# on exit; a SIGKILL cannot be trapped, so a killed capture can leave an unmasked file behind in
# $TMPDIR/prv-capture.* (mode 0700). Stale ones are swept on the next run.
set -uo pipefail

usage() { awk 'NR>1 && /^#/ {sub(/^# ?/,""); print; next} NR>1 {exit}' "$0"; }
die() { echo "capture.sh: $*" >&2; exit 2; }

(( BASH_VERSINFO[0] >= 3 )) || die "bash >= 3 required (found ${BASH_VERSION:-unknown})"

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { usage; exit 0; }
out="${1:-}"
[[ -n "$out" && "$out" != --* ]] || { usage >&2; exit 2; }
shift
repos=()
expect=0
max=2000000
while [[ $# -gt 0 && "$1" != "--" ]]; do
  case "$1" in
    --repo) [[ "${2:-}" == *=* ]] || die "--repo needs name=/path"; repos+=("$2"); shift 2 ;;
    --expect-exit) [[ "${2:-}" =~ ^[0-9]+$ ]] || die "--expect-exit needs a number"; expect="$2"; shift 2 ;;
    --max-bytes) [[ "${2:-}" =~ ^[0-9]+$ ]] || die "--max-bytes needs a number"; max="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
done
[[ "${1:-}" == "--" ]] || die "missing -- before the command"
shift
[[ $# -gt 0 ]] || die "empty command"

mkdir -p -- "$(dirname -- "$out")" || die "cannot create $(dirname -- "$out")"
: > "$out" 2>/dev/null || die "cannot write $out"

# private temp dir (0700): the raw, unmasked output only lives here
tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/prv-capture.XXXXXX")" || die "mktemp failed"
chmod 700 "$tmpdir" 2>/dev/null
tmp="$tmpdir/out"
child=""
cleanup() { [[ -n "$child" ]] && kill -- "$child" 2>/dev/null; rm -rf -- "$tmpdir"; }
trap cleanup EXIT
trap 'exit 130' INT TERM
# sweep leftovers of killed captures
find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'prv-capture.*' -type d -mtime +1 -exec rm -rf -- {} + 2>/dev/null

{
  echo "# evidence  time=$(date -Iseconds)  cwd=$PWD"
  for r in ${repos[@]+"${repos[@]}"}; do
    name="${r%%=*}"; path="${r#*=}"
    sha="$(git -C "$path" rev-parse --short HEAD 2>/dev/null || echo '?')"
    dirty=0; [[ -n "$(git -C "$path" status --porcelain 2>/dev/null)" ]] && dirty=1
    echo "# repo $name sha=$sha dirty=$dirty"
  done
  printf '# cmd:'; printf ' %q' "$@"; echo
} > "$tmp" || die "cannot write temp file"

"$@" < /dev/null >> "$tmp" 2>&1 &
child=$!
wait "$child"
rc=$?
child=""

size=$(wc -c < "$tmp")
if (( size > max )); then
  head -c "$max" "$tmp" > "$tmp.cut" && mv -- "$tmp.cut" "$tmp"
  printf '\n# TRUNCATED: output was %s bytes, kept the first %s (--max-bytes)\n' "$size" "$max" >> "$tmp"
fi
[[ -n "$(tail -c1 "$tmp")" ]] && echo >> "$tmp"
echo "exit=$rc" >> "$tmp"

# literal values of secret-named env vars -> ${NAME}
secret_env=()
secret_pat='pass|password|passwd|pwd|token|secret|key|cred|credential|auth|cookie|session|jwt|pat'
while IFS='=' read -r k v; do
  case "$k" in PWD|OLDPWD|HOME|USER|LOGNAME|SHELL|TERM|LANG|LC_ALL|HOSTNAME|TMPDIR) continue ;; esac
  lk="$(printf '%s' "$k" | tr '[:upper:]' '[:lower:]')"
  if [[ "$lk" =~ $secret_pat ]]; then
    [[ ${#v} -ge 6 ]] && secret_env+=("$k")
  fi
done < <(env)
python3 - "$tmp" ${secret_env[@]+"${secret_env[@]}"} > "$out" <<'PY' || { echo "capture.sh: masking failed, evidence not written" >&2; : > "$out"; exit 2; }
import os, re, sys

path, names = sys.argv[1], sys.argv[2:]

text = open(path, encoding="utf-8", errors="replace").read()

# 1. values of secret-named environment variables -> ${NAME}
for n in sorted(names, key=lambda n: -len(os.environ.get(n, ""))):
    v = os.environ.get(n, "")
    if v:
        text = text.replace(v, "${%s}" % n)

SECRET_WORDS = (r"pass(?:word|wd)?|pwd|token|secret|key|cred(?:ential)?|auth(?:orization)?|cookie|session|jwt|pat|api[-_]?key")

def looks_like_secret(v):
    """A credential-ish value: long enough and mixed with digits or punctuation.
    Plain English words ('tokenization', 'failed') are left alone."""
    if len(v) < 8:
        return False
    return bool(re.search(r"\d", v) or re.search(r"[^\w\s]", v))

VAR_REF = re.compile(r"^\$?\{?[A-Za-z_][A-Za-z0-9_]*\}?$")

def mask_bearer(m):
    """'Bearer <value>': the value is a credential whatever it looks like. A variable name
    ($TOKEN / ${TOKEN}) is kept, because the command line is recorded as typed.
    The separator may be a quoted space (\\ ) — that is how the recorded command line looks."""
    val = m.group(3)
    return m.group(1) + m.group(2) + (val if VAR_REF.match(val) else "***")

# 2. header lines: "Authorization: ...", "X-Api-Key: ...", "X-Custom-Auth: ..."
text = re.sub(
    r"(?im)^((?:[<>]\s*)?(?:[A-Za-z0-9_-]*\b(?:" + SECRET_WORDS + r")\b[A-Za-z0-9_-]*\s*:\s*).+)$",
    r"\1***", text)

# 3. name=value / name: value pairs whose name is secret-ish
text = re.sub(
    r"(?i)\b((?:" + SECRET_WORDS + r")[A-Za-z0-9_-]*\s*[:=]\s*)[\"']?([^\s\"',;]+)[\"']?",
    lambda m: m.group(1) + ('***' if looks_like_secret(m.group(2)) else m.group(2)), text)

# 4. keyword + credential shapes
rules = [
    (r"(?i)\b(bearer|basic)((?:\\?\s)+)([^\s\"',;\\]{8,})", mask_bearer, 0),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", "<private-key>", re.S),
    (r"(?i)\b(bearer|basic|token|apikey|api_key|secret|password|passwd|session)\s*[:=]\s*[\"']?([^\s\"',;]{8,})[\"']?",
     lambda m: m.group(1) + "=" + ("***" if looks_like_secret(m.group(2)) else m.group(2)), 0),
    (r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}", "<jwt>", 0),
    (r"glpat-[A-Za-z0-9_-]{16,}", "glpat-***", 0),
    (r"\b(AKIA|ASIA)[0-9A-Z]{16}\b", r"\1***", 0),
    (r"(://[^/\s:@]+:)[^@\s/]+@", r"\1***@", 0),
    (r"(?i)(\"(?:password|passwd|pwd|secret|token|access_?token|refresh_?token|api_?key|client_?secret)\"\s*:\s*)\"(?:[^\"\\]|\\.)*\"", r'\1"***"', 0),
    (r"(?i)\b((?:password|passwd|pwd|secret|token|access_?token|api_?key|client_?secret|[A-Z_]*(?:SECRET|TOKEN|PASSWORD)[A-Z_]*)\s*=\s*)('[^']*'|\"[^\"]*\"|[^\s&;,'\"]+)", r"\1***", 0),
    (r"(\s--password(?:=|\s+))\S+", r"\1***", 0),
]
for pat, rep, flags in rules:
    text = re.sub(pat, rep, text, flags=flags)

cmd_rules = [  # only on the recorded command line, where flags are unambiguous
    (r"(?<=\s)(-p)([^\s-]\S*)", r"\1***"),             # mysql -p<pw>
    (r"(\s(?:-u|--user)\s+)([^:\s]+:)(\S+)", r"\1\2***"),   # curl -u user:pass
    (r"(?<=\s)(-u|--user)([^:\s]+:)(\S+)", r"\1\2***"),     # curl -uuser:pass
]
def mask_cmd(m):
    line = m.group(0)
    for i, (pat, rep) in enumerate(cmd_rules):
        if i == 0 and not re.search(r"\b(mysql|mariadb|mysqldump|mysqladmin)\b", line):
            continue
        line = re.sub(pat, rep, line)
    return line
text = re.sub(r"(?m)^# cmd:.*$", mask_cmd, text)
sys.stdout.write(text)
PY

lines=$(wc -l < "$out")
if [[ "$rc" == "$expect" ]]; then
  echo "captured $out ($lines lines) exit=$rc (expected $expect)"
  exit 0
fi
echo "captured $out ($lines lines) exit=$rc (EXPECTED $expect)"
exit 1
