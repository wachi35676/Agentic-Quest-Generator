"""Ollama client using subprocess (matching agentic-assignment approach).

Calls `ollama run <model>` via subprocess. On WSL, auto-detects
and uses `ollama.exe` instead.
"""

import os
import time
import subprocess
from dataclasses import dataclass
from config import CONFIG


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    text: str
    duration_ms: float
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    success: bool = True
    error: str | None = None


def _detect_ollama_cmd() -> str:
    """Detect whether to use 'ollama' or 'ollama.exe' (for WSL)."""
    try:
        if os.path.exists("/proc/version"):
            with open("/proc/version") as f:
                if "microsoft" in f.read().lower():
                    return "ollama.exe"
    except Exception:
        pass
    return "ollama"


class OllamaClient:
    """Subprocess-based Ollama client.

    Calls `ollama run <model>` with the prompt piped to stdin.
    This matches the approach used in the agentic-assignment project.
    """

    def __init__(self, model: str = None):
        self.model = model or CONFIG.model_name
        self.ollama_cmd = _detect_ollama_cmd()

    def generate(
        self,
        prompt: str,
        system: str = None,
        temperature: float = None,
        max_tokens: int = None,
        timeout: int = None,
    ) -> LLMResponse:
        """Call Ollama via subprocess.

        Args:
            prompt: The user prompt to send.
            system: Optional system prompt (prepended to prompt).
            temperature: Not directly controllable via CLI, ignored.
            max_tokens: Not directly controllable via CLI, ignored.
            timeout: Subprocess timeout in seconds (default from config).

        Returns:
            LLMResponse with the generated text and metadata.
        """
        timeout = timeout or CONFIG.llm_timeout

        # Combine system prompt with user prompt if provided
        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{prompt}"

        last_error = None
        for attempt in range(CONFIG.llm_max_retries):
            start_time = time.time()
            try:
                p = subprocess.run(
                    [self.ollama_cmd, "run", self.model],
                    input=full_prompt.encode("utf-8"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=timeout,
                )
                duration_ms = (time.time() - start_time) * 1000
                out = p.stdout.decode("utf-8", errors="ignore").strip()

                if not out:
                    err = p.stderr.decode("utf-8", errors="ignore")
                    last_error = f"Ollama empty output. stderr={err[:250]}"
                    if attempt < CONFIG.llm_max_retries - 1:
                        time.sleep(0.5 * (attempt + 1))
                    continue

                return LLMResponse(
                    text=out,
                    duration_ms=duration_ms,
                    model=self.model,
                )

            except subprocess.TimeoutExpired:
                last_error = f"Ollama timed out after {timeout}s"
                if attempt < CONFIG.llm_max_retries - 1:
                    time.sleep(0.5 * (attempt + 1))

            except FileNotFoundError:
                return LLMResponse(
                    text="",
                    duration_ms=0,
                    model=self.model,
                    success=False,
                    error=f"'{self.ollama_cmd}' not found. Is Ollama installed?",
                )

            except Exception as e:
                last_error = str(e)
                if attempt < CONFIG.llm_max_retries - 1:
                    time.sleep(0.5 * (attempt + 1))

        return LLMResponse(
            text="",
            duration_ms=0,
            model=self.model,
            success=False,
            error=f"Failed after {CONFIG.llm_max_retries} attempts: {last_error}",
        )

    def check_connection(self) -> bool:
        """Check if Ollama is available and the model exists."""
        try:
            p = subprocess.run(
                [self.ollama_cmd, "list"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            out = p.stdout.decode("utf-8", errors="ignore")
            # Check if our model appears in the list
            return any(
                self.model in line
                for line in out.strip().split("\n")
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False
