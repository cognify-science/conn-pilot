from __future__ import annotations

import ast
import json
import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_MCP_URL = "https://control-plane-production-0adf.up.railway.app/mcp"


class PublicDocumentationTests(unittest.TestCase):
    def test_required_scientific_and_integration_guides_exist(self) -> None:
        required = {
            "SCIENTIST_CONTEXT.md",
            "CHANGELOG.md",
            "docs/reference/mcp-tools.md",
            "docs/reference/conn-official-sources.md",
            "docs/reference/conn-official-sources.json",
            "docs/science/statistical-methods.md",
            "docs/science/scientific-audit.md",
            "contracts/scientific_audit.v1.json",
            "docs/science/qc-manual.md",
            "docs/science/worked-example.md",
            "docs/science/evidence-governance.md",
            "docs/science/data-governance.md",
            "docs/science/parameter-selector-evaluation.md",
            "docs/science/glossary.md",
            "docs/science/scientific-faq.md",
            "docs/science/study-report-template.md",
            "docs/science/architecture.md",
            "docs/science/scientific-modules.md",
            "docs/science/preloaded-datasets.md",
            "docs/science/benchmark-validation-2026-10.md",
            "docs/science/data/benchmark-results-2026-10.json",
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
        paths = [
            ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "CLAUDE.md",
            ROOT / "SCIENTIST_CONTEXT.md", ROOT / "CHANGELOG.md",
            ROOT / ".github" / "copilot-instructions.md",
        ]
        paths.extend((ROOT / "docs").rglob("*.md"))
        paths.extend((ROOT / "docs" / "science" / "data").glob("*.json"))
        paths.extend((ROOT / "docs" / "reference").glob("*.json"))
        paths.extend((ROOT / "plugin" / "conn-pilot").glob("*.json"))
        forbidden = re.compile(r"C:\\Users\\|D:\\ConnPilot|100\.76\.|192\.168\.", re.I)
        findings = []
        for path in paths:
            if forbidden.search(path.read_text(encoding="utf-8-sig")):
                findings.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(findings, [])

    def test_scientific_reference_covers_exact_public_mcp_surface(self) -> None:
        source = (ROOT / "src" / "conn_pilot" / "control_plane.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        tools = {
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "server"
                and decorator.func.attr == "tool"
                for decorator in node.decorator_list
            )
        }
        reference = (ROOT / "docs" / "reference" / "mcp-tools.md").read_text(encoding="utf-8")
        documented = set(re.findall(r"^\| `([a-z_]+)` \|", reference, re.M))
        self.assertTrue(tools)
        self.assertEqual(documented, tools)
        self.assertIn(f"exposes {len(tools)} tools", reference)

    def test_official_conn_consultation_index_matches_guide(self) -> None:
        directory = ROOT / "docs" / "reference"
        registry = json.loads((directory / "conn-official-sources.json").read_text(encoding="utf-8"))
        guide = (directory / "conn-official-sources.md").read_text(encoding="utf-8")
        definitions = dict(re.findall(r"^\[([^\]]+)\]: (https://\S+)$", guide, re.M))
        citations = set(re.findall(r"\]\[([^\]]+)\]", guide))
        self.assertTrue(citations)
        self.assertLessEqual(citations, definitions.keys())
        sources = registry["sources"]
        self.assertEqual(len({source["id"] for source in sources}), len(sources))
        self.assertEqual({source["id"]: source["url"] for source in sources}, definitions)
        allowed_hosts = {"web.conn-toolbox.org", "github.com", "www.nitrc.org", "doi.org"}
        for source in sources:
            parsed = urlparse(source["url"])
            self.assertEqual(parsed.scheme, "https")
            self.assertIn(parsed.hostname, allowed_hosts)
            self.assertTrue(source["topics"])
            self.assertTrue(source["version_relation"])
            if source["kind"] == "released_source":
                self.assertEqual(source["commit"], registry["upstream"]["reference_commit"])
                self.assertIn(f"/{source['commit']}/", source["url"])

    def test_public_documentation_relative_links_resolve(self) -> None:
        paths = [ROOT / "README.md", ROOT / "SCIENTIST_CONTEXT.md", ROOT / "CHANGELOG.md"]
        paths.extend((ROOT / "docs").rglob("*.md"))
        broken = []
        for path in paths:
            source = re.sub(
                r"```[^\n]*\n.*?```", "", path.read_text(encoding="utf-8-sig"), flags=re.S
            )
            for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", source):
                target = link.split()[0].strip("<>")
                if re.match(r"(?:[a-z][a-z0-9+.-]*:|#)", target, re.I):
                    continue
                target_path = path.parent / unquote(target.split("#", 1)[0])
                if not target_path.exists():
                    broken.append((path.relative_to(ROOT).as_posix(), target))
        self.assertEqual(broken, [])


if __name__ == "__main__":
    unittest.main()
