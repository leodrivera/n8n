#!/usr/bin/env python3

"""
Rebase a single patch branch (e.g., 'iam') in your fork
onto the latest upstream release tag of n8n, and tag the result as <tag>-iam.

Context (fork-aware):
  - 'origin' is your fork (where the custom '-iam' tag should live).
  - 'upstream' points to n8n-io/n8n (source of official tags).
  - The base tag (OLD_TAG) is inferred from upstream-like tags only
    (excluding your custom '*-iam' tags).

Workflow:
  1) Ensure the 'upstream' remote exists and fetch its tags.
  2) Determine NEW_TAG:
       - If --to-tag is provided, use it; otherwise query GitHub latest release.
  3) Determine OLD_TAG using ONLY upstream-like tags:
       git describe --tags --abbrev=0 --exclude '*-iam' <patch_branch>
     (or override via --from-tag if needed).
  4) Rebase:
       git rebase --rebase-merges --onto refs/tags/<NEW_TAG> refs/tags/<OLD_TAG> <PATCH_BRANCH>
  5) Create/update an annotated tag <NEW_TAG>-iam (e.g., n8n@1.108.3-iam)
     on your current HEAD (in your fork). No pushes are performed.

Requirements:
  - Run inside a git repository.
  - Clean working tree (no unstaged/unstashed changes).
  - Optional: set GITHUB_TOKEN or GH_TOKEN to avoid GitHub API rate limits.
  - GPG signing will be used if available and configured.
"""

import argparse
import json
import os
import subprocess
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ------------------------- Configuration -------------------------

UPSTREAM_REPO = "n8n-io/n8n"
UPSTREAM_URL = f"https://github.com/{UPSTREAM_REPO}.git"
PATCH_BRANCH_DEFAULT = "iam"
RELEASE_TAG_SUFFIX = "iam"  # results in <upstream-tag>-iam

# ------------------------- Utilities -------------------------

def run(cmd: str, capture: bool = True, check: bool = True, timeout: int = 120):
    """Run a shell command and return its stdout as text."""
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError(f"Timeout executing: {cmd}")
    rc = proc.returncode
    text = out.decode("utf-8", errors="replace") if out else ""
    if check and rc != 0:
        raise RuntimeError(f"Command failed ({rc}): {cmd}\n{text}")
    return text if capture else None

def is_gpg_signing_available() -> bool:
    """Check if GPG signing is available and configured."""
    try:
        # Check if GPG is available
        run("gpg --version", capture=False)
        
        # Check if git is configured for GPG signing
        signing_key = run("git config --get user.signingkey", capture=True, check=False)
        if signing_key and signing_key.strip():
            return True
            
        # Check if GPG signing is enabled globally
        gpg_sign = run("git config --get commit.gpgsign", capture=True, check=False)
        if gpg_sign and gpg_sign.strip().lower() in ('true', '1', 'yes'):
            return True
            
        return False
    except RuntimeError:
        return False

def ensure_repo():
    """Ensure we're inside a git repo."""
    try:
        run("git rev-parse --is-inside-work-tree", capture=False)
    except RuntimeError:
        sys.exit("ERROR: Run this script inside a git repository.")

def ensure_clean():
    """Ensure working tree and index are clean."""
    wt = subprocess.run(["git", "diff", "--quiet"]).returncode
    idx = subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode
    untracked = run("git ls-files --others --exclude-standard").strip()
    if wt != 0 or idx != 0 or untracked:
        sys.exit("ERROR: Working tree/index has changes or untracked files. Commit/stash first.")

def ensure_upstream_remote():
    """Ensure the 'upstream' remote exists and fetch tags."""
    remotes = run("git remote -v")
    if "upstream" not in remotes:
        run(f"git remote add upstream {UPSTREAM_URL}", capture=False)
    run("git fetch upstream --tags", capture=False)

def verify_tag_local(tag: str):
    """Ensure a given tag exists locally; fetch it from upstream if needed."""
    try:
        run(f"git rev-parse -q --verify refs/tags/{tag}", capture=False)
    except RuntimeError:
        # fetch the specific tag from upstream into local tag namespace
        run(f"git fetch upstream {tag}:refs/tags/{tag}", capture=False)

def branch_exists(branch: str) -> bool:
    try:
        run(f"git rev-parse --verify {branch}", capture=False)
        return True
    except RuntimeError:
        return False

def get_latest_tag():
    """Query GitHub's latest release tag for UPSTREAM_REPO."""
    api = f"https://api.github.com/repos/{UPSTREAM_REPO}/releases/latest"
    headers = {"User-Agent": "release-rebase-script"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = Request(api, headers=headers)
        with urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        tag = data.get("tag_name")
        if not tag:
            raise RuntimeError("GitHub API did not return 'tag_name'.")
        return tag
    except (HTTPError, URLError, TimeoutError) as e:
        raise RuntimeError(f"Failed to fetch latest release: {e}")

def infer_base_tag_with_describe(branch: str) -> str | None:
    """
    Infer the previous base tag ONLY among upstream-like tags, excluding
    custom '*-iam' tags that exist only in your fork:
      git describe --tags --abbrev=0 --exclude '*-iam' <branch>
    """
    try:
        desc = run(f"git describe --tags --abbrev=0 --exclude '*-iam' {branch}").strip()
        return desc or None
    except RuntimeError:
        return None

def create_or_update_release_tag(new_tag: str, suffix: str = RELEASE_TAG_SUFFIX) -> str:
    """Create or update an annotated tag <new_tag>-<suffix> on current HEAD."""
    t = f"{new_tag}-{suffix}"
    
    # Check if GPG signing is available
    use_gpg = is_gpg_signing_available()
    
    if use_gpg:
        print("[gpg] GPG signing available - will sign the tag")
        # Force-move the tag if it already exists, with GPG signing
        try:
            run(f"git tag -fs {t} -m 'Release {t}'", capture=False)
        except RuntimeError:
            run(f"git tag -s {t} -m 'Release {t}'", capture=False)
    else:
        print("[gpg] GPG signing not available - creating unsigned tag")
        # Force-move the tag if it already exists, without GPG signing
        try:
            run(f"git tag -fa {t} -m 'Release {t}'", capture=False)
        except RuntimeError:
            run(f"git tag -a {t} -m 'Release {t}'", capture=False)
    
    return t

def do_rebase(patch_branch: str, old_tag: str, new_tag: str):
    """Perform the rebase of patch_branch from old_tag onto new_tag."""
    print(f"[rebase] {patch_branch}: {old_tag} -> {new_tag}")
    verify_tag_local(old_tag)
    verify_tag_local(new_tag)
    run(f"git checkout {patch_branch}", capture=False)
    
    # Check if GPG signing is available for commits during rebase
    use_gpg = is_gpg_signing_available()
    if use_gpg:
        print("[gpg] GPG signing available - commits during rebase will be signed")
        # Temporarily enable GPG signing for commits if not already enabled
        current_gpg_sign = run("git config --get commit.gpgsign", capture=True, check=False)
        if not current_gpg_sign or current_gpg_sign.strip().lower() not in ('true', '1', 'yes'):
            run("git config commit.gpgsign true", capture=False)
            print("[gpg] Temporarily enabled commit.gpgsign for this rebase")
    
    run(
        f"git rebase --rebase-merges --onto refs/tags/{new_tag} refs/tags/{old_tag} {patch_branch}",
        capture=False
    )
    
    head = run("git rev-parse --short HEAD").strip()
    print(f"[ok] HEAD at {head} on top of {new_tag}")

# --------------------------- CLI ----------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Rebase a patch branch in your fork onto the latest n8n upstream release tag."
    )
    ap.add_argument("--patch-branch", default=PATCH_BRANCH_DEFAULT,
                    help="Patch branch name (default: iam)")
    ap.add_argument("--to-tag",
                    help="Target upstream tag (e.g., n8n@1.108.3). If not set, the latest release is used.")
    ap.add_argument("--from-tag",
                    help="Force the previous base tag (e.g., n8n@1.107.4) instead of inferring with git describe.")
    args = ap.parse_args()

    ensure_repo()
    ensure_clean()
    ensure_upstream_remote()

    # Check GPG signing availability early
    gpg_available = is_gpg_signing_available()
    if gpg_available:
        print("[gpg] GPG signing is available and will be used for commits and tags")
    else:
        print("[gpg] GPG signing not available - commits and tags will be unsigned")

    # Ensure the patch branch exists (you said you'll rename it to 'iam')
    if not branch_exists(args.patch_branch):
        sys.exit(f"ERROR: Branch '{args.patch_branch}' does not exist. Create/rename it first.")

    # Determine NEW_TAG
    new_tag = args.to_tag or get_latest_tag()
    verify_tag_local(new_tag)

    # Determine OLD_TAG (prefer explicit --from-tag; otherwise, infer via describe excluding '*-iam')
    old_tag = args.from_tag or infer_base_tag_with_describe(args.patch_branch)
    if not old_tag:
        sys.exit(
            "ERROR: Could not infer the previous base tag with "
            f"git describe --tags --abbrev=0 --exclude '*-iam' {args.patch_branch}\n"
            "Hint: pass --from-tag n8n@X.Y.Z explicitly."
        )

    # Rebase and tag
    do_rebase(args.patch_branch, old_tag, new_tag)
    custom_tag = create_or_update_release_tag(new_tag, suffix=RELEASE_TAG_SUFFIX)
    print(f"[tag] Created/updated: {custom_tag}")

    print("\nNext steps (in your fork):\n"
          f"  git push -u origin {args.patch_branch}\n"
          f"  git push -f origin {custom_tag}\n")

if __name__ == "__main__":
    main()
