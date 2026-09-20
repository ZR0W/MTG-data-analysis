from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path("config/config.yaml")


@dataclass
class PathsConfig:
    raw_dir: Path
    processed_dir: Path


@dataclass
class IngestConfig:
    user_agent: str
    cache_ttl_hours: int
    bulk_types: list[str]


@dataclass
class PeriodGroupConfig:
    """How consecutive sets are grouped into analysis periods.

    per_set is the finest grain: one period per set, with breakpoints at each set's
    release date. rolling_sets groups `group_size` consecutive sets to smooth noise
    from small sets.
    """

    mode: str = "per_set"
    group_size: int = 5

    def __post_init__(self) -> None:
        if self.mode not in ("per_set", "rolling_sets"):
            raise ValueError(f"unknown period mode: {self.mode}")
        if self.group_size < 1:
            raise ValueError("group_size must be >= 1")


@dataclass
class Config:
    paths: PathsConfig
    ingest: IngestConfig
    set_type_exclude: list[str] = field(default_factory=list)
    periods: PeriodGroupConfig = field(default_factory=PeriodGroupConfig)


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> Config:
    raw = yaml.safe_load(Path(path).read_text())
    return Config(
        paths=PathsConfig(
            raw_dir=Path(raw["paths"]["raw_dir"]),
            processed_dir=Path(raw["paths"]["processed_dir"]),
        ),
        ingest=IngestConfig(**raw["ingest"]),
        set_type_exclude=list(raw.get("set_type_exclude", [])),
        periods=PeriodGroupConfig(**raw.get("periods", {})),
    )
