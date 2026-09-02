from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from backend.app.modules.knowledge.service import KnowledgeGraphService
from backend.app.modules.parser.service import ParserService


@dataclass(frozen=True)
class ReviewFinding:
    category: str
    message: str


@dataclass(frozen=True)
class ReviewResult:
    review_id: str
    summary: str
    findings: list[ReviewFinding]


class ReviewService:
    """Simple review service that produces findings from git diff and parse heuristics."""

    def __init__(
        self,
        parser_service: ParserService | None = None,
        knowledge_graph_service: KnowledgeGraphService | None = None,
    ) -> None:
        self._parser_service = parser_service or ParserService()
        self._knowledge_graph_service = knowledge_graph_service or KnowledgeGraphService()

    def review_diff(self, repository_path: str) -> ReviewResult:
        repo_path = Path(repository_path)
        diff_output = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        changed_files = [line for line in diff_output.stdout.splitlines() if line.strip()]
        summary = f"{len(changed_files)} file changed" if len(changed_files) == 1 else f"{len(changed_files)} files changed"

        knowledge_graph = self._knowledge_graph_service.build(repository_path)
        findings: list[ReviewFinding] = []
        for parsed_change in self._parser_service.parse_changes(repository_path):
            if self._parser_service.detect_style_issue(parsed_change.content):
                findings.append(
                    ReviewFinding(
                        category="style",
                        message=(
                            f"Potential style issue in {parsed_change.file_path} "
                            f"using repository context with {knowledge_graph.module_count} modules"
                        ),
                    )
                )

        if not findings:
            findings.append(
                ReviewFinding(
                    category="style",
                    message=(
                        "No obvious issues found; repository context includes "
                        f"{knowledge_graph.file_count} files and {knowledge_graph.module_count} modules"
                    ),
                )
            )

        return ReviewResult(review_id="review-001", summary=summary, findings=findings)
