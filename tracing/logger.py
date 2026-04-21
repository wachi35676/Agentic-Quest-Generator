"""JSONL trace logger for recording all agent reasoning steps.

Every LLM call, parsing attempt, validation check, and decision
is logged for research analysis and pattern comparison.
"""

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from config import CONFIG


@dataclass
class TraceEntry:
    """A single trace log entry."""
    timestamp: float
    trace_id: str
    task_id: str
    pattern: str
    step: int
    step_type: str  # "llm_call" | "parse" | "validate" | "decision" | "error" | "repair"
    prompt: str = ""
    response: str = ""
    parsed_json: dict | None = None
    parse_success: bool = True
    duration_ms: float = 0.0
    tokens_estimate: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class TraceLogger:
    """Logs agent reasoning traces to JSONL files."""

    def __init__(self, task_id: str, pattern: str, trace_id: str = None):
        self.task_id = task_id
        self.pattern = pattern
        self.trace_id = trace_id or f"tr_{uuid.uuid4().hex[:12]}"
        self.step_counter = 0
        self.entries: list[TraceEntry] = []

        # Ensure output directory exists
        os.makedirs(CONFIG.traces_dir, exist_ok=True)
        self.filepath = os.path.join(
            CONFIG.traces_dir,
            f"{self.trace_id}_{pattern}_{task_id}.jsonl"
        )

    def log(
        self,
        step_type: str,
        prompt: str = "",
        response: str = "",
        parsed_json: dict = None,
        parse_success: bool = True,
        duration_ms: float = 0.0,
        tokens_estimate: dict = None,
        metadata: dict = None,
    ) -> TraceEntry:
        """Log a trace entry and write it to the JSONL file."""
        self.step_counter += 1

        entry = TraceEntry(
            timestamp=time.time(),
            trace_id=self.trace_id,
            task_id=self.task_id,
            pattern=self.pattern,
            step=self.step_counter,
            step_type=step_type,
            prompt=prompt,
            response=response,
            parsed_json=parsed_json,
            parse_success=parse_success,
            duration_ms=duration_ms,
            tokens_estimate=tokens_estimate or {},
            metadata=metadata or {},
        )

        self.entries.append(entry)
        self._write_entry(entry)
        return entry

    def _write_entry(self, entry: TraceEntry):
        """Append a single entry to the JSONL file."""
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), default=str) + "\n")

    def get_stats(self) -> dict:
        """Get summary statistics for this trace."""
        llm_calls = [e for e in self.entries if e.step_type == "llm_call"]
        total_duration = sum(e.duration_ms for e in llm_calls)
        total_input_tokens = sum(e.tokens_estimate.get("input", 0) for e in llm_calls)
        total_output_tokens = sum(e.tokens_estimate.get("output", 0) for e in llm_calls)
        repairs = [e for e in self.entries if e.step_type == "repair"]
        errors = [e for e in self.entries if e.step_type == "error"]

        return {
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "pattern": self.pattern,
            "total_steps": self.step_counter,
            "llm_calls": len(llm_calls),
            "total_duration_ms": total_duration,
            "total_duration_seconds": total_duration / 1000,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "repair_attempts": len(repairs),
            "errors": len(errors),
        }
