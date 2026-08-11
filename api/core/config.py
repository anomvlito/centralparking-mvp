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


@dataclass(frozen=True)
class VehicleFilterSettings:
    """Filtro de vehículo (YOLOX-Tiny/ONNX) previo al pipeline ALPR.

    Mismo patrón de rollout seguro que ``DirectionSettings`` (ver ADR-004):
    apagado por defecto y, al habilitarse, en modo sombra (audita, no
    descarta) hasta una activación deliberada posterior.

    conf_threshold=0.18: bajado desde 0.20 el 2026-08-11 (ver ADR-004, "Fix
    2026-08-11") — el 0.20 original se calibró contra 143 imágenes con
    vehículo confirmado + 535 sin detección del 2026-08-06 (con YOLOX-Tiny,
    los únicos descartes en ese momento fueron escenas nocturnas
    confirmadas sin vehículo, no autos reales perdidos), pero con más
    tiempo en producción activa se ajustó un poco más abajo para reducir el
    margen de falsos negativos.
    """

    enabled: bool = False
    shadow_mode: bool = True
    conf_threshold: float = 0.18

    def __post_init__(self) -> None:
        if not 0 < self.conf_threshold < 1:
            raise ValueError(
                "VEHICLE_FILTER_CONF_THRESH debe estar en el rango (0, 1)"
            )
        if not self.enabled and not self.shadow_mode:
            raise ValueError(
                "VEHICLE_FILTER_SHADOW_MODE debe ser true cuando "
                "VEHICLE_FILTER_ENABLED es false"
            )

    @classmethod
    def from_env(
        cls, environ: Mapping[str, str] | None = None
    ) -> "VehicleFilterSettings":
        env = os.environ if environ is None else environ
        enabled = _as_bool(
            env.get("VEHICLE_FILTER_ENABLED", "false"), "VEHICLE_FILTER_ENABLED"
        )
        if not enabled:
            return cls()
        shadow_mode = _as_bool(
            env.get("VEHICLE_FILTER_SHADOW_MODE", "true"),
            "VEHICLE_FILTER_SHADOW_MODE",
        )
        return cls(
            enabled=enabled,
            shadow_mode=shadow_mode,
            conf_threshold=float(
                env.get("VEHICLE_FILTER_CONF_THRESH", "0.18")
            ),
        )

    @property
    def mode(self) -> str:
        if not self.enabled:
            return "disabled"
        return "shadow" if self.shadow_mode else "active"


VEHICLE_FILTER_SETTINGS = VehicleFilterSettings.from_env()


@dataclass(frozen=True)
class SightingConsolidationSettings:
    """Consolidación difusa de avistamientos (ver ADR-005).

    Mismo patrón de rollout seguro que ``DirectionSettings``/
    ``VehicleFilterSettings``: apagado por defecto y, al habilitarse, en modo
    sombra (audita qué agruparía, no marca nada como DISMISSED) hasta una
    activación deliberada posterior. Nunca borra imágenes ni sobrescribe la
    patente original — solo agrega interpretación (match_status), igual que
    ``dismiss_detection_event`` y el resto de la conciliación existente.

    Opera sobre las lecturas crudas de ``staging_detections`` (no sobre el
    ``combined_score`` ya promovido a ``detection_log``): con datos reales
    (2026-08-10, PCYD65 leído mal 7 veces) el ``combined_score`` de una
    lectura incorrecta (PCYD55) superó al de la correcta (PCYD65) por 0.0002
    — ruido, no señal. ``min_confidence`` filtra por la confianza cruda del
    OCR antes de votar, y la patente ganadora de un grupo es la que más
    veces se repite igual entre las lecturas que pasan el filtro (desempate
    por confianza promedio) — no la de mayor confianza individual.

    ``archive_discarded_images`` (ver ADR-006) es un flag aparte, solo
    relevante cuando ``shadow_mode=False``: si está activo, la imagen de
    cada lectura recién marcada ``DISMISSED`` se mueve —nunca se borra— de
    ``/ftp/historico/{fecha}`` a ``/ftp/descartadas/{fecha}``. Apagado por
    defecto incluso con la consolidación ya activa en producción.

    ``max_distance`` por defecto es 2 desde ADR-008 (antes 1, ver ADR-005):
    con datos reales de un día completo de producción, ampliarlo a 2
    resolvió 15 casos adicionales el 2026-08-11 sin ninguna señal del
    riesgo que ADR-005 consideraba (fusión de dos autos reales ya
    identificados por separado con confianza independiente).
    """

    enabled: bool = False
    shadow_mode: bool = True
    max_distance: int = 2
    window_seconds: int = 90
    min_confidence: float = 0.90
    archive_discarded_images: bool = False

    def __post_init__(self) -> None:
        if self.max_distance not in {0, 1, 2}:
            raise ValueError("SIGHTING_CONSOLIDATION_MAX_DISTANCE debe estar entre 0 y 2")
        if not 0 < self.window_seconds <= 600:
            raise ValueError(
                "SIGHTING_CONSOLIDATION_WINDOW_SECONDS debe estar en el rango (0, 600]"
            )
        if not 0 < self.min_confidence < 1:
            raise ValueError(
                "SIGHTING_CONSOLIDATION_MIN_CONFIDENCE debe estar en el rango (0, 1)"
            )
        if not self.enabled and not self.shadow_mode:
            raise ValueError(
                "SIGHTING_CONSOLIDATION_SHADOW_MODE debe ser true cuando "
                "SIGHTING_CONSOLIDATION_ENABLED es false"
            )

    @classmethod
    def from_env(
        cls, environ: Mapping[str, str] | None = None
    ) -> "SightingConsolidationSettings":
        env = os.environ if environ is None else environ
        enabled = _as_bool(
            env.get("SIGHTING_CONSOLIDATION_ENABLED", "false"),
            "SIGHTING_CONSOLIDATION_ENABLED",
        )
        if not enabled:
            return cls()
        shadow_mode = _as_bool(
            env.get("SIGHTING_CONSOLIDATION_SHADOW_MODE", "true"),
            "SIGHTING_CONSOLIDATION_SHADOW_MODE",
        )
        return cls(
            enabled=enabled,
            shadow_mode=shadow_mode,
            max_distance=int(env.get("SIGHTING_CONSOLIDATION_MAX_DISTANCE", "2")),
            min_confidence=float(
                env.get("SIGHTING_CONSOLIDATION_MIN_CONFIDENCE", "0.90")
            ),
            window_seconds=int(env.get("SIGHTING_CONSOLIDATION_WINDOW_SECONDS", "90")),
            archive_discarded_images=_as_bool(
                env.get("SIGHTING_CONSOLIDATION_ARCHIVE_ENABLED", "false"),
                "SIGHTING_CONSOLIDATION_ARCHIVE_ENABLED",
            ),
        )

    @property
    def mode(self) -> str:
        if not self.enabled:
            return "disabled"
        return "shadow" if self.shadow_mode else "active"


SIGHTING_CONSOLIDATION_SETTINGS = SightingConsolidationSettings.from_env()
