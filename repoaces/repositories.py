from __future__ import annotations

import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

from .shell import require_ok, run_cmd


@dataclass(frozen=True)
class RepoWorkspace:
    repo_dir: Path
    repo_url: str
    base_commit: str
    clone_source: str


class RepositoryManager:
    """Prepare clean repository workspaces for coding agents."""

    def __init__(self, workspaces_root: Path, reference_repo: Path | None = None, use_reference_repo: bool | None = None) -> None:
        self.workspaces_root = workspaces_root
        self.reference_repo = reference_repo
        if use_reference_repo is None:
            use_reference_repo = os.getenv("REPOACES_USE_REFERENCE_REPO", "0") == "1"
        self.use_reference_repo = use_reference_repo

    def prepare_clean_repo(
        self,
        *,
        run_id: str,
        repo_url: str,
        base_commit: str,
        pr_number: int | None = None,
        repo_name: str = "FastGPT",
        force: bool = False,
    ) -> RepoWorkspace:
        if not base_commit:
            raise ValueError("base_commit is required")
        repo_dir = self.workspaces_root / run_id / repo_name
        if force and repo_dir.parent.exists():
            self._remove_within_root(repo_dir.parent)
        if repo_dir.exists() and (repo_dir / ".git").exists():
            source = "existing"
        else:
            repo_dir.parent.mkdir(parents=True, exist_ok=True)
            source = self._clone(repo_url=repo_url, base_commit=base_commit, repo_dir=repo_dir)
        fetched_pr_head = self._checkout_clean_with_pr_fallback(
            repo_dir=repo_dir,
            repo_url=repo_url,
            base_commit=base_commit,
            pr_number=pr_number,
        )
        if fetched_pr_head:
            source = f"{source}+pr-head-fetch"
        return RepoWorkspace(repo_dir=repo_dir, repo_url=repo_url, base_commit=base_commit, clone_source=source)

    def _clone(self, *, repo_url: str, base_commit: str, repo_dir: Path) -> str:
        if self.use_reference_repo and self.reference_repo and self._reference_can_checkout(base_commit):
            proc = run_cmd(["git", "clone", "--no-hardlinks", "--no-checkout", str(self.reference_repo), str(repo_dir)], timeout=900)
            require_ok(proc, "git clone from reference repo")
            return "reference"
        proc = run_cmd(["git", "clone", "--no-checkout", repo_url, str(repo_dir)], timeout=2400)
        require_ok(proc, "git clone from remote")
        return "remote"

    def _checkout_clean_with_pr_fallback(
        self,
        *,
        repo_dir: Path,
        repo_url: str,
        base_commit: str,
        pr_number: int | None,
    ) -> bool:
        try:
            self._checkout_clean(repo_dir, base_commit)
            return False
        except RuntimeError as first_error:
            if not pr_number:
                raise
            self._fetch_pr_head(repo_dir=repo_dir, repo_url=repo_url, pr_number=pr_number)
            try:
                self._checkout_clean(repo_dir, base_commit)
            except RuntimeError as retry_error:
                raise RuntimeError(
                    f"Unable to checkout base commit {base_commit} after fetching PR #{pr_number} head.\n"
                    f"Initial checkout error:\n{first_error}\n\nRetry checkout error:\n{retry_error}"
                ) from retry_error
            return True

    def _checkout_clean(self, repo_dir: Path, base_commit: str) -> None:
        checkout = run_cmd(["git", "checkout", "--force", base_commit], cwd=repo_dir, timeout=900)
        require_ok(checkout, f"git checkout {base_commit}")
        reset = run_cmd(["git", "reset", "--hard", base_commit], cwd=repo_dir, timeout=300)
        require_ok(reset, f"git reset --hard {base_commit}")
        clean = run_cmd(["git", "clean", "-fdx"], cwd=repo_dir, timeout=300)
        require_ok(clean, "git clean")

    def _fetch_pr_head(self, *, repo_dir: Path, repo_url: str, pr_number: int) -> None:
        set_url = run_cmd(["git", "remote", "set-url", "origin", repo_url], cwd=repo_dir, timeout=60)
        require_ok(set_url, "git remote set-url origin")
        fetch = run_cmd(
            ["git", "fetch", "origin", f"pull/{pr_number}/head:refs/remotes/origin/pr-{pr_number}-head", "--no-tags"],
            cwd=repo_dir,
            timeout=2400,
        )
        require_ok(fetch, f"git fetch PR #{pr_number} head")

    def _reference_can_checkout(self, base_commit: str) -> bool:
        if not self.reference_repo or not (self.reference_repo / ".git").exists():
            return False
        exists = run_cmd(["git", "cat-file", "-e", f"{base_commit}^{{commit}}"], cwd=self.reference_repo, timeout=60)
        if exists.returncode != 0:
            return False
        # A local reference can contain the commit object but miss blobs. Prefer
        # remote clone unless the caller explicitly enables references and this
        # quick tree read succeeds.
        tree = run_cmd(["git", "ls-tree", "-r", "--name-only", base_commit, "--", "package.json"], cwd=self.reference_repo, timeout=60)
        return tree.returncode == 0

    def _remove_within_root(self, target: Path) -> None:
        resolved_root = self.workspaces_root.resolve()
        resolved_target = target.resolve()
        if resolved_root == resolved_target or resolved_root not in resolved_target.parents:
            raise ValueError(f"Refusing to remove path outside workspaces root: {resolved_target}")
        shutil.rmtree(resolved_target, onerror=_make_writable_and_retry)


def _make_writable_and_retry(function: object, path: str, _exc_info: object) -> None:
    os.chmod(path, stat.S_IWRITE)
    function(path)
