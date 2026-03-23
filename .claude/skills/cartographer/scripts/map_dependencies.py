#!/usr/bin/env python3
"""Map internal module dependencies in the ContextCrawler codebase.

Scans all Python files under the given source directory, extracts internal
imports, and outputs a dependency graph in Mermaid format.

Usage:
    python map_dependencies.py contextcrawler/
    python map_dependencies.py contextcrawler/ --format json
    python map_dependencies.py contextcrawler/ --format dot
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path


def extract_imports(filepath: Path, package_name: str) -> list[tuple[str, str]]:
    """Extract internal imports from a Python file.

    Returns a list of (source_module, imported_module) tuples.
    """
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        print(f"  Warning: Could not parse {filepath}", file=sys.stderr)
        return []

    # Determine the module name from the file path
    parts = filepath.with_suffix("").parts
    try:
        pkg_idx = parts.index(package_name)
    except ValueError:
        return []

    source_module = ".".join(parts[pkg_idx:])
    if source_module.endswith(".__init__"):
        source_module = source_module[: -len(".__init__")]

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith(package_name):
                # Simplify to package-level module
                target = node.module
                imports.append((source_module, target))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(package_name):
                    imports.append((source_module, alias.name))

    return imports


def simplify_module(module: str, depth: int = 2) -> str:
    """Simplify module path to a given depth for cleaner diagrams.

    e.g., 'contextcrawler.http.client' with depth=2 → 'http.client'
    """
    parts = module.split(".")
    if parts[0] == "contextcrawler":
        parts = parts[1:]
    return ".".join(parts[:depth])


def build_graph(
    source_dir: Path, package_name: str, depth: int = 2
) -> dict[str, set[str]]:
    """Build the dependency graph from source files."""
    graph: dict[str, set[str]] = defaultdict(set)

    for pyfile in source_dir.rglob("*.py"):
        for source, target in extract_imports(pyfile, package_name):
            src = simplify_module(source, depth)
            tgt = simplify_module(target, depth)
            if src != tgt:  # Skip self-imports
                graph[src].add(tgt)

    return dict(graph)


def to_mermaid(graph: dict[str, set[str]]) -> str:
    """Convert the dependency graph to a Mermaid diagram."""
    lines = ["graph TD"]

    # Group nodes by top-level package
    packages: dict[str, list[str]] = defaultdict(list)
    all_nodes = set()
    for src, targets in graph.items():
        all_nodes.add(src)
        all_nodes.update(targets)

    for node in sorted(all_nodes):
        pkg = node.split(".")[0]
        packages[pkg].append(node)

    # Create subgraphs
    for pkg, nodes in sorted(packages.items()):
        safe_pkg = pkg.replace(".", "_")
        lines.append(f"    subgraph {safe_pkg}[{pkg}]")
        for node in sorted(nodes):
            safe_id = node.replace(".", "_")
            lines.append(f"        {safe_id}[{node}]")
        lines.append("    end")

    # Create edges
    for src, targets in sorted(graph.items()):
        safe_src = src.replace(".", "_")
        for tgt in sorted(targets):
            safe_tgt = tgt.replace(".", "_")
            lines.append(f"    {safe_src} --> {safe_tgt}")

    return "\n".join(lines)


def to_json(graph: dict[str, set[str]]) -> str:
    """Convert to JSON format."""
    serializable = {k: sorted(v) for k, v in graph.items()}
    return json.dumps(serializable, indent=2)


def to_dot(graph: dict[str, set[str]]) -> str:
    """Convert to Graphviz DOT format."""
    lines = ["digraph dependencies {", "    rankdir=TD;", '    node [shape=box];']
    for src, targets in sorted(graph.items()):
        for tgt in sorted(targets):
            lines.append(f'    "{src}" -> "{tgt}";')
    lines.append("}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Map ContextCrawler dependencies")
    parser.add_argument("source_dir", type=Path, help="Source directory to scan")
    parser.add_argument(
        "--package",
        default="contextcrawler",
        help="Package name (default: contextcrawler)",
    )
    parser.add_argument(
        "--format",
        choices=["mermaid", "json", "dot"],
        default="mermaid",
        help="Output format (default: mermaid)",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=2,
        help="Module path depth for grouping (default: 2)",
    )
    args = parser.parse_args()

    if not args.source_dir.is_dir():
        print(f"Error: {args.source_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    graph = build_graph(args.source_dir, args.package, args.depth)

    formatters = {
        "mermaid": to_mermaid,
        "json": to_json,
        "dot": to_dot,
    }

    print(formatters[args.format](graph))


if __name__ == "__main__":
    main()
