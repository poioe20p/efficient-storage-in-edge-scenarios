#!/usr/bin/env python3

"""Generate a deterministic commit message from staged changes."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter


TOPIC_META: dict[str, dict[str, str]] = {
    "edge_server_runtime": {
        "label": "Edge server runtime",
        "scope": "edge",
        "summary": "modularized runtime and request lifecycle behavior",
    },
    "sdn_controller": {
        "label": "SDN controller",
        "scope": "controller",
        "summary": "refined VIP routing and recovery-side decision flow",
    },
    "testing_toolchain": {
        "label": "Testing toolchain",
        "scope": "testing",
        "summary": "extended experiment orchestration and analysis support",
    },
    "scripts_tooling": {
        "label": "Scripts tooling",
        "scope": "scripts",
        "summary": "improved local automation and developer workflow scripts",
    },
    "docker_surfaces": {
        "label": "Container surfaces",
        "scope": "docker",
        "summary": "updated container build/runtime integration surfaces",
    },
    "operation_docs": {
        "label": "Operation docs",
        "scope": "docs",
        "summary": "updated operational guidance and experiment narratives",
    },
    "docs_general": {
        "label": "Documentation",
        "scope": "docs",
        "summary": "refined repository documentation content",
    },
    "thesis_materials": {
        "label": "Thesis materials",
        "scope": "thesis",
        "summary": "updated thesis and research artifacts",
    },
    "repo_tools": {
        "label": "Repository tools",
        "scope": "tools",
        "summary": "updated utility tooling and supporting scripts",
    },
    "repo_misc": {
        "label": "Repository core",
        "scope": "repo",
        "summary": "applied cross-cutting repository updates",
    },
}


TOPIC_RULES: list[tuple[str, str]] = [
    ("source/docker/edge_server/source/", "edge_server_runtime"),
    ("source/sdn_controller/", "sdn_controller"),
    ("source/scripts/testing/", "testing_toolchain"),
    ("source/scripts/tools/", "scripts_tooling"),
    ("source/scripts/", "scripts_tooling"),
    ("source/docker/", "docker_surfaces"),
    ("docs/operation/", "operation_docs"),
    ("docs/", "docs_general"),
    ("tese/", "thesis_materials"),
    ("tools/", "repo_tools"),
]


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _staged_files() -> list[str]:
    output = _run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def _shortstat() -> str:
    output = _run_git(["diff", "--cached", "--shortstat"]).strip()
    return output


def _topic_for_path(path: str) -> str:
    for prefix, topic in TOPIC_RULES:
        if path.startswith(prefix):
            return topic
    return "repo_misc"


def _collect_topics(files: list[str]) -> Counter[str]:
    return Counter(_topic_for_path(path) for path in files)


def _primary_topic(topic_counts: Counter[str]) -> str:
    if not topic_counts:
        return "repo_misc"
    return topic_counts.most_common(1)[0][0]


def _infer_type(topic_counts: Counter[str]) -> str:
    if not topic_counts:
        return "chore"

    keys = set(topic_counts)
    docs_only = keys.issubset({"operation_docs", "docs_general", "thesis_materials"})
    if docs_only:
        return "docs"

    if "edge_server_runtime" in keys or "sdn_controller" in keys:
        return "feat"

    if keys == {"testing_toolchain"}:
        return "test"

    return "chore"


def _infer_scope(primary_topic: str) -> str:
    return TOPIC_META.get(primary_topic, TOPIC_META["repo_misc"])["scope"]


def _subject_action(primary_topic: str) -> str:
    actions = {
        "edge_server_runtime": "rework edge runtime structure",
        "sdn_controller": "refine controller routing behavior",
        "testing_toolchain": "expand testing workflow coverage",
        "scripts_tooling": "improve repository scripting workflow",
        "docker_surfaces": "adjust container runtime surfaces",
        "operation_docs": "update operation workflow narratives",
        "docs_general": "update repository documentation",
        "thesis_materials": "update thesis and research materials",
        "repo_tools": "improve utility tooling",
        "repo_misc": "apply cross-cutting repository updates",
    }
    return actions.get(primary_topic, actions["repo_misc"])


def _build_subject(commit_type: str, scope: str, primary_topic: str) -> str:
    subject = f"{commit_type}({scope}): {_subject_action(primary_topic)}"
    return subject[:72]


def _build_body(topic_counts: Counter[str], shortstat: str) -> str:
    lines: list[str] = []
    if shortstat:
        lines.append(shortstat)

    if topic_counts:
        lines.append("")
        lines.append("Topics:")
        for topic, count in topic_counts.most_common(6):
            label = TOPIC_META.get(topic, TOPIC_META["repo_misc"])["label"]
            noun = "file" if count == 1 else "files"
            lines.append(f"- {label} ({count} {noun})")

        lines.append("")
        lines.append("Change focus:")
        for topic, _count in topic_counts.most_common(4):
            summary = TOPIC_META.get(topic, TOPIC_META["repo_misc"])["summary"]
            lines.append(f"- {summary}")

    return "\n".join(lines).rstrip()


def generate_message(include_body: bool = True) -> str:
    files = _staged_files()
    if not files:
        return ""

    topic_counts = _collect_topics(files)
    primary_topic = _primary_topic(topic_counts)
    commit_type = _infer_type(topic_counts)
    scope = _infer_scope(primary_topic)
    subject = _build_subject(commit_type, scope, primary_topic)

    if not include_body:
        return subject

    body = _build_body(topic_counts, _shortstat())
    if not body:
        return subject
    return f"{subject}\n\n{body}\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a commit message from staged changes."
    )
    parser.add_argument(
        "--subject-only",
        action="store_true",
        help="Print only the subject line.",
    )
    parser.add_argument(
        "--from-staged",
        action="store_true",
        help="Compatibility flag for Makefile/hook usage.",
    )
    args = parser.parse_args()

    message = generate_message(include_body=not args.subject_only)
    if not message:
        return 1

    sys.stdout.write(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
