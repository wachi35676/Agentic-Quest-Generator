"""Global configuration for the Agentic Quest Generator."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    # Ollama settings
    ollama_base_url: str = "http://localhost:11434"
    model_name: str = "phi4:14b"
    default_temperature: float = 0.7
    structured_temperature: float = 0.3  # For scoring, planning, structured output
    max_tokens: int = 2048
    llm_timeout: int = 120  # seconds
    llm_max_retries: int = 3

    # Agent settings
    react_max_steps: int = 12
    reflection_max_rounds: int = 3
    tot_branching: int = 3
    tot_budget: int = 24
    critic_max_rounds: int = 3
    plan_max_steps: int = 8
    plan_max_replans: int = 1
    json_repair_max_attempts: int = 3

    # Output directories
    generated_quests_dir: str = "quests/generated"
    traces_dir: str = "tracing/traces"
    eval_results_dir: str = "evaluation/results"

    # World zones — fixed vocabulary to constrain LLM output
    world_zones: tuple = (
        "village",
        "dark_forest",
        "mountain_pass",
        "ancient_ruins",
        "swamp",
        "castle",
        "cave_system",
        "marketplace",
        "graveyard",
        "river_crossing",
        "abandoned_mine",
        "tower",
    )


# Global config instance
CONFIG = Config()
