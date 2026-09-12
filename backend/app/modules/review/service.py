from __future__ import annotations

import subprocess
from pathlib import Path

from backend.app.modules.knowledge.service import KnowledgeGraphService
from backend.app.modules.parser.service import ParserService
from backend.app.modules.review.models import ReviewFinding, ReviewResult
from backend.app.modules.review.diff_analyzer import DiffAnalyzer


class ReviewService:
    """Simple review service that produces findings from git diff and parse heuristics."""

    def __init__(
        self,
        parser_service: ParserService | None = None,
        knowledge_graph_service: KnowledgeGraphService | None = None,
        diff_analyzer: DiffAnalyzer | None = None,
    ) -> None:
        self._parser_service = parser_service or ParserService()
        self._knowledge_graph_service = knowledge_graph_service or KnowledgeGraphService()
        self._diff_analyzer = diff_analyzer or DiffAnalyzer()

    def review_diff(
        self,
        repository_path: str,
        base_sha: str = "",
        head_sha: str = "",
        changed_files: list[str] | None = None,
    ) -> ReviewResult:
        repo_path = Path(repository_path)

        if base_sha and head_sha:
            diff_command = [
                "git",
                "diff",
                "--unified=80",
                base_sha,
                head_sha,
            ]
        else:
            diff_command = [
                "git",
                "diff",
                "--unified=80",
            ]

        diff_output = subprocess.run(
            diff_command,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )

        diff_text = diff_output.stdout

        if changed_files is None:
            changed_files_output = subprocess.run(
                [
                    "git",
                    "diff",
                    "--name-only",
                    base_sha,
                    head_sha,
                ]
                if base_sha and head_sha
                else ["git", "diff", "--name-only"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )

            changed_files = [
                line
                for line in changed_files_output.stdout.splitlines()
                if line.strip()
            ]

        summary = (
            f"{len(changed_files)} file changed"
            if len(changed_files) == 1
            else f"{len(changed_files)} files changed"
        )

        knowledge_graph = self._knowledge_graph_service.build(repository_path)

        findings: list[ReviewFinding] = []

        # Review the actual PR diff rather than the clean working tree.
        if diff_text.strip():
            if self._parser_service.detect_style_issue(diff_text):
                findings.append(
                    ReviewFinding(
                        category="style",
                        severity="low",
                        file_path=None,
                        line=None,
                        message=(
                            "Potential style issue detected in the pull request diff using repository context; "
                            f"the repository context includes {knowledge_graph.file_count} files and "
                            f"{knowledge_graph.module_count} modules."
                            ),
                        explanation=(
                            "The current parser detected a possible style issue in the changed code. "
                            "Repository context was used during the review."
                                    ),
                        suggestion=(
                            "Review the changed code for consistency with the repository's style conventions."
                        ),
                    )
                )

        findings.extend(self._diff_analyzer.analyze(diff_text))

        if not findings:
            findings.append(
                ReviewFinding(
                    category="review",
                    severity="info",
                    file_path=None,
                    line=None,
                    message="No obvious issues found in the supplied pull request diff.",
                    explanation=(
                        f"Repository context includes {knowledge_graph.file_count} files and "
                        f"{knowledge_graph.module_count} modules."
                    ),
                    suggestion=None,
                )
            )

        findings = self._deduplicate_findings(findings)

        return ReviewResult(
            review_id="review-001",
            summary=summary,
            findings=findings,
        )

    @staticmethod
    def _deduplicate_findings(findings: list[ReviewFinding]) -> list[ReviewFinding]:
        unique: list[ReviewFinding] = []
        seen: set[tuple[str, str | None, int | None, str]] = set()
        for finding in findings:
            identity = (finding.category, finding.file_path, finding.line, finding.message)
            if identity not in seen:
                seen.add(identity)
                unique.append(finding)
        return unique
