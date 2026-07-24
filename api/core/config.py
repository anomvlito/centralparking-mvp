"""Configuración validada del clasificador vertical."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from typing import Mapping


def _as_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} debe ser booleano")


@dataclass(frozen=True)
class DirectionSettings:
    """Fuente única e inmutable para dirección.

    Las unidades son segundos, coordenadas ``center_y`` normalizadas y
    ``center_y/segundo``. El modo seguro por defecto está deshabilitado y,
    cuando se habilita, permanece en observación hasta una activación
    deliberada posterior.
    """

    enabled: bool = False
    observation_only: bool = True
    window_seconds: float = 15.0
    min_samples: int = 3
    max_history: int = 8
    min_displacement: float = 0.08
    min_slope_per_second: float = 0.01
    min_consistency: float = 0.67
    entry_sign: str = "positive"

    def __post_init__(self) -> None:
        if self.window_seconds <= 0:
            raise ValueError("DIRECTION_WINDOW_SEC debe ser mayor que 0")
        if not 3 <= self.min_samples <= 8:
            raise ValueError("DIRECTION_MIN_SAMPLES debe estar entre 3 y 8")
        if not self.min_samples <= self.max_history <= 8:
            raise ValueError(
                "DIRECTION_MAX_HISTORY debe estar entre MIN_SAMPLES y 8"
            )
        if not 0 < self.min_displacement <= 1:
            raise ValueError(
                "DIRECTION_MIN_DISPLACEMENT debe estar en el rango (0, 1]"
            )
        if self.min_slope_per_second <= 0:
            raise ValueError("DIRECTION_MIN_SLOPE debe ser mayor que 0")
        if not 0.5 < self.min_consistency <= 1:
            raise ValueError(
                "DIRECTION_MIN_CONSISTENCY debe estar en el rango (0.5, 1]"
            )
        if self.entry_sign not in {"positive", "negative"}:
            raise ValueError(
                "DIRECTION_ENTRY_SIGN debe ser 'positive' o 'negative'"
            )
        if not self.enabled and not self.observation_only:
            raise ValueError(
                "DIRECTION_OBSERVATION_ONLY debe ser true cuando "
                "DIRECTION_ENABLED es false"
            )

    @classmethod
    def from_env(
        cls, environ: Mapping[str, str] | None = None
    ) -> "DirectionSettings":
        env = os.environ if environ is None else environ
        enabled = _as_bool(env.get("DIRECTION_ENABLED", "false"), "DIRECTION_ENABLED")
        if not enabled:
            # Un conjunto viejo o incompleto de variables no puede activar ni
            # impedir el arranque de una función explícitamente deshabilitada.
            return cls()
        observation_only = _as_bool(
            env.get("DIRECTION_OBSERVATION_ONLY", "true"),
            "DIRECTION_OBSERVATION_ONLY",
        )
        return cls(
            enabled=enabled,
            observation_only=observation_only,
            window_seconds=float(env.get("DIRECTION_WINDOW_SEC", "15")),
            min_samples=int(env.get("DIRECTION_MIN_SAMPLES", "3")),
            max_history=int(env.get("DIRECTION_MAX_HISTORY", "8")),
            min_displacement=float(
                env.get("DIRECTION_MIN_DISPLACEMENT", "0.08")
            ),
            min_slope_per_second=float(
                env.get("DIRECTION_MIN_SLOPE", "0.01")
            ),
            min_consistency=float(
                env.get("DIRECTION_MIN_CONSISTENCY", "0.67")
            ),
            entry_sign=env.get("DIRECTION_ENTRY_SIGN", "positive").lower(),
        )

    @property
    def mode(self) -> str:
        if not self.enabled:
            return "disabled"
        return "observation_only" if self.observation_only else "active"

    @property
    def version(self) -> str:
        canonical = json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":")
        ).encode()
        return f"sha256:{hashlib.sha256(canonical).hexdigest()[:16]}"

    def public_dict(self) -> dict:
        return {**asdict(self), "mode": self.mode, "version": self.version}


DIRECTION_SETTINGS = DirectionSettings.from_env()
