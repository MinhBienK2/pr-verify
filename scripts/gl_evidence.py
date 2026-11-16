#!/usr/bin/env python3
"""Publish a Markdown evidence body (with local images) to a GitLab MR via glab.

  gl_evidence.py --repo <local clone of the MR's project> --mr <iid> --body report.md \
                 --expect-sha <sha the evidence was taken on> \
                 [--key <feature-slug>] [--target note|description] [--dry-run]

What it does:
  1. Resolves host + project from the clone's `origin` remote (works for self-hosted;
     `glab auth status` lists gitlab.com first, so the host is never guessed).
  2. Checks the MR's head sha starts with --expect-sha (required unless --dry-run): evidence
     taken on a commit the MR does not carry must not be published. Push first.
  3. Finds every local image in the body: ![alt](path), ![alt](<path with spaces> "title"),
     <img src="path">, and reference definitions [id]: path. Uploads each to THAT project
     (uploads belong to one project), cached by sha256 in <body>.uploads.<host>.<project-id>.json.
     Only files under the workspace's shots/ and logs/ are uploaded, and only image extensions;
     --allow-any lifts that (it is for evidence outside the workspace, use with care).
  4. Rewrites each reference to https://<host>/-/project/<id>/uploads/<secret>/<file>
     (the relative /uploads/... form renders broken on current GitLab; /<ns>/<proj>/uploads 404s).
     Any image reference still pointing at a local path afterwards is an error, dry-run included.
  5. --target note (default): updates YOUR note carrying <!-- pr-verify:<key> -->, or creates one.
     --target description: replaces the block between <!-- pr-verify:<key>:start --> and
     <!-- pr-verify:<key>:end --> (exactly one of each, start before end), or appends it; aborts
     if the description changed while uploading.
  6. Reads the result back, checks every image URL is absolute and in this project, prints the URL.

--dry-run performs only reads and prints the final body. Exit 1 on any failure.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse

# ![alt](dest "title") — alt may contain balanced [], dest may be <...> or contain balanced ()
MD_IMG = re.compile(r"""(!\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*)(<[^>\n]+>|(?:[^\s()]|\([^\s()]*\))+)((?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\s*\))""")
HTML_IMG = re.compile(r"""(<img\b[^>]*?\bsrc\s*=\s*)("[^"]+"|'[^']+'|[^\s>]+)""", re.I)
REF_DEF = re.compile(r"""(?m)^( {0,3}\[[^\]]+\]:\s*)(<[^>\n]+>|\S+)""")
# a looser scan: any markdown image, used to catch paths the strict patterns above do not match
LOOSE_IMG = re.compile(r"""!\[[^\]]*\]\(([^)\n]+)\)""")
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".mp4", ".webm")
ALLOWED_DIRS = ("shots/", "logs/")


def sh(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {r.stderr.strip()[:400]} {r.stdout.strip()[:200]}")
    return r.stdout


def remote(repo):
    url = sh(["git", "remote", "get-url", "origin"], cwd=repo).strip()
    if "://" in url:
        u = urllib.parse.urlsplit(url)
        host, path = u.hostname, u.path
    else:  # scp-like: [user@]host:path
        m = re.match(r"^(?:[^@/]+@)?([^:/]+):(.+)$", url)
        if not m:
            raise RuntimeError(f"cannot parse origin remote: {url}")
        host, path = m.group(1), m.group(2)
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not host or "/" not in path:
        raise RuntimeError(f"cannot parse origin remote: {url}")
    return host, path


class GL:
    def __init__(self, host, path):
        self.host, self.path = host, path
        self.enc = urllib.parse.quote(path, safe="")

    def api(self, method, endpoint, body=None, form=None):
        cmd = ["glab", "api", "--hostname", self.host, "--method", method, endpoint]
        tmp = None
        if form:
            cmd += ["--form", form]
        if body is not None:
            tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
            json.dump(body, tmp, ensure_ascii=False)
            tmp.close()
            cmd += ["--header", "Content-Type: application/json", "--input", tmp.name]
        try:
            out = sh(cmd)
        finally:
            if tmp:
                os.unlink(tmp.name)
        out = out.strip()
        return json.loads(out) if out else None

    def all_pages(self, endpoint):
        items, page = [], 1
        while True:
            sep = "&" if "?" in endpoint else "?"
            chunk = self.api("GET", f"{endpoint}{sep}per_page=100&page={page}") or []
            items += chunk
            if len(chunk) < 100:
                return items
            page += 1


def is_remote(ref):
    return re.match(r"^(https?:)?//", ref) is not None or ref.startswith(("data:", "#", "mailto:"))


def clean(ref):
    ref = ref.strip()
    if ref[:1] in "<\"'" and ref[-1:] in ">\"'":
        ref = ref[1:-1]
    return urllib.parse.unquote(ref)


def local_refs(text):
    """Every image-like reference in text that does not point at a URL."""
    out = []
    for rx, grp in ((MD_IMG, 2), (HTML_IMG, 2)):
        out += [clean(m.group(grp)) for m in rx.finditer(text)]
    out += [clean(m.group(2)) for m in REF_DEF.finditer(text) if clean(m.group(2)).lower().endswith(IMG_EXT)]
    return [r for r in out if not is_remote(r)]


def unspaced_paths(text):
    """Local image paths that contain a space and are not wrapped in <...>. The strict patterns
    above do not match them, so they would be published as broken relative links. Fail loudly
    instead of shipping a broken picture."""
    out = []
    for m in LOOSE_IMG.finditer(text):
        dest = m.group(1).strip()
        if dest.startswith("<") and dest.endswith(">"):
            continue
        dest = re.sub(r"\s+[\"'(].*$", "", dest).strip()
        if " " in dest and not is_remote(dest):
            out.append(dest)
    return out


def resolve_upload(ref, base, ws, allow_any):
    """Where an image reference points, and whether it may be uploaded at all.
    A relative path is resolved against the workspace root first, then against the directory of
    the body file, so a body may use either form."""
    if os.path.isabs(ref):
        cands = [ref]
    else:
        cands = [os.path.join(ws, ref), os.path.join(base, ref)]
    f = None
    for c in cands:
        rc = os.path.realpath(c)
        if os.path.isfile(rc):
            f = rc
            break
    if f is None:
        raise RuntimeError(f"image not found: {ref} (tried {', '.join(cands)})")
    if allow_any:
        return f
    ws_real = os.path.realpath(ws)
    if os.path.commonpath([f, ws_real]) != ws_real:
        raise RuntimeError(f"refusing to upload {ref}: it is outside the workspace {ws}; "
                           f"only evidence under {', '.join(ALLOWED_DIRS)} may be published")
    rel = os.path.relpath(f, ws_real).replace(os.sep, "/")
    if not rel.startswith(ALLOWED_DIRS):
        raise RuntimeError(f"refusing to upload {ref}: only evidence under {', '.join(ALLOWED_DIRS)} "
                           f"may be published (use --allow-any to override)")
    ext = os.path.splitext(f)[1].lower()
    if ext not in IMG_EXT:
        raise RuntimeError(f"refusing to upload {ref}: {ext or 'no extension'} is not an image "
                           f"({', '.join(IMG_EXT)})")
    return f


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="local clone of the MR's project")
    ap.add_argument("--mr", required=True, type=int)
    ap.add_argument("--body", required=True, help="Markdown file; image paths resolve relative to it")
    ap.add_argument("--expect-sha", help="sha the evidence was taken on; MR head must start with it (required to publish)")
    ap.add_argument("--key", default="pr-verify", help="marker key; one note/description block per key (use the feature slug)")
    ap.add_argument("--target", choices=["note", "description"], default="note")
    ap.add_argument("--workspace", help="workspace holding shots/ and logs/ (default: the parent of the body's directory)")
    ap.add_argument("--allow-any", action="store_true", help="upload any local file, not only evidence under shots/ and logs/")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.dry_run and not a.expect_sha:
        raise RuntimeError("--expect-sha is required to publish (the head sha of the last verification run for this repo)")

    host, path = remote(a.repo)
    gl = GL(host, path)
    proj = gl.api("GET", f"projects/{gl.enc}")
    pid = proj["id"]
    mr = gl.api("GET", f"projects/{pid}/merge_requests/{a.mr}")
    head = mr.get("sha") or ""
    print(f"project {path} (id {pid}) on {host}; MR !{a.mr} [{mr['state']}] head {head[:10]} {mr['web_url']}")
    if a.expect_sha and not head.startswith(a.expect_sha.lower()):
        msg = f"MR head is {head[:10]}, evidence was taken on {a.expect_sha}: push the verified commits (or re-run on the MR head) first"
        if not a.dry_run:
            raise RuntimeError(msg)
        print(f"[dry-run] WARNING: {msg}")

    body_path = os.path.abspath(a.body)
    base = os.path.dirname(body_path)
    body = open(body_path, encoding="utf-8").read()
    ws = os.path.abspath(a.workspace) if a.workspace else (
        os.path.dirname(base) if os.path.basename(base) == "report" else base)
    cache_path = f"{body_path}.uploads.{host}.{pid}.json"
    prefix = f"https://{host}/-/project/{pid}/uploads/"
    try:
        cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
        cache = {k: v for k, v in cache.items() if isinstance(v, str) and v.startswith(prefix)}
    except (OSError, ValueError):
        cache = {}

    uploaded = set()

    def upload(ref):
        f = resolve_upload(ref, base, ws, a.allow_any)
        digest = hashlib.sha256(open(f, "rb").read()).hexdigest()
        uploaded.add(digest)
        if digest not in cache:
            if a.dry_run:
                return f"{prefix}<dry-run>/{urllib.parse.quote(os.path.basename(f))}"
            up = gl.api("POST", f"projects/{pid}/uploads", form=f"file=@{f}")
            fp = up.get("full_path") or ""
            if f"/-/project/{pid}/uploads/" not in fp:  # older GitLab: build it from url
                mm = re.search(r"uploads/([0-9a-f]{32})/(.+)$", up.get("url", ""))
                if not mm:
                    raise RuntimeError(f"unexpected upload response: {up}")
                fp = f"/-/project/{pid}/uploads/{mm.group(1)}/{mm.group(2)}"
            cache[digest] = f"https://{host}{fp}"
            with open(cache_path, "w") as fh:
                json.dump(cache, fh, indent=1)
            print(f"  uploaded {ref}")
        return cache[digest]

    def swap(m, quote_html=False):
        ref = clean(m.group(2))
        if is_remote(ref):
            return m.group(0)
        url = upload(ref)
        if quote_html:
            url = '"' + url + '"'
        tail = m.group(3) if m.re is MD_IMG else ""
        return m.group(1) + url + tail

    body = MD_IMG.sub(swap, body)
    body = HTML_IMG.sub(lambda m: swap(m, quote_html=True), body)
    body = REF_DEF.sub(lambda m: swap(m) if clean(m.group(2)).lower().endswith(IMG_EXT) else m.group(0), body)
    leftover = local_refs(body)
    if leftover:
        raise RuntimeError("image references still local after rewrite (unsupported syntax?): " + ", ".join(leftover))
    spaced = unspaced_paths(body)
    if spaced:
        raise RuntimeError("image path(s) with spaces must be wrapped in <...>: " + ", ".join(spaced))
    n_img = len(uploaded)

    marker = f"<!-- pr-verify:{a.key} -->"
    start, end = f"<!-- pr-verify:{a.key}:start -->", f"<!-- pr-verify:{a.key}:end -->"
    if a.target == "note":
        final = f"{marker}\n{body}"
        me = gl.api("GET", "user")["id"]
        notes = gl.all_pages(f"projects/{pid}/merge_requests/{a.mr}/notes")
        mine = [n for n in notes if marker in (n.get("body") or "") and not n.get("system") and n["author"]["id"] == me]
        if len(mine) > 1:
            print(f"WARNING: {len(mine)} of your notes carry {marker}; updating the newest ({mine[0]['id']}), delete the others by hand")
        action = f"update note {mine[0]['id']}" if mine else "create note"
        if a.dry_run:
            print(f"[dry-run] would {action} with {n_img} image(s)\n----\n{final}\n----")
            return
        if mine:
            # someone else may have edited the note while we were uploading
            now = gl.api("GET", f"projects/{pid}/merge_requests/{a.mr}/notes/{mine[0]['id']}")["body"]
            if now != (mine[0].get("body") or ""):
                raise RuntimeError(f"note {mine[0]['id']} changed while preparing the update; re-run")
            res = gl.api("PUT", f"projects/{pid}/merge_requests/{a.mr}/notes/{mine[0]['id']}", body={"body": final})
        else:
            res = gl.api("POST", f"projects/{pid}/merge_requests/{a.mr}/notes", body={"body": final})
        stored = gl.api("GET", f"projects/{pid}/merge_requests/{a.mr}/notes/{res['id']}")["body"]
        where = f"{mr['web_url']}#note_{res['id']}"
    else:
        desc = mr.get("description") or ""
        block = f"{start}\n{body}\n{end}"
        ns, ne = desc.count(start), desc.count(end)
        if ns == 0 and ne == 0:
            final = (desc.rstrip() + "\n\n" if desc.strip() else "") + block
        elif ns == 1 and ne == 1 and desc.index(start) < desc.index(end):
            final = desc[:desc.index(start)] + block + desc[desc.index(end) + len(end):]
        else:
            raise RuntimeError(f"description has {ns} start and {ne} end markers for key {a.key!r} (or end before start): fix it by hand, refusing to guess")
        if a.dry_run:
            print(f"[dry-run] would update description with {n_img} image(s)\n----\n{final}\n----")
            return
        now = gl.api("GET", f"projects/{pid}/merge_requests/{a.mr}").get("description") or ""
        if now != desc:
            raise RuntimeError("MR description changed while preparing the update; re-run")
        gl.api("PUT", f"projects/{pid}/merge_requests/{a.mr}", body={"description": final})
        stored = gl.api("GET", f"projects/{pid}/merge_requests/{a.mr}")["description"]
        where = mr["web_url"]

    urls = [clean(m.group(2)) for m in MD_IMG.finditer(stored)] + [clean(m.group(2)) for m in HTML_IMG.finditer(stored)]
    urls += [clean(m.group(2)) for m in REF_DEF.finditer(stored) if "/uploads/" in clean(m.group(2))]
    bad = [u for u in urls if "/uploads/" in u and not u.startswith(prefix)] + local_refs(stored)
    if bad:
        print("image URLs that will render broken:", *bad, sep="\n  ")
        sys.exit(1)
    print(f"published {a.target} with {n_img} image(s): {where}")
    print("open it in a logged-in browser and confirm every image renders before reporting done")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(f"error: {e}")
