"""Contract tests for the MCP surface: what a client actually sees.

These assertions pin down the parts of the MCP spec we claim in docs/COMPLIANCE.md,
so a careless edit cannot silently drop them.
"""

from __future__ import annotations

import asyncio
import unittest

import context  # noqa: F401

from aninest.server import mcp

EXPECTED_TOOLS = {
    "art_search": ("Illustration search", True),
    "arena_lookup": ("Arena lineup lookup", True),
    "memory_search": ("Memory search", False),
    "memory_stats": ("Memory store stats", False),
    "service_health": ("Service health", False),
}


def _tools():
    return asyncio.run(mcp.list_tools())


class ToolSurfaceTest(unittest.TestCase):
    def test_all_tools_listed(self) -> None:
        names = {tool.name for tool in _tools()}
        self.assertEqual(names, set(EXPECTED_TOOLS))

    def test_every_tool_has_schema_and_description(self) -> None:
        for tool in _tools():
            with self.subTest(tool=tool.name):
                self.assertEqual(tool.inputSchema.get("type"), "object")
                self.assertTrue((tool.description or "").strip())

    def test_titles_match_docs(self) -> None:
        for tool in _tools():
            with self.subTest(tool=tool.name):
                self.assertEqual(tool.title, EXPECTED_TOOLS[tool.name][0])

    def test_annotations_declare_read_only(self) -> None:
        for tool in _tools():
            with self.subTest(tool=tool.name):
                ann = tool.annotations
                self.assertIsNotNone(ann, "annotations missing")
                self.assertTrue(ann.readOnlyHint, "every tool is read-only")
                self.assertFalse(ann.destructiveHint)
                self.assertEqual(bool(ann.openWorldHint), EXPECTED_TOOLS[tool.name][1])

    def test_instructions_explain_health_first(self) -> None:
        self.assertIn("service_health", mcp.instructions or "")


class ResourceAndPromptTest(unittest.TestCase):
    def test_memory_stats_resource(self) -> None:
        resources = asyncio.run(mcp.list_resources())
        uris = {str(r.uri) for r in resources}
        self.assertIn("aninest://memory/stats", uris)

    def test_find_illustration_prompt(self) -> None:
        prompts = asyncio.run(mcp.list_prompts())
        self.assertIn("find_illustration", {p.name for p in prompts})


if __name__ == "__main__":
    unittest.main()
