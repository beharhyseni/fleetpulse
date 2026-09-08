import json
from datetime import UTC, datetime
from typing import Any, cast

from anthropic import Anthropic
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AgentRun
from app.services.agent_tools import TOOLS, run_tool

MODEL = "claude-sonnet-4-6"
MAX_ITERATIONS = 8
MAX_TOKENS = 1500

AGENT_SYSTEM = (
    "You are the FleetPulse ops agent, investigating incidents on an IoT fleet. "
    "You may only learn about the world through your tools. Start broad (fleet stats "
    "or alerts), then drill into specific devices. Consult runbooks for procedure. "
    "Ground every claim in tool evidence: cite device names, alert ids, and numbers "
    "you actually received; never invent any. If the evidence warrants action, call "
    "create_maintenance_ticket once with a concise summary; it may return status "
    "proposed, which means a human must approve it, and that is expected. When you "
    "have enough evidence, stop calling tools and write your findings: what happened, "
    "the evidence, the likely cause stated cautiously, and recommended next steps."
)


def _get_client() -> Anthropic:
    return Anthropic(api_key=get_settings().anthropic_api_key, timeout=60.0)


def investigate(db: Session, question: str, approve_writes: bool = False) -> dict[str, Any]:
    client = _get_client()
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    trace: list[dict[str, Any]] = []
    in_tok = out_tok = 0
    status = "capped"
    resp = None

    for _ in range(MAX_ITERATIONS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=AGENT_SYSTEM,
            tools=cast(Any, TOOLS),
            messages=cast(Any, messages),
        )
        in_tok += resp.usage.input_tokens
        out_tok += resp.usage.output_tokens
        if resp.stop_reason != "tool_use":
            status = "completed"
            break
        messages.append({"role": "assistant", "content": resp.content})
        results: list[dict[str, Any]] = []
        for block in resp.content:
            if block.type == "tool_use":
                out = run_tool(db, block.name, dict(block.input), approve_writes)
                trace.append(
                    json.loads(
                        json.dumps(
                            {"tool": block.name, "input": dict(block.input), "result": out},
                            default=str,
                        )
                    )
                )
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(out, default=str),
                    }
                )
        messages.append({"role": "user", "content": results})

    findings = "".join(b.text for b in resp.content if b.type == "text") if resp else ""
    run = AgentRun(
        question=question,
        approve_writes=approve_writes,
        status=status,
        findings=findings,
        trace=trace,
        iterations=len(trace),
        input_tokens=in_tok,
        output_tokens=out_tok,
        model=MODEL,
        created_at=datetime.now(UTC),
    )
    db.add(run)
    db.commit()

    return {
        "run_id": run.id,
        "status": status,
        "findings": findings,
        "actions": [t for t in trace if t["tool"] == "create_maintenance_ticket"],
        "trace": trace,
        "usage": {"input_tokens": in_tok, "output_tokens": out_tok, "iterations": len(trace)},
    }
