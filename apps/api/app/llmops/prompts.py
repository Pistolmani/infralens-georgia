from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from string import Template

import yaml


class PromptRegistryError(Exception):
    pass


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    model: str
    temperature: float
    output_schema: str
    template: str

    def render(self, **context: object) -> str:
        prepared = {
            key: value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            for key, value in context.items()
        }
        return Template(self.template).safe_substitute(prepared)


class PromptRegistry:
    def __init__(self, prompt_dir: Path) -> None:
        self._prompt_dir = prompt_dir
        self._prompts = self._load_prompts(prompt_dir)

    def get(self, name: str) -> Prompt:
        try:
            return self._prompts[name]
        except KeyError as exc:
            raise PromptRegistryError(f"Prompt '{name}' was not found in {self._prompt_dir}") from exc

    def _load_prompts(self, prompt_dir: Path) -> dict[str, Prompt]:
        if not prompt_dir.exists():
            raise PromptRegistryError(f"Prompt directory does not exist: {prompt_dir}")

        prompts: dict[str, Prompt] = {}
        for path in sorted(prompt_dir.glob("*.yaml")):
            prompt = _load_prompt(path)
            if prompt.name in prompts:
                raise PromptRegistryError(f"Duplicate prompt name '{prompt.name}' in {path}")
            prompts[prompt.name] = prompt

        if not prompts:
            raise PromptRegistryError(f"No prompt YAML files found in {prompt_dir}")

        return prompts


def _load_prompt(path: Path) -> Prompt:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise PromptRegistryError(f"Prompt file must contain a mapping: {path}")

    required = ("name", "version", "model", "temperature", "output_schema", "template")
    missing = [field for field in required if raw.get(field) in (None, "")]
    if missing:
        raise PromptRegistryError(f"Prompt file {path} is missing required field(s): {', '.join(missing)}")

    try:
        temperature = float(raw["temperature"])
    except (TypeError, ValueError) as exc:
        raise PromptRegistryError(f"Prompt file {path} has invalid temperature") from exc

    return Prompt(
        name=str(raw["name"]),
        version=str(raw["version"]),
        model=str(raw["model"]),
        temperature=temperature,
        output_schema=str(raw["output_schema"]),
        template=str(raw["template"]),
    )
