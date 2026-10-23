from backend.app.modules.review.diff_analyzer import DiffAnalyzer


def test_added_debug_line_has_location_and_structured_fields() -> None:
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
 value = 1
+print(value)
"""

    findings = DiffAnalyzer().analyze(diff)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.category == "quality"
    assert finding.severity == "low"
    assert finding.file_path == "app.py"
    assert finding.line == 2
    assert finding.message == "Debug print statement detected."


def test_removed_and_unchanged_debug_lines_are_ignored() -> None:
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,3 +1,3 @@
-print(removed)
 print(unchanged)
+value = 1
"""

    assert DiffAnalyzer().analyze(diff) == []


def test_multiple_detectors_and_severities() -> None:
    diff = """diff --git a/service.py b/service.py
--- a/service.py
+++ b/service.py
@@ -1,2 +1,8 @@
 value = 1
+TODO: finish this
+FIXME: handle this
+try:
+    process()
+except Exception:
+    pass
+API_KEY = \"real-secret-value\"
"""

    findings = DiffAnalyzer().analyze(diff)
    by_message = {finding.message: finding for finding in findings}

    assert by_message["TODO marker introduced in the change."].severity == "low"
    assert by_message["FIXME marker introduced in the change."].severity == "medium"
    assert by_message["Broad exception handling detected."].severity == "high"
    assert by_message["Potential hard-coded secret detected."].severity == "high"


def test_secret_placeholders_and_specific_exception_are_ignored() -> None:
    diff = """diff --git a/config.py b/config.py
--- a/config.py
+++ b/config.py
@@ -1,2 +1,4 @@
 value = 1
+API_KEY = \"YOUR_API_KEY\"
+TOKEN = \"<token>\"
+except ValueError:
"""

    assert DiffAnalyzer().analyze(diff) == []


def test_unsafe_subprocess_and_safe_argument_list() -> None:
    diff = """diff --git a/runner.py b/runner.py
--- a/runner.py
+++ b/runner.py
@@ -1,2 +1,4 @@
 value = 1
+subprocess.run(command, shell=True)
+subprocess.run([\"tool\", \"--check\"], shell=False)
+os.system(user_input)
"""

    findings = DiffAnalyzer().analyze(diff)

    assert len(findings) == 2
    assert all(finding.category == "security" for finding in findings)
    assert all(finding.severity == "high" for finding in findings)
    assert {finding.line for finding in findings} == {2, 4}


def test_same_line_different_categories_are_retained() -> None:
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,1 +1,2 @@
 value = 1
+print(value)  # TODO: remove
"""

    findings = DiffAnalyzer().analyze(diff)

    assert {(finding.category, finding.line) for finding in findings} == {
        ("quality", 2),
        ("maintainability", 2),
    }
