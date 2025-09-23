#!/usr/bin/env python3

"""
Create a release branch from an upstream n8n tag and cherry-pick custom commits.

New strategy (history-preserving):
  - Create a new branch 'release/<version>-iam' based on upstream tag (e.g., 'n8n@1.108.3' → version '1.108.3').
  - Cherry-pick a curated list of commits containing our customizations.
  - Create a custom '<to-tag>-iam' tag on current HEAD (used by GHCR workflow).
  - Do NOT include this script in the release branch.

Context (fork-aware):
  - 'origin' is your fork.
  - 'upstream' points to n8n-io/n8n (source of official tags).

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
RELEASE_BRANCH_PREFIX = "release/"
RELEASE_TAG_SUFFIX = "iam"

# Commits to cherry-pick on top of the upstream release tag.
# Adjust this list as needed to include your customization commits.
CHERRY_PICK_COMMITS: list[str] = [
    "39d39d2880",
    "92ffba5efb",
]

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

def extract_version_from_tag(tag: str) -> str:
    """Return the version number from a tag like 'n8n@1.108.3' → '1.108.3'."""
    return tag.split("@", 1)[1] if "@" in tag else tag

def create_or_update_release_tag(new_tag: str, suffix: str = RELEASE_TAG_SUFFIX) -> str:
    """Create an annotated tag <new_tag>-<suffix> on current HEAD. Fails if tag exists."""
    t = f"{new_tag}-{suffix}"
    # Fail if tag already exists locally
    existing = run(f"git rev-parse -q --verify refs/tags/{t}", capture=True, check=False)
    if existing and existing.strip():
        raise RuntimeError(f"Tag already exists: {t}")
    use_gpg = is_gpg_signing_available()
    if use_gpg:
        print("[gpg] GPG signing available - will sign the tag")
        run(f"git tag -s {t} -m 'Release {t}'", capture=False)
    else:
        print("[gpg] GPG signing not available - creating unsigned tag")
        run(f"git tag -a {t} -m 'Release {t}'", capture=False)
    return t

def create_or_reset_release_branch(new_tag: str) -> str:
    """Create or reset 'release/<version>-iam' branch to point at the given upstream tag."""
    version = extract_version_from_tag(new_tag)
    branch_name = f"{RELEASE_BRANCH_PREFIX}{version}-{RELEASE_TAG_SUFFIX}"
    print(f"[branch] Creating/resetting branch: {branch_name} at {new_tag}")
    # Create or reset the branch to the tag (force-move if it already exists)
    run(f"git checkout -B {branch_name} refs/tags/{new_tag}", capture=False)
    return branch_name

def cherry_pick_commits(commits: list[str], strategy: str = "theirs"):
    """Cherry-pick a list of commits onto the current branch using the given strategy."""
    if not commits:
        print("[cherry-pick] No commits specified, skipping.")
        return
    print(f"[strategy] Conflict resolution: {strategy}")
    use_gpg = is_gpg_signing_available()
    if use_gpg:
        print("[gpg] GPG signing available - cherry-picked commits will be signed if configured")
    for sha in commits:
        sha = sha.strip()
        if not sha:
            continue
        sign_flag = "-S" if use_gpg else ""
        if strategy == "manual":
            cmd = f"git cherry-pick {sign_flag} -x {sha}".strip()
        else:
            cmd = f"git cherry-pick {sign_flag} -x -X {strategy} {sha}".strip()
        print(f"[cherry-pick] {sha}")
        run(cmd, capture=False)

def remove_workflows_dir_from_release_branch():
    """Remove .github/workflows from the current branch and commit the deletion if present."""
    workflows_path = os.path.join(".github", "workflows")
    if not os.path.isdir(workflows_path):
        print("[workflows] No .github/workflows directory present - skipping removal")
        return
    # Check if any files in the directory are tracked
    tracked = run("git ls-files .github/workflows", capture=True, check=False).strip()
    if not tracked:
        print("[workflows] No tracked workflow files - skipping removal")
        return
    print("[workflows] Removing .github/workflows from release branch")
    run("git rm -r .github/workflows", capture=False)
    # Commit the deletion (GPG signing is used if configured via git config)
    run("git commit -m 'chore(release): remove .github/workflows in release branch'", capture=False)

# --------------------------- CLI ----------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Create a release/<version> branch from upstream tag and cherry-pick custom commits."
    )
    ap.add_argument("--to-tag",
                    help="Target upstream tag (e.g., n8n@1.108.3). If not set, the latest release is used.")
    ap.add_argument("--strategy", choices=["theirs", "ours", "manual"], default="theirs",
                    help="Conflict resolution strategy for cherry-pick")
    args = ap.parse_args()

    ensure_repo()
    ensure_clean()
    ensure_upstream_remote()

    gpg_available = is_gpg_signing_available()
    if gpg_available:
        print("[gpg] GPG signing is available and will be used for commits")
    else:
        print("[gpg] GPG signing not available - commits will be unsigned")

    new_tag = args.to_tag or get_latest_tag()
    verify_tag_local(new_tag)

    # Create/reset branch and cherry-pick commits
    branch_name = create_or_reset_release_branch(new_tag)
    try:
        # Remove workflows from the release branch to avoid permissions issues when pushing
        remove_workflows_dir_from_release_branch()
        cherry_pick_commits(CHERRY_PICK_COMMITS, args.strategy)
        head = run("git rev-parse --short HEAD").strip()
        print(f"[ok] {branch_name} at {head} on top of {new_tag}")
        custom_tag = create_or_update_release_tag(new_tag)
        print(f"[tag] Created/updated: {custom_tag}")
        print("\nNext steps (in your fork):\n"
              f"  git push -u origin {branch_name}\n"
              f"  git push origin {custom_tag}\n")
    except Exception as e:
        print(f"\n[error] Operation failed: {e}")
        print("\nYou may need to resolve conflicts and continue with:\n"
              "  git status\n"
              "  git add <resolved-files>\n"
              "  git cherry-pick --continue\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
