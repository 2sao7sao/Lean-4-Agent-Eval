"""Integration interfaces. The sales SpecCompiler has an M1 implementation.

Documents must be validated at each boundary. Protocol conformance alone does
not validate semantics, evidence integrity, permissions or proof claims.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

Document = Mapping[str, Any]


@dataclass(frozen=True)
class RunContext:
    run_id: str
    contract_sha256: str
    output_directory: Path
    max_tool_calls: int
    max_seconds: int
    max_tokens: int
    max_cost_usd: str


class SpecCompiler(Protocol):
    def compile(self, request: str, answers: Mapping[str, str]) -> Document:
        """Return a clarification/review envelope; contract is null while unresolved.

        SalesSpecCompiler is the current domain implementation. No execution or
        approval is implied by a ready-for-review response.
        """
        ...


class CaseBuilder(Protocol):
    def build(self, confirmed_contract: Document, coverage_plan: Document) -> Sequence[Document]:
        """Build from M1 requirement confirmation; runtime freezing is a later gate.

        SalesCaseBuilder materializes local sales fixtures. Packaging keeps private
        oracles separate from agent inputs. This does not authorize agent execution.
        """
        ...


class AgentAdapter(Protocol):
    def run(self, case: Document, context: RunContext) -> Document:
        """Return actual run data with independently collected boundary evidence."""
        ...


class Verifier(Protocol):
    def verify(self, check: Document, run: Document, evidence: Document) -> Document:
        """Return a receipt bound to the run, contract and verifier version."""
        ...


class CampaignReporter(Protocol):
    def summarize(self, contract: Document, runs: Sequence[Document],
                  receipts: Sequence[Document]) -> Document:
        """Keep failure, missing evidence and infrastructure errors visible."""
        ...
