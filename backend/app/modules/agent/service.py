from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from backend.app.modules.agent.memory import RepositoryMemory, RepositoryMemoryStore
from backend.app.modules.knowledge.service import KnowledgeGraphService
from backend.app.modules.review.service import ReviewService


@dataclass(frozen=True)
class PullRequestReview:
    agent_name: str
    pull_request_number: int
    changed_files: list[str]
    confidence: float
    confidence_reasons: list[str]
    baseline_commit: str | None
    recommendation: str
    summary: str
    findings: list[dict[str, str]]


class PullRequestReviewAgent:
    """Reviews a PR using the latest analysis saved after a merge."""

    def __init__(
        self,
        memory_store: RepositoryMemoryStore,
        knowledge_service: KnowledgeGraphService | None = None,
        review_service: ReviewService | None = None,
    ) -> None:
        self._memory_store = memory_store
        self._knowledge_service = knowledge_service or KnowledgeGraphService()
        self._review_service = review_service or ReviewService()

    def remember_merged_repository(self, repository_id: str, repository_path: str, pr_number: int) -> RepositoryMemory:
        graph = self._knowledge_service.build(repository_path)
        commit_sha = self._git_output(["rev-parse", "HEAD"], repository_path)
        memory = RepositoryMemory(repository_id, commit_sha, graph.file_count, graph.module_count, pr_number)
        self._memory_store.save(memory)
        return memory

    def review_pull_request(
        self,
        repository_id: str,
        repository_path: str,
        pr_number: int,
        base_sha: str = "",
        head_sha: str = "",
    ) -> PullRequestReview:
        baseline = self._memory_store.get(repository_id)

        changed_files = self._changed_files(
            repository_path,
            base_sha,
            head_sha,
        )

        confidence = 0.45
        reasons = ["The review inspected the pull request file diff."]

        if baseline:
            confidence += 0.25
            reasons.append(
                f"It used merged PR #{baseline.merged_pr_number} "
                f"at {baseline.commit_sha[:12]} as repository memory."
            )
        else:
            reasons.append("No merged baseline is stored yet, so this is a first-pass review.")

        if base_sha and head_sha:
            confidence += 0.15
            reasons.append("Both base and head commits were supplied for a precise comparison.")

        if changed_files:
            confidence += min(0.12, len(changed_files) * 0.02)
            reasons.append(f"The diff contains {len(changed_files)} changed file(s).")
        else:
            reasons.append("No diff files were available; verify that the supplied commit references are fetched.")

        review = self._review_service.review_diff(
            repository_path=repository_path,
            base_sha=base_sha,
            head_sha=head_sha,
            changed_files=changed_files,
        )

        findings = [
            {
                "category": finding.category,
                "message": finding.message,
            }
            for finding in review.findings
        ]

        confidence = round(min(confidence, 0.95), 2)

        recommendation = "Add focused tests for each changed module before merging."

        return PullRequestReview(
            agent_name="pull-request-review-agent",
            pull_request_number=pr_number,
            changed_files=changed_files,
            confidence=confidence,
            confidence_reasons=reasons,
            baseline_commit=baseline.commit_sha if baseline else None,
            recommendation=recommendation,
            summary=review.summary,
            findings=findings,
        )

    @staticmethod
    def _git_output(command: list[str], repository_path: str) -> str:
        result = subprocess.run(["git", *command], cwd=Path(repository_path), capture_output=True, text=True, check=True)
        return result.stdout.strip()

    def _changed_files(self, repository_path: str, base_sha: str, head_sha: str) -> list[str]:
        """
        Return files changed between the supplied base and head commits.

        Use a direct two-tree comparison because GitHub App checkouts are
        intentionally shallow and may not contain enough ancestry to calculate
        a three-dot merge-base comparison.
        """
        if base_sha and head_sha:
            command = ["diff", "--name-only", base_sha, head_sha]
        else:
            command = ["diff", "--name-only"]

        try:
            output = self._git_output(command, repository_path)
        except subprocess.CalledProcessError:
            output = self._git_output(["diff", "--name-only"], repository_path)

        return [line for line in output.splitlines() if line.strip()]
