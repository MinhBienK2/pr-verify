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
# -p<pw>, glpat-, AKIA, JWT, PEM). The values of environment variables whose name contains
# PASS, TOKEN, SECRET or KEY are also replaced with their name wherever they appear.
# The command's stdin is /dev/null. The raw output is kept in $TMPDIR and removed on any exit.
set -uo pipefail

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; }
die() { echo "capture.sh: $*" >&2; exit 2; }

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
tmp="$(mktemp)" || die "mktemp failed"
child=""
cleanup() { [[ -n "$child" ]] && kill -- "$child" 2>/dev/null; rm -f -- "$tmp"; }
trap cleanup EXIT
trap 'exit 130' INT TERM

{
  echo "# evidence  time=$(date -Iseconds)  cwd=$PWD"
  for r in "${repos[@]}"; do
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
if (( size > max + 4096 )); then
  head -c "$max" "$tmp" > "$tmp.cut" && mv -- "$tmp.cut" "$tmp"
  printf '\n# TRUNCATED: output was %s bytes, kept the first %s (--max-bytes)\n' "$size" "$max" >> "$tmp"
fi
[[ -n "$(tail -c1 "$tmp")" ]] && echo >> "$tmp"
echo "exit=$rc" >> "$tmp"

# literal values of secret-named env vars -> ${NAME}
secret_env=()
while IFS='=' read -r k v; do
  [[ "$k" =~ (PASS|TOKEN|SECRET|KEY) && ${#v} -ge 6 ]] && secret_env+=("$k")
done < <(env)
python3 - "$tmp" "${secret_env[@]}" > "$out" <<'PY' || { echo "capture.sh: masking failed, evidence not written" >&2; : > "$out"; exit 2; }
import os, re, sys
path, names = sys.argv[1], sys.argv[2:]
text = open(path, encoding="utf-8", errors="replace").read()
for n in sorted(names, key=lambda n: -len(os.environ.get(n, ""))):
    v = os.environ.get(n, "")
    if v:
        text = text.replace(v, "${%s}" % n)
rules = [
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", "<private-key>", re.S),
    (r"(?im)^((?:[<>]\s*)?(?:authorization|proxy-authorization|cookie|set-cookie|private-token|x-api-key|x-auth-token)\s*:\s*).+$", r"\1***", 0),
    (r"(?i)((?:authorization|cookie|private-token|x-api-key)\s*:(?:\\?\s)*)(?:(?:bearer|basic|token)(?:\\?\s)+)?(?:[^\s'\"\\]|\\.)+", r"\1***", 0),
    (r"(?i)\b(bearer|basic|token)(\s+)[A-Za-z0-9._~+/=-]{8,}", r"\1\2***", 0),
    (r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}", "<jwt>", 0),
    (r"glpat-[A-Za-z0-9_-]{16,}", "glpat-***", 0),
    (r"\b(AKIA|ASIA)[0-9A-Z]{16}\b", r"\1***", 0),
    (r"(://[^/\s:@]+:)[^@\s/]+@", r"\1***@", 0),
    (r"(?i)(\"(?:password|passwd|pwd|secret|token|access_?token|refresh_?token|api_?key|client_?secret)\"\s*:\s*)\"(?:[^\"\\]|\\.)*\"", r'\1"***"', 0),
    (r"(?i)\b((?:password|passwd|pwd|secret|token|access_?token|api_?key|client_?secret|[A-Z_]*(?:SECRET|TOKEN|PASSWORD)[A-Z_]*)\s*=\s*)('[^']*'|\"[^\"]*\"|[^\s&;,'\"]+)", r"\1***", 0),
    (r"(\s--password(?:=|\s+))\S+", r"\1***", 0),
]
cmd_rules = [  # only on the recorded command line, where flags are unambiguous
    (r"(?<=\s)(-p)([^\s-]\S*)", r"\1***"),            # mysql -p<pw> (only when the command is a MySQL client)
    (r"(\s(?:-u|--user)\s+[^:\s]+:)\S+", r"\1***"),  # curl -u user:pass
]
for pat, rep, flags in rules:
    text = re.sub(pat, rep, text, flags=flags)
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
