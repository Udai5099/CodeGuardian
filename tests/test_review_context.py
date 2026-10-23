from __future__ import annotations

from pathlib import Path
import subprocess

from backend.app.modules.review.context import ReviewContextBuilder
from backend.app.modules.review.models import ReviewFinding


def _git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "context-repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.name", "Test User")
    _git(repository, "config", "user.email", "test@example.com")
    return repository


def _commit(repository: Path, message: str) -> str:
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", message)
    return _git(repository, "rev-parse", "HEAD")


def test_builds_context_with_added_lines_language_and_surrounding_source(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    source = repository / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("one\ntwo\nthree\n", encoding="utf-8")
    base_sha = _commit(repository, "initial")

    source.write_text("one\ntwo\nprint('new')\nthree\n", encoding="utf-8")
    head_sha = _commit(repository, "add line")

    context = ReviewContextBuilder(
        str(repository),
        base_sha,
        head_sha,
        [ReviewFinding(category="quality", message="debug")],
    ).build()

    assert len(context.files) == 1
    file_context = context.files[0]
    assert file_context.file_path == "src/app.py"
    assert file_context.language == "Python"
    assert [(line.line_number, line.content) for line in file_context.added_lines] == [(3, "print('new')")]
    assert "2: two" in file_context.source_excerpt
    assert "3: print('new')" in file_context.source_excerpt
    assert context.deterministic_findings[0].message == "debug"


def test_respects_per_file_and_total_character_limits(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    first = repository / "first.py"
    second = repository / "second.py"
    first.write_text("old\n", encoding="utf-8")
    second.write_text("old\n", encoding="utf-8")
    base_sha = _commit(repository, "initial")

    first.write_text("\n".join(["line " + str(number) for number in range(1, 80)]) + "\n", encoding="utf-8")
    second.write_text("\n".join(["line " + str(number) for number in range(1, 80)]) + "\n", encoding="utf-8")
    head_sha = _commit(repository, "large changes")

    context = ReviewContextBuilder(
        str(repository),
        base_sha,
        head_sha,
        [],
        max_source_chars_per_file=40,
        max_total_source_chars=60,
    ).build()

    assert context.files
    assert all(len(file_context.source_excerpt) <= 40 for file_context in context.files)
    assert sum(len(file_context.source_excerpt) for file_context in context.files) <= 60


def test_ignores_env_and_private_key_files(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    (repository / ".env").write_text("TOKEN=old\n", encoding="utf-8")
    (repository / "server.pem").write_text("old-key\n", encoding="utf-8")
    base_sha = _commit(repository, "initial")

    (repository / ".env").write_text("TOKEN=new\n", encoding="utf-8")
    (repository / "server.pem").write_text("new-key\n", encoding="utf-8")
    head_sha = _commit(repository, "sensitive changes")

    context = ReviewContextBuilder(str(repository), base_sha, head_sha, []).build()

    assert context.files == []


def test_handles_deleted_files_without_reading_working_tree_path(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    deleted = repository / "deleted.py"
    deleted.write_text("print('gone')\n", encoding="utf-8")
    base_sha = _commit(repository, "initial")

    deleted.unlink()
    head_sha = _commit(repository, "delete file")

    context = ReviewContextBuilder(str(repository), base_sha, head_sha, []).build()

    assert len(context.files) == 1
    assert context.files[0].file_path == "deleted.py"
    assert context.files[0].added_lines == []
    assert context.files[0].source_excerpt == ""


def test_empty_diff_returns_empty_context(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    (repository / "app.py").write_text("value = 1\n", encoding="utf-8")
    commit_sha = _commit(repository, "initial")

    context = ReviewContextBuilder(str(repository), commit_sha, commit_sha, []).build()

    assert context.files == []
    assert context.deterministic_findings == []


def test_respects_max_files_limit(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    for number in range(3):
        (repository / f"file{number}.py").write_text("old\n", encoding="utf-8")
    base_sha = _commit(repository, "initial")

    for number in range(3):
        (repository / f"file{number}.py").write_text(f"new {number}\n", encoding="utf-8")
    head_sha = _commit(repository, "three changes")

    context = ReviewContextBuilder(str(repository), base_sha, head_sha, [], max_files=2).build()

    assert [file_context.file_path for file_context in context.files] == ["file0.py", "file1.py"]


def test_excludes_binary_files(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    binary = repository / "image.bin"
    binary.write_bytes(b"\x00\x01old")
    base_sha = _commit(repository, "initial")

    binary.write_bytes(b"\x00\x01new")
    head_sha = _commit(repository, "binary change")

    context = ReviewContextBuilder(str(repository), base_sha, head_sha, []).build()

    assert context.files == []


def test_handles_renamed_files(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    old_path = repository / "old.py"
    old_path.write_text("value = 1\n", encoding="utf-8")
    base_sha = _commit(repository, "initial")

    _git(repository, "mv", "old.py", "renamed.py")
    (repository / "renamed.py").write_text("value = 1\nvalue = 2\n", encoding="utf-8")
    head_sha = _commit(repository, "rename file")

    context = ReviewContextBuilder(str(repository), base_sha, head_sha, []).build()

    assert len(context.files) == 1
    assert context.files[0].file_path == "renamed.py"
    assert context.files[0].added_lines[0].line_number == 2


def test_source_excerpt_comes_from_head_not_working_tree(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    source = repository / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    base_sha = _commit(repository, "initial")

    source.write_text("value = 2\nhead line\n", encoding="utf-8")
    head_sha = _commit(repository, "head change")
    source.write_text("value = 999\nworking tree only\n", encoding="utf-8")

    context = ReviewContextBuilder(str(repository), base_sha, head_sha, []).build()

    excerpt = context.files[0].source_excerpt
    assert "2: head line" in excerpt
    assert "working tree only" not in excerpt


def test_unknown_language_falls_back_to_text(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    source = repository / "app.custom"
    source.write_text("old\n", encoding="utf-8")
    base_sha = _commit(repository, "initial")

    source.write_text("old\nnew\n", encoding="utf-8")
    head_sha = _commit(repository, "unknown language change")

    context = ReviewContextBuilder(str(repository), base_sha, head_sha, []).build()

    assert context.files[0].language == "Text"


def test_deterministic_findings_are_preserved(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    source = repository / "app.py"
    source.write_text("old\n", encoding="utf-8")
    base_sha = _commit(repository, "initial")

    source.write_text("old\nnew\n", encoding="utf-8")
    head_sha = _commit(repository, "change")
    finding = ReviewFinding(category="quality", message="existing finding")

    context = ReviewContextBuilder(str(repository), base_sha, head_sha, [finding]).build()

    assert context.deterministic_findings == [finding]
