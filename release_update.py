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

def do_rebase(patch_branch: str, old_tag: str, new_tag: str, strategy: str = "theirs"):
    """Perform the rebase of patch_branch from old_tag onto new_tag."""
    print(f"[rebase] {patch_branch}: {old_tag} -> {new_tag}")
    print(f"[strategy] Conflict resolution: {strategy}")
    verify_tag_local(old_tag)
    verify_tag_local(new_tag)
    run(f"git checkout {patch_branch}", capture=False)
    
    # Store the original HEAD for potential undo
    original_head = run("git rev-parse HEAD").strip()
    print(f"[rebase] Original HEAD: {original_head}")
    
    # Check if GPG signing is available for commits during rebase
    use_gpg = is_gpg_signing_available()
    if use_gpg:
        print("[gpg] GPG signing available - commits during rebase will be signed")
    
    # Build rebase command based on strategy
    if strategy == "manual":
        rebase_cmd = f"git rebase --rebase-merges --onto refs/tags/{new_tag} refs/tags/{old_tag} {patch_branch}"
    else:
        rebase_cmd = f"git rebase --rebase-merges -X {strategy} --onto refs/tags/{new_tag} refs/tags/{old_tag} {patch_branch}"
    
    run(rebase_cmd, capture=False)
    
    head = run("git rev-parse --short HEAD").strip()
    print(f"[ok] HEAD at {head} on top of {new_tag}")
    
    return original_head

def undo_changes(patch_branch: str, old_tag: str, new_tag: str, custom_tag: str):
    """Undo the changes made by the script: abort rebase, delete custom tag, restore branch state."""
    print("[undo] Starting undo process...")
    
    try:
        # 1. Abort any ongoing rebase
        try:
            run("git rebase --abort", capture=False)
            print("[undo] Aborted ongoing rebase")
        except RuntimeError:
            # Rebase might not be in progress, that's okay
            pass
        
        # 2. Delete the custom tag if it exists
        try:
            run(f"git tag -d {custom_tag}", capture=False)
            print(f"[undo] Deleted tag: {custom_tag}")
        except RuntimeError:
            # Tag might not exist, that's okay
            pass
        
        # 3. Reset the patch branch to its original state (before rebase)
        try:
            # Try to find the original HEAD from reflog
            # Look for the last checkout to this branch before any rebase operations
            reflog_output = run("git reflog --format='%H %gs' -n 20", capture=True, check=False)
            found_original_head = None
            
            # Look for the last checkout to the patch branch
            for line in reflog_output.split('\n'):
                if f"checkout: moving to {patch_branch}" in line:
                    found_original_head = line.split()[0]
                    break
            
            if found_original_head:
                run(f"git reset --hard {found_original_head}", capture=False)
                print(f"[undo] Reset {patch_branch} to original state ({found_original_head[:8]})")
            else:
                # Fallback: try to use ORIG_HEAD if it exists
                try:
                    orig_head = run("git rev-parse ORIG_HEAD", capture=True, check=False).strip()
                    if orig_head:
                        run(f"git reset --hard {orig_head}", capture=False)
                        print(f"[undo] Reset {patch_branch} to ORIG_HEAD ({orig_head[:8]})")
                    else:
                        print("[undo] Could not determine original branch state")
                except RuntimeError:
                    print("[undo] Could not determine original branch state")
        except RuntimeError:
            print("[undo] Could not reset branch to original state")
        
        
        print("[undo] Undo completed successfully")
        
    except Exception as e:
        print(f"[undo] Error during undo: {e}")
        print("[undo] Manual cleanup may be required")
        raise

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
    ap.add_argument("--undo", action="store_true",
                    help="Undo the last operation performed by this script (abort rebase, delete custom tag, restore branch state).")
    ap.add_argument("--strategy", choices=["theirs", "ours", "manual"], default="theirs",
                    help="Conflict resolution strategy: 'theirs' (accept incoming changes), 'ours' (keep local changes), 'manual' (resolve manually)")
    args = ap.parse_args()

    ensure_repo()
    
    # Handle undo operation
    if args.undo:
        print("[undo] Undo mode activated")
        # For undo, we don't need a clean working tree since we're fixing conflicts
        ensure_upstream_remote()
        
        # Try to determine the tags and custom tag that were used
        # We'll make educated guesses based on recent tags and branch state
        try:
            # Get the latest tag to construct the custom tag name
            latest_tag = get_latest_tag()
            custom_tag = f"{latest_tag}-{RELEASE_TAG_SUFFIX}"
            
            # Try to infer the old tag
            old_tag = args.from_tag or infer_base_tag_with_describe(args.patch_branch)
            if not old_tag:
                old_tag = "unknown"  # We'll still try to undo what we can
            
            print("[undo] Attempting to undo operation with:")
            print(f"[undo]   Patch branch: {args.patch_branch}")
            print(f"[undo]   Custom tag: {custom_tag}")
            print(f"[undo]   Old tag: {old_tag}")
            
            undo_changes(args.patch_branch, old_tag, latest_tag, custom_tag)
            print("[undo] Undo operation completed")
            return
            
        except Exception as e:
            print(f"[undo] Error during undo: {e}")
            print("[undo] You may need to manually clean up:")
            print("  - git rebase --abort")
            print("  - git tag -d <custom-tag>")
            print("  - git reset --hard <original-commit>")
            sys.exit(1)
    
    # Normal operation - ensure clean working tree
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
    original_head = None
    try:
        original_head = do_rebase(args.patch_branch, old_tag, new_tag, args.strategy)
        custom_tag = create_or_update_release_tag(new_tag, suffix=RELEASE_TAG_SUFFIX)
        print(f"[tag] Created/updated: {custom_tag}")

        print("\nNext steps (in your fork):\n"
              f"  git push -f origin {args.patch_branch}  # Force push due to rebase\n"
              f"  git push -f origin {custom_tag}\n")
              
    except Exception as e:
        print(f"\n[error] Operation failed: {e}")
        print("\nTo undo the changes made so far, run:")
        print(f"  {sys.argv[0]} --undo --patch-branch {args.patch_branch}")
        if args.from_tag:
            print(f"  {sys.argv[0]} --undo --patch-branch {args.patch_branch} --from-tag {args.from_tag}")
        
        # If we have the original_head, we can provide a more specific undo command
        if original_head:
            print("\nOr use the stored original HEAD directly:")
            print(f"  git reset --hard {original_head}")
            print(f"  git tag -d {new_tag}-{RELEASE_TAG_SUFFIX}")
        
        sys.exit(1)

if __name__ == "__main__":
    main()
