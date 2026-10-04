from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin" / "conn-pilot"


class PluginPackageTests(unittest.TestCase):
    def test_portable_and_codex_manifests_are_consistent(self) -> None:
        portable = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
        portable_mcp = json.loads((PLUGIN / "mcp.json").read_text(encoding="utf-8"))
        codex = json.loads(
            (PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        codex_mcp = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))

        self.assertEqual(portable["name"], "conn-pilot")
        self.assertEqual(portable["version"], "0.1.0-beta.1")
        self.assertEqual(codex["name"], portable["name"])
        self.assertEqual(codex["version"], portable["version"])
        self.assertEqual(codex["skills"], "./skills/")
        self.assertEqual(codex["mcpServers"], "./.mcp.json")
        self.assertEqual(
            portable_mcp["mcpServers"]["conn-pilot"]["url"],
            codex_mcp["mcpServers"]["conn-pilot"]["url"],
        )
        self.assertEqual(
            portable_mcp["mcpServers"]["conn-pilot"]["type"], "streamable-http"
        )

    def test_marketplace_points_to_the_packaged_plugin(self) -> None:
        marketplace = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(marketplace["name"], "conn-pilot-private")
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "conn-pilot")
        source = (ROOT / entry["source"]["path"]).resolve()
        self.assertEqual(source, PLUGIN.resolve())
        self.assertTrue((source / "plugin.json").is_file())

    def test_all_skills_have_valid_identity_and_mcp_dependency(self) -> None:
        skill_dirs = sorted(path for path in (PLUGIN / "skills").iterdir() if path.is_dir())
        self.assertEqual(
            {path.name for path in skill_dirs},
            {
                "compare-conn-methods",
                "design-conn-experiment",
                "review-conn-results",
                "run-conn-analysis",
            },
        )
        for path in skill_dirs:
            text = (path / "SKILL.md").read_text(encoding="utf-8")
            match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
            self.assertIsNotNone(match)
            metadata = yaml.safe_load(match.group(1))
            self.assertEqual(metadata["name"], path.name)
            agent = yaml.safe_load(
                (path / "agents" / "openai.yaml").read_text(encoding="utf-8")
            )
            dependency = agent["dependencies"]["tools"][0]
            self.assertEqual(dependency["value"], "conn-pilot")
            self.assertEqual(dependency["transport"], "streamable_http")
            self.assertIn(f"${path.name}", agent["interface"]["default_prompt"])


if __name__ == "__main__":
    unittest.main()
