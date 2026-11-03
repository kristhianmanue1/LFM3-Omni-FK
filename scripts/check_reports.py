#!/usr/bin/env python3
"""Gate estructural de reportes de dos capas (ADR-016, ADR-022).

Comprueba **forma**, nunca honestidad. Que un reporte pase este gate no
prueba que su evidencia sea cierta, que la ronda adversarial se ejecutara ni
que el trabajo esté hecho: prueba que el reporte está completo y que su hash
reproduce. La verificación de que una regla se cumplió de verdad sigue fuera
del alcance de Skevi (`project-manifest.yaml` §no_ofrece).

Qué se valida de la capa técnica: fence ```text presente; claves obligatorias
del bloque de trazabilidad y del reporte; polaridad cerrada sobre las claves;
`STATE` y `DECISION` dentro de su conjunto; al menos una línea de EVIDENCE con
la forma `- <qué> -> <resultado>`; marca válida cuando el último segmento es
una sola palabra; y `report_sha256` reproducible en forma canónica.

Marcas y transición (ADR-005): el validador acepta la línea **con marca y sin
ella**. Una línea cuyo último segmento tiene varias palabras es prosa sin
marca y pasa; una de una sola palabra ocupa el lugar de la marca y debe ser
`pass`, `fail` o `inconclusive` — así se atrapan `passed`, `ok` o `addressed`
sin romper la transición.

Fail-closed (ADR-006): sin clave `reports` en skevi-gate.json no comprueba
nada — inactivo, nunca error; clave presente con tipo inválido sí es error.

Uso:
  python3 scripts/check_reports.py [--root DIR]
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_NAME = "skevi-gate.json"
CONFIG_KEY = "reports"

# Capa técnica de ADR-016: las obligatorias son las que ese ADR enumera.
# `session` es opcional por el propio ADR y `DECISION` la exige `04` §5.2 para
# una ronda adversarial (no para un reporte de fase), de ahí que sea opcional
# aquí. `OPERATIONS`, `AUTHORITY` y `RISK` **no tienen fuente normativa**: son
# práctica heredada de los registros vigentes. Se admiten para no rechazar
# esos registros, y esa ausencia de fuente está declarada en ADR-022 como
# límite conocido — una clave sin regla que la respalde no se convierte en
# regla por estar en esta lista (AGENTS.md §Convenciones de edición).
REQUIRED_KEYS = {
    "id", "date", "time_utc", "head_sha", "model",
    "STATE", "GATE", "PENDING", "report_sha256",
}
OPTIONAL_KEYS = {"session", "DECISION", "OPERATIONS", "AUTHORITY", "RISK"}
MARKS = {"pass", "fail", "inconclusive"}
STATES = {"OK", "PARTIAL", "BLOCKED"}
DECISIONS = {"proceed", "fix-and-retry", "escalate"}

# Cualquier bloque cercado, no sólo ```text: una capa técnica en un fence
# liso no puede escapar al gate. La capa se ancla en `report_sha256`, que
# es lo que ADR-016 hace obligatorio, no en el lenguaje del fence.
FENCE_RE = re.compile(r"```[A-Za-z0-9_+-]*\n(.*?)\n```", re.S)
HASH_KEY = "report_sha256"
KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}Z$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class _ConfigError(ValueError):
    """Diagnóstico con campos conocidos, nunca payload del usuario (ADR-007)."""


def _is_hash_line(line: str) -> bool:
    """La línea que se excluye del canon es la de la clave exacta, no la de
    cualquier clave con ese prefijo (`report_sha256_prev` no se excluye)."""
    match = KEY_RE.match(line)
    return match is not None and match.group(1) == HASH_KEY


def _first_token(value: str) -> str:
    return value.split("(")[0].split(";")[0].strip().split(" ")[0]


def check_report(relative: str, text: str) -> list[str]:
    """Fallos de forma de un reporte. Lista vacía = capas técnicas válidas.

    Un archivo puede llevar más de una capa técnica (dos emisiones en el
    mismo registro): se validan todas, no sólo la primera. Un fence ```text
    que no declara `report_sha256` es salida de comando transcrita, no una
    capa técnica, y se ignora — el gate ancla la capa, no todo bloque
    preformateado.
    """
    layers = [
        m.group(1) for m in FENCE_RE.finditer(text)
        if any(l.startswith(HASH_KEY) for l in m.group(1).split("\n"))
    ]
    if not layers:
        return [f"{relative}: sin capa técnica (ningún bloque declara {HASH_KEY})"]
    failures: list[str] = []
    for layer in layers:
        failures.extend(_check_layer(relative, layer, text))
    return failures


def _check_layer(relative: str, layer: str, text: str) -> list[str]:
    failures: list[str] = []
    lines = layer.split("\n")
    keys: dict[str, str] = {}
    evidence: list[str] = []
    in_evidence = False
    for line in lines:
        if line.strip() == "EVIDENCE":
            in_evidence = True
            continue
        match = KEY_RE.match(line)
        if match:
            in_evidence = False
            name = match.group(1)
            if name in keys:
                # Sin esto, la última repetición ganaba en silencio y
                # `STATE = BLOCKED` seguido de `STATE = OK` pasaba el gate.
                failures.append(f"{relative}: clave duplicada en la capa: {name}")
            keys[name] = match.group(2).strip()
        elif in_evidence and line.strip():
            evidence.append(line)

    missing = sorted(REQUIRED_KEYS - set(keys))
    for key in missing:
        failures.append(f"{relative}: falta la clave obligatoria {key}")
    for key in sorted(set(keys) - REQUIRED_KEYS - OPTIONAL_KEYS):
        failures.append(f"{relative}: clave desconocida en la capa técnica: {key}")

    if "STATE" in keys and _first_token(keys["STATE"]) not in STATES:
        failures.append(
            f"{relative}: STATE debe empezar por uno de "
            f"{', '.join(sorted(STATES))}"
        )
    if "DECISION" in keys and _first_token(keys["DECISION"]) not in DECISIONS:
        failures.append(
            f"{relative}: DECISION debe empezar por uno de "
            f"{', '.join(sorted(DECISIONS))}"
        )
    if "date" in keys and not DATE_RE.match(keys["date"]):
        failures.append(f"{relative}: date debe ser AAAA-MM-DD")
    if "time_utc" in keys and not TIME_RE.match(keys["time_utc"]):
        failures.append(f"{relative}: time_utc debe ser HH:MM:SSZ")
    if "head_sha" in keys and not SHA1_RE.match(keys["head_sha"]):
        failures.append(f"{relative}: head_sha debe ser 40 hexadecimales")

    if not any(l.strip() == "EVIDENCE" for l in lines):
        failures.append(f"{relative}: sin sección EVIDENCE")
    elif not evidence:
        failures.append(f"{relative}: EVIDENCE sin ninguna línea")
    for line in evidence:
        body = line.strip()
        if not body.startswith("- "):
            failures.append(f"{relative}: línea de EVIDENCE sin viñeta: {body[:40]}")
            continue
        if "->" not in body:
            failures.append(
                f"{relative}: línea de EVIDENCE sin '->' que separe fuente de "
                f"resultado: {body[:40]}"
            )
            continue
        last = body.rsplit("->", 1)[1].strip()
        if last and " " not in last and last not in MARKS:
            failures.append(
                f"{relative}: marca inválida «{last}»; ADR-005 sólo admite "
                f"{', '.join(sorted(MARKS))} (o línea sin marca)"
            )

    if "report_sha256" in keys:
        declared = keys["report_sha256"]
        if not SHA256_RE.match(declared):
            failures.append(f"{relative}: report_sha256 debe ser 64 hexadecimales")
        else:
            canonical = "\n".join(l for l in lines if not _is_hash_line(l))
            actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if actual != declared:
                failures.append(
                    f"{relative}: report_sha256 no reproduce en forma canónica "
                    "(UTF-8, LF, sin newline final, excluida su propia línea)"
                )
    return failures


def _contained_path(root: Path, value: str) -> Path | None:
    """Resuelve `value` contra `root`; None si es absoluta, empieza por `~`
    o escapa de la raíz tras `.resolve()` (cierra también el symlink)."""
    if value.startswith("/") or value.startswith("~"):
        return None
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def load_config(root: Path) -> dict:
    path = root / CONFIG_NAME
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise _ConfigError(f"{CONFIG_NAME}: la raíz debe ser un objeto")
    return data


def declared_reports(root: Path) -> tuple[list[Path], set[str]] | None:
    """Archivos a comprobar y rutas exentas. None = inactivo (sin la clave)."""
    config = load_config(root)
    if CONFIG_KEY not in config:
        return None
    value = config[CONFIG_KEY]
    if not isinstance(value, dict):
        raise _ConfigError(
            f"{CONFIG_NAME}: «{CONFIG_KEY}» debe ser un objeto con «dir» "
            "y, opcionalmente, «exempt»"
        )
    unknown = sorted(set(value) - {"dir", "exempt"})
    if unknown:
        raise _ConfigError(
            f"{CONFIG_NAME}: «{CONFIG_KEY}» sólo admite «dir» y «exempt»"
        )
    directory = value.get("dir")
    if not isinstance(directory, str) or not directory.strip():
        raise _ConfigError(f"{CONFIG_NAME}: «{CONFIG_KEY}.dir» debe ser texto")
    # `dir` es entrada no confiable: misma frontera que `_safe_relative_paths`
    # en check_sizes.py. Sin esto, una ruta absoluta o un `..` hacían que el
    # gate leyera fuera del repo y reventara con traceback, filtrando rutas
    # del host — justo lo que ADR-007 prohíbe y este script promete no hacer.
    target = _contained_path(root, directory)
    if target is None:
        raise _ConfigError(
            f"{CONFIG_NAME}: «{CONFIG_KEY}.dir» debe ser una ruta relativa "
            "contenida en la raíz del proyecto"
        )
    if not target.is_dir():
        raise _ConfigError(
            f"{CONFIG_NAME}: «{CONFIG_KEY}.dir» declarado pero el directorio "
            f"no existe: {directory}"
        )
    exempt = value.get("exempt", [])
    if not isinstance(exempt, list) or not all(isinstance(e, str) for e in exempt):
        raise _ConfigError(
            f"{CONFIG_NAME}: «{CONFIG_KEY}.exempt» debe ser una lista de rutas"
        )
    # Symlinks fuera: misma frontera que check_sizes.py aplica al listado.
    files = sorted(
        p for p in target.glob("*.md") if not p.is_symlink()
    )
    return files, set(exempt)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = ROOT
    # La línea de comandos también es una frontera: se valida contra un
    # esquema cerrado y falla controlado (§2.4, ADR-007). Un IndexError o un
    # argumento ignorado en silencio serían los dos fallos que este mismo
    # script le reprocha al resto del corpus.
    if argv:
        if argv[0] != "--root" or len(argv) != 2:
            print("BLOQ — check_reports recibió argumentos inválidos")
            print("- uso: check_reports.py [--root DIR]")
            return 1
        root = Path(argv[1]).resolve()
        if not root.is_dir():
            print("BLOQ — check_reports no encontró la raíz indicada")
            print("- «--root» debe apuntar a un directorio existente")
            return 1

    try:
        declared = declared_reports(root)
    except _ConfigError as exc:
        print("BLOQ — check_reports encontró configuración inválida")
        print(f"- {exc}")
        return 1
    except json.JSONDecodeError as exc:
        print("BLOQ — check_reports encontró configuración inválida")
        print(f"- {CONFIG_NAME}: JSON inválido (línea {exc.lineno}, columna {exc.colno})")
        return 1
    except (OSError, UnicodeDecodeError):
        print("BLOQ — check_reports encontró configuración inválida")
        print(f"- {CONFIG_NAME}: no se pudo leer la configuración")
        return 1

    if declared is None:
        print(f"OK — inactivo: sin clave «{CONFIG_KEY}» en {CONFIG_NAME}")
        return 0

    files, exempt = declared
    failures: list[str] = []
    checked = 0
    skipped = 0
    for file in files:
        relative = file.relative_to(root).as_posix()
        if relative in exempt:
            skipped += 1
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            failures.append(f"{relative}: contenido no válido como UTF-8")
            continue
        except OSError:
            # Nunca volcar la excepción: puede llevar rutas del host (ADR-007).
            failures.append(f"{relative}: no se pudo leer el archivo")
            continue
        # docs/reviews/ también aloja prosa de cierre sin capa técnica: sólo
        # se validan los archivos que declaran una, y «declarar una» significa
        # tener `report_sha256`, no tener un fence ```text — un registro
        # trivial puede transcribir salida de comando (00-INDICE: «tarea
        # trivial: capa humana sola»).
        if HASH_KEY not in text:
            continue
        checked += 1
        failures.extend(check_report(relative, text))

    if failures:
        print("BLOQ — check_reports encontró incumplimientos")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(
        f"OK — {checked} reporte(s) con capa técnica verificada"
        + (f"; {skipped} exento(s)" if skipped else "")
    )
    return 0


# Compatibilidad de imports previos (SPEC-LANG REQ-L3): también se conservan
# los argumentos por nombre de comprobar_reporte. No son nombres nuevos.
def comprobar_reporte(relativo: str, texto: str) -> list[str]:
    return check_report(relative=relativo, text=texto)


cargar_config = load_config
reportes_declarados = declared_reports


if __name__ == "__main__":
    raise SystemExit(main())
