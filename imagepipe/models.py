"""Inputs and execution records shared by the image pipeline."""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class APIConfig(BaseModel):
    base_url: str = "https://api.openai.com"
    env_file: str = ".env"
    key_name: str = "OPENAI"
    request_timeout_seconds: float = 900
    max_reference_images: int = Field(default=16, gt=0, le=16)


class GenerationConfig(BaseModel):
    model: str = "gpt-image-2.6-sunburst"
    quality: Literal["low", "medium", "high", "xhigh", "max", "auto"] = "max"
    complexity: Literal["low", "medium", "high"] = "high"
    native_width: int = Field(default=1152, gt=0)
    native_height: int = Field(default=2048, gt=0)
    steps: int = Field(default=20, gt=0)
    width: int = Field(default=720, gt=0)
    height: int = Field(default=1280, gt=0)
    seed_base: int = 20261101


class SchedulerConfig(BaseModel):
    http_concurrency: int = Field(default=140, gt=0)
    max_active_jobs: int = Field(default=140, gt=0)
    images_per_minute: int = Field(default=105, gt=0)
    tokens_per_minute: int = Field(default=2_100_000, gt=0)
    estimated_tokens_per_image: int = Field(default=20_000, gt=0)
    poll_interval_seconds: float = Field(default=5, gt=0)
    max_attempts: int = Field(default=3, gt=0)


class ImageConfig(BaseModel):
    provider: Literal["gpt", "qwen", "codex"] = "gpt"
    api: APIConfig = Field(default_factory=APIConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    continuity: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def provider_defaults(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        for section in ("api", "generation", "scheduler"):
            if isinstance(data.get(section), BaseModel):
                data[section] = data[section].model_dump(exclude_unset=True)
        # Saved Qwen runs and older custom YAML files predate the provider field.
        if "provider" not in data and data.get("generation", {}).get("model", "").startswith("qwen"):
            data["provider"] = "qwen"
        if data.get("provider") == "qwen":
            defaults = {
                "api": {"base_url": "https://api.zlk7301.com", "key_name": "QWEN-IMAGE",
                        "request_timeout_seconds": 90, "max_reference_images": 10},
                "generation": {"model": "qwen-image-2.1"},
                "scheduler": {"http_concurrency": 16, "max_active_jobs": 64},
            }
            for section, fields in defaults.items():
                data[section] = {**fields, **data.get(section, {})}
        return data

    @model_validator(mode="after")
    def validate_gpt_size(self) -> "ImageConfig":
        if self.provider == "gpt":
            width, height = self.generation.native_width, self.generation.native_height
            if (width % 16 or height % 16 or max(width, height) > 3840
                    or max(width, height) > 3 * min(width, height)
                    or not 655360 <= width * height <= 8294400):
                raise ValueError("GPT Image size requires 16-pixel multiples, aspect ratio at most 3:1, "
                                 "maximum edge 3840 and 655360–8294400 pixels")
        return self


@dataclass
class ImageTask:
    asset_id: str
    mode: Literal["text", "edit", "reference"]
    prompt: str
    reference_ids: list[str]
    target_path: str
    seed: int


@dataclass
class CopyTask:
    asset_id: str
    source_path: str
    target_path: str


@dataclass
class ImagePlan:
    package_root: str
    tasks: list[ImageTask]
    copies: list[CopyTask]
