"""Contract tests for the MCP surface: what a client actually sees.

These assertions pin down the parts of the MCP spec we claim in docs/COMPLIANCE.md,
so a careless edit cannot silently drop them.
"""

from __future__ import annotations

import asyncio
import unittest

import context  # noqa: F401

from aninest.server import EXPECTED_TOOLS as SERVER_TOOLS
from aninest.server import mcp

#: tool -> (title, reaches outside the machine, may write the local overlay)
EXPECTED_TOOLS = {
    "art_search": ("Illustration search", True, False),
    "character_lookup": ("Character lookup", False, False),
    "portrait_identify": ("Portrait identification", False, False),
    "arena_lookup": ("Arena lineup lookup", True, False),
    "memory_search": ("Memory search", False, False),
    "memory_stats": ("Memory store stats", False, False),
    "service_health": ("Service health", False, False),
    "character_match": ("Character name match", False, False),
    "character_update": ("Character update", False, True),
    "character_correct": ("Character name correction", False, True),
}


def _tools():
    return asyncio.run(mcp.list_tools())


class ToolSurfaceTest(unittest.TestCase):
    def test_all_tools_listed(self) -> None:
        names = {tool.name for tool in _tools()}
        self.assertEqual(names, set(EXPECTED_TOOLS))
        # The package's own contract list must match what this test documents.
        self.assertEqual(set(SERVER_TOOLS), set(EXPECTED_TOOLS))

    def test_every_tool_has_schema_and_description(self) -> None:
        for tool in _tools():
            with self.subTest(tool=tool.name):
                self.assertEqual(tool.inputSchema.get("type"), "object")
                self.assertTrue((tool.description or "").strip())

    def test_titles_match_docs(self) -> None:
        for tool in _tools():
            with self.subTest(tool=tool.name):
                self.assertEqual(tool.title, EXPECTED_TOOLS[tool.name][0])

    def test_annotations_are_accurate(self) -> None:
        """A host decides whether to auto-approve from these three flags."""
        for tool in _tools():
            with self.subTest(tool=tool.name):
                ann = tool.annotations
                title, open_world, writes = EXPECTED_TOOLS[tool.name]
                self.assertIsNotNone(ann, "annotations missing")
                self.assertEqual(bool(ann.readOnlyHint), not writes)
                self.assertFalse(ann.destructiveHint, "nothing here deletes user data")
                self.assertEqual(bool(ann.openWorldHint), open_world)

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
