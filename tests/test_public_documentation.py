from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_MCP_URL = "https://control-plane-production-0adf.up.railway.app/mcp"


class PublicDocumentationTests(unittest.TestCase):
    def test_required_scientific_and_integration_guides_exist(self) -> None:
        required = {
            "docs/science/architecture.md",
            "docs/science/scientific-modules.md",
            "docs/science/pipeline-lifecycle.md",
            "docs/science/parameter-selection.md",
            "docs/science/evidence-corpus.md",
            "docs/science/qc-and-inference.md",
            "docs/science/reproducibility.md",
            "docs/integrations/ai-assisted-setup.md",
            "docs/integrations/openai-clients.md",
            "docs/integrations/claude.md",
            "docs/integrations/microsoft-copilot.md",
            "docs/integrations/verification-checklist.md",
            "docs/integrations/assistant-bootstrap-prompt.md",
            "docs/security-and-data-boundaries.md",
            "AGENTS.md",
            "CLAUDE.md",
            ".github/copilot-instructions.md",
        }
        missing = sorted(path for path in required if not (ROOT / path).is_file())
        self.assertEqual(missing, [])

    def test_all_mcp_client_files_use_the_public_endpoint(self) -> None:
        files = (
            ROOT / ".mcp.json",
            ROOT / ".vscode" / "mcp.json",
            ROOT / "plugin" / "conn-pilot" / ".mcp.json",
            ROOT / "plugin" / "conn-pilot" / "mcp.json",
        )
        for path in files:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            servers = payload.get("mcpServers", payload.get("servers"))
            self.assertEqual(servers["conn-pilot"]["url"], PUBLIC_MCP_URL)

    def test_public_guides_do_not_disclose_private_machine_details(self) -> None:
        paths = [ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "CLAUDE.md"]
        paths.extend((ROOT / "docs" / "science").glob("*.md"))
        paths.extend((ROOT / "docs" / "integrations").glob("*.md"))
        paths.append(ROOT / "docs" / "security-and-data-boundaries.md")
        paths.extend((ROOT / "plugin" / "conn-pilot").glob("*.json"))
        forbidden = re.compile(r"C:\\Users\\|D:\\ConnPilot|100\.76\.|192\.168\.", re.I)
        findings = []
        for path in paths:
            if forbidden.search(path.read_text(encoding="utf-8-sig")):
                findings.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
