#!/usr/bin/env python3
"""Gate de estructura y tamaños de Skevi.

La polaridad es cerrada: todo archivo de texto queda sujeto a un límite salvo
una exención explícita. También falla si falta un archivo canónico o aparece
Markdown operativo suelto en la raíz.

Copiable sin edición a un proyecto adoptante: si su estructura de archivos
canónicos, límites o exenciones difiere de la de Skevi, declara
`skevi-gate.json` en la raíz en vez de editar este script (ADR-006). Desde
gate/v9 (ADR-039) la unidad de copia son los cuatro scripts de scripts/
juntos: la validación de manifiestos vive en check_templates.py y este
script la delega por import.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import check_templates


# Identidad de esta copia del gate (ADR-027). Skevi no puede avisar a un
# adoptante de que existe una versión nueva: el manifiesto le prohíbe observar
# proyectos ajenos. Lo que sí puede es que la copia diga quién es y cuántos
# días tiene, en la salida que el adoptante ya ejecuta. Al cambiar el
# comportamiento del gate se sube GATE_VERSION y se pone la fecha del cambio.
GATE_VERSION = "gate/v13"
GATE_GENERATED_AT = "2026-10-29"
GATE_STALE_AFTER_DAYS = 90

ROOT = Path(__file__).resolve().parent.parent
ROOT_MARKDOWN = {"AGENTS.md", "CLAUDE.md", "README.md"}
REQUIRED = {
    "AGENTS.md",
    "README.md",
    "docs/estandar-diseno-software-github.md",
    "docs/ai-agent-guide/00-INDICE.md",
    "docs/ai-agent-guide/01-analisis-y-requerimientos.md",
    "docs/ai-agent-guide/02-specs-adr-contratos.md",
    "docs/ai-agent-guide/03-cascaron-proyecto.md",
    "docs/ai-agent-guide/04-ejecucion-y-verificacion.md",
    "scripts/check_sizes.py",
    "templates/skevi/registro-contexto.md",
    "templates/skevi/plan-de-implementacion.md",
    "templates/skevi/usage-guide.md",
    "templates/skevi/architecture-overview.md",
}
SKIP_DIRS = {
    ".an-kla",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "data",
    "datos",
    "dist",
    "generated",
    "node_modules",
    "vendor",
}
EXEMPT_SUFFIXES = {
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".lock",
    ".pdf",
    ".png",
    ".pyc",
    ".svg",
    ".tar",
    ".woff",
    ".woff2",
    ".zip",
}
EXEMPT_PATHS: set[str] = set()
# Exención por nombre exacto de archivo (ADR-030): basura que Git no
# versiona, sin declarar su ruta una a una.
EXEMPT_NAMES: set[str] = set()
# Presupuesto de la ruta de lectura obligatoria (ADR-021). Vacío =
# inactivo: §3.4 acota cada archivo por separado, y hasta ADR-021
# nada acotaba la suma que un ejecutor debe leer antes de actuar.
READING_PATH: dict = {}
# Ocupación medida en la última corrida; None si el presupuesto está inactivo.
READING_PATH_OBSERVED: int | None = None
LIMITS = {
    "AGENTS.md": 200,
    "README.md": 300,
}
DEFAULT_LIMIT = 800
TEMPLATE_PREFIX = "templates/"
TEMPLATE_LIMIT = 300

# Manifiesto de plantillas (#28 D1 + enmiendas T09, ADR-020): el esquema
# cerrado, el listado exacto y los digests vigentes se validan en
# check_templates.py, dueño del dominio desde gate/v9 (ADR-039); este
# gate delega por import. Los alias preservan la superficie que tests y
# adoptantes importan desde aquí: mover el hogar no es romper la API.
TEMPLATE_MANIFEST_NAME = check_templates.TEMPLATE_MANIFEST_NAME
TEMPLATE_MANIFEST_SCHEMA = check_templates.TEMPLATE_MANIFEST_SCHEMA
SCRIPT_MANIFEST_SCHEMA = check_templates.SCRIPT_MANIFEST_SCHEMA
CORPUS_MANIFEST_SCHEMA = check_templates.CORPUS_MANIFEST_SCHEMA
check_template_manifest = check_templates.check_template_manifest
check_corpus_manifest = check_templates.check_corpus_manifest

# Instantánea de los valores de Skevi, congelada al importar el módulo, antes
# de que ninguna configuración de proyecto pueda tocarlos. `main()` restaura
# desde aquí en cada invocación: si alguna vez se llama dos veces en el mismo
# proceso (tests, un orquestador), la segunda no hereda la config de la
# primera por acumulación silenciosa.
_SKEVI_DEFAULTS = {
    "ROOT_MARKDOWN": frozenset(ROOT_MARKDOWN),
    "REQUIRED": frozenset(REQUIRED),
    "SKIP_DIRS": frozenset(SKIP_DIRS),
    "EXEMPT_PATHS": frozenset(EXEMPT_PATHS),
    "EXEMPT_NAMES": frozenset(EXEMPT_NAMES),
    "READING_PATH": dict(READING_PATH),
    "LIMITS": dict(LIMITS),
    "DEFAULT_LIMIT": DEFAULT_LIMIT,
}


def reset_to_skevi_defaults() -> None:
    """Restaura el estado de módulo a los valores de Skevi, antes de leer
    la configuración del proyecto. Ver `_SKEVI_DEFAULTS`."""
    global DEFAULT_LIMIT
    ROOT_MARKDOWN.clear()
    ROOT_MARKDOWN.update(_SKEVI_DEFAULTS["ROOT_MARKDOWN"])
    REQUIRED.clear()
    REQUIRED.update(_SKEVI_DEFAULTS["REQUIRED"])
    SKIP_DIRS.clear()
    SKIP_DIRS.update(_SKEVI_DEFAULTS["SKIP_DIRS"])
    EXEMPT_PATHS.clear()
    EXEMPT_PATHS.update(_SKEVI_DEFAULTS["EXEMPT_PATHS"])
    EXEMPT_NAMES.clear()
    EXEMPT_NAMES.update(_SKEVI_DEFAULTS["EXEMPT_NAMES"])
    READING_PATH.clear()
    READING_PATH.update(_SKEVI_DEFAULTS["READING_PATH"])
    LIMITS.clear()
    LIMITS.update(_SKEVI_DEFAULTS["LIMITS"])
    DEFAULT_LIMIT = _SKEVI_DEFAULTS["DEFAULT_LIMIT"]


# Configuración del proyecto adoptante. Los valores de arriba son los de Skevi
# sobre sí mismo; un proyecto que adopta el gate declara los suyos aquí, por
# escrito, conforme a §3.4 del estándar: heredar el valor por defecto sin
# decidirlo es aceptable, cambiarlo en silencio no lo es.
CONFIG_NAME = "skevi-gate.json"
CONFIG_KEYS = {
    "limits", "default_limit", "exempt_paths", "exempt_names", "required",
    "skip_dirs", "root_markdown", "plans", "reading_path", "reports",
}
# "plans" la consume scripts/check_plans.py (gate estructural de planes,
# ADR-014) y "reports" scripts/check_reports.py (gate de reportes de dos
# capas, ADR-022): misma config, polaridad cerrada compartida — ausente =
# inactivo. Un check_sizes desactualizado las rechaza con BLOQ en vez de
# ignorarlas, que es el efecto buscado.


class _ConfigError(ValueError):
    """Diagnóstico interno con constantes/campos conocidos, nunca payload.

    Procedencia: ADR-007 y SPEC-AUD-02. Conserva compatibilidad con quienes
    capturan ValueError; sólo esta variante admite mostrar su mensaje.
    """


def _resolve_project_path(value: object) -> Path | None:
    """Resuelve `value` contra ROOT; None si no es texto, es absoluta,
    empieza por `~` o escapa de ROOT. No exige que el archivo exista: los
    elementos de `required` se declaran antes de comprobarse."""
    if not isinstance(value, str) or value.startswith("/") or value.startswith("~"):
        return None
    candidate = (ROOT / value).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        return None
    return candidate


def _safe_relative_paths(field: str, values: object) -> list[str]:
    """Valida una lista de rutas de `skevi-gate.json`: relativas, dentro de
    ROOT. Rechaza absolutas y saltos hacia fuera (`../..`), con la misma
    frontera que `_resolve_registry_path` aplica al bloque de registro."""
    if not isinstance(values, list):
        raise _ConfigError(f"{CONFIG_NAME}: «{field}» debe ser una lista de rutas")
    safe: list[str] = []
    for value in values:
        if _resolve_project_path(value) is None:
            raise _ConfigError(
                f"{CONFIG_NAME}: «{field}» tiene una ruta inválida "
                "(debe ser relativa a la raíz del proyecto)"
            )
        safe.append(value)
    return safe


def _string_list(field: str, values: object) -> list[str]:
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise _ConfigError(f"{CONFIG_NAME}: «{field}» debe ser una lista de texto")
    return values


def _exempt_names(field: str, values: object) -> list[str]:
    """Nombre de archivo sin ruta (ADR-030); para rutas, «exempt_paths»."""
    names = _string_list(field, values)
    if any(not n or n in {".", ".."} or "/" in n or "\\" in n for n in names):
        raise _ConfigError(
            f"{CONFIG_NAME}: «{field}» sólo admite nombres de archivo sin "
            "ruta; para exentar una ruta usa «exempt_paths»"
        )
    return names


def _reading_path(values: object) -> dict:
    """Valida la clave `reading_path` de `skevi-gate.json` (ADR-021).

    Polaridad cerrada como el resto de la config: subclave desconocida,
    límite no entero o ruta que escapa la raíz fallan en vez de ignorarse.
    Un typo no puede apagar el presupuesto en silencio — mismo criterio que
    `plans` en scripts/check_plans.py.
    """
    if not isinstance(values, dict):
        raise _ConfigError(
            f"{CONFIG_NAME}: «reading_path» debe ser un objeto con "
            "«limit» y «files»"
        )
    unknown = sorted(set(values) - {"limit", "files", "worst_case_of"})
    if unknown:
        raise _ConfigError(
            f"{CONFIG_NAME}: «reading_path» sólo admite «limit», «files» "
            "y «worst_case_of»"
        )
    if "limit" not in values or "files" not in values:
        raise _ConfigError(
            f"{CONFIG_NAME}: «reading_path» exige «limit» y «files»"
        )
    limit = values["limit"]
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise _ConfigError(
            f"{CONFIG_NAME}: «reading_path.limit» debe ser un entero positivo"
        )
    files = _safe_relative_paths("reading_path.files", values["files"])
    if not files:
        raise _ConfigError(
            f"{CONFIG_NAME}: «reading_path.files» no puede estar vacía"
        )
    resultado = {"limit": limit, "files": files}
    if "worst_case_of" in values:
        alternativas = _safe_relative_paths(
            "reading_path.worst_case_of", values["worst_case_of"]
        )
        if not alternativas:
            raise _ConfigError(
                f"{CONFIG_NAME}: «reading_path.worst_case_of» no puede "
                "estar vacía"
            )
        resultado["worst_case_of"] = alternativas
    return resultado


def load_config() -> dict:
    """Lee `skevi-gate.json` de la raíz si existe. Ausente = valores de Skevi.

    Polaridad cerrada: una clave desconocida falla en vez de ignorarse, para
    que un error de escritura sea detectable y no silencioso.
    """
    path = ROOT / CONFIG_NAME
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise _ConfigError(f"{CONFIG_NAME}: la raíz debe ser un objeto")
    unknown = sorted(set(data) - CONFIG_KEYS)
    if unknown:
        raise _ConfigError(
            f"{CONFIG_NAME}: claves desconocidas; permitidas: "
            + ", ".join(sorted(CONFIG_KEYS))
        )
    return data


def apply_config(config: dict) -> None:
    """Aplica la configuración del proyecto sobre los valores de Skevi.

    Dos semánticas distintas, a propósito. `limits`, `exempt_paths`,
    `skip_dirs` y `root_markdown` se **añaden** a los de Skevi: un proyecto
    que declara un límite propio no pierde los de `AGENTS.md`/`README.md`, y
    una exención no borra las que ya existían. `required` en cambio
    **reemplaza**: la lista de archivos canónicos de Skevi
    (`docs/estandar-diseno-software-github.md`, la guía en inglés, las
    plantillas) sólo tiene sentido dentro de este repositorio; un proyecto
    adoptante con otra estructura de directorios — como `an-kla-memory`, que
    usa `docs/architecture/`— declara la suya.

    Entradas mal tipadas producen `ValueError`: main las convierte en BLOQ,
    sin traceback (ADR-007).
    """
    global DEFAULT_LIMIT
    if "limits" in config:
        raw = config["limits"]
        if not isinstance(raw, dict):
            raise _ConfigError(f"{CONFIG_NAME}: «limits» debe ser un objeto")
        for name, value in raw.items():
            if not isinstance(value, int) or isinstance(value, bool):
                raise _ConfigError(
                    f"{CONFIG_NAME}: cada valor de «limits» debe ser un entero"
                )
            LIMITS[str(name)] = value
    if "default_limit" in config:
        value = config["default_limit"]
        if not isinstance(value, int) or isinstance(value, bool):
            raise _ConfigError(f"{CONFIG_NAME}: «default_limit» debe ser un entero")
        DEFAULT_LIMIT = value
    if "exempt_paths" in config:
        EXEMPT_PATHS.update(_safe_relative_paths("exempt_paths", config["exempt_paths"]))
    if "exempt_names" in config:
        EXEMPT_NAMES.update(_exempt_names("exempt_names", config["exempt_names"]))
    if "required" in config:
        REQUIRED.clear()
        REQUIRED.update(_safe_relative_paths("required", config["required"]))
    if "skip_dirs" in config:
        SKIP_DIRS.update(_string_list("skip_dirs", config["skip_dirs"]))
    if "root_markdown" in config:
        ROOT_MARKDOWN.update(_string_list("root_markdown", config["root_markdown"]))
    if "reading_path" in config:
        READING_PATH.update(_reading_path(config["reading_path"]))


def limit_for(name: str) -> int:
    if name in LIMITS:
        return LIMITS[name]
    if name.startswith(TEMPLATE_PREFIX):
        return TEMPLATE_LIMIT
    return DEFAULT_LIMIT


REGISTRY_START_RE = re.compile(r"^<!--\s*skevi:registry:start\s*-->$", re.IGNORECASE)
REGISTRY_END_RE = re.compile(r"^<!--\s*skevi:registry:end\s*-->$", re.IGNORECASE)
REGISTRY_HOSTS = {"AGENTS.md", "CLAUDE.md"}


def _resolve_registry_path(value: str) -> Path | None:
    """Resuelve `value` contra ROOT; None si es absoluta o escapa de ROOT."""
    if value.startswith("/") or value.startswith("~"):
        return None
    candidate = (ROOT / value).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        return None
    return candidate


def check_registry_block(relative: Path, text: str) -> list[str]:
    """Valida el bloque delimitado de §3.5 si el archivo lo trae."""
    if relative.name not in REGISTRY_HOSTS:
        return []

    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if REGISTRY_START_RE.match(line.strip())]
    ends = [i for i, line in enumerate(lines) if REGISTRY_END_RE.match(line.strip())]

    if not starts and not ends:
        return []
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        return [f"{relative}: bloque skevi:registry con delimitadores desbalanceados"]

    failures: list[str] = []
    raw_body = [line.strip() for line in lines[starts[0] + 1 : ends[0]] if line.strip()]
    body = [line for line in raw_body if not line.startswith((";", "#"))]

    if not body or body[0] != "[skevi]":
        failures.append(f"{relative}: bloque skevi:registry sin sección [skevi]")
        entries = body
    else:
        entries = body[1:]
        if any(line == "[skevi]" for line in entries):
            failures.append(f"{relative}: bloque skevi:registry con sección [skevi] duplicada")
            entries = [line for line in entries if line != "[skevi]"]

    if not entries:
        failures.append(f"{relative}: bloque skevi:registry sin entradas")

    for line in entries:
        if "=" not in line:
            failures.append(f"{relative}: línea de registro inválida: {line!r}")
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not key or not value:
            failures.append(f"{relative}: línea de registro inválida: {line!r}")
            continue
        target = _resolve_registry_path(value)
        if target is None:
            failures.append(
                f"{relative}: skevi:registry.{key} usa ruta fuera de la raíz del "
                f"proyecto: {value}"
            )
        elif not target.is_file():
            failures.append(
                f"{relative}: skevi:registry.{key} apunta a ruta inexistente: {value}"
            )
    return failures


def discover() -> list[Path]:
    paths: list[Path] = []
    for path in ROOT.rglob("*"):
        # Los symlinks no se siguen: la frontera de raíz vale también para el
        # listado. Sin esto el gate medía y reportaba el tamaño de un archivo
        # ajeno al repositorio, y el nombre del enlace bastaba para inferirlo.
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in relative.parts[:-1]):
            continue
        paths.append(relative)
    return sorted(paths)


def count_text_lines(relative: Path) -> int | None:
    """None significa exención; los errores de lectura los reporta main.

    Procedencia: estándar §3.4 y ADR-007; una lectura fallida no acredita
    tamaño ni permite omitir el archivo como si estuviera exento.
    """
    if relative.as_posix() in EXEMPT_PATHS:
        return None
    if relative.name in EXEMPT_NAMES:
        return None
    if relative.suffix.lower() in EXEMPT_SUFFIXES:
        return None
    text = (ROOT / relative).read_text(encoding="utf-8")
    return len(text.splitlines())


def check_reading_path() -> list[str]:
    """Suma las líneas de la ruta de lectura obligatoria (ADR-021).

    Un archivo ausente o ilegible no acredita tamaño cero: es un fallo, con
    la misma lógica que `count_text_lines` aplica a la exención (ADR-007).
    Nunca vuelca la excepción: puede llevar rutas o datos del host.
    """
    global READING_PATH_OBSERVED
    READING_PATH_OBSERVED = None
    if not READING_PATH:
        return []
    failures: list[str] = []

    # Coherencia root_markdown ↔ reading_path (issue #63): un Markdown
    # operativo de raíz declarado por el adoptante —`AN-KLA.md` en el caso
    # real— es lectura obligatoria del ejecutor; un presupuesto activo que
    # no lo declara mide una ruta incompleta y da la falsa comodidad que
    # #42 dejó y #63 encontró dos veces en adoptantes. Config contra
    # config: sin detectar runtime, sin red. Desde gate/v11 (ADR-041) la
    # exigencia cubre también la entrada del ejecutor: AGENTS.md y
    # CLAUDE.md, si existen en la raíz, son lectura obligatoria con
    # presupuesto activo — README queda fuera: cara humana, no entrada del
    # ejecutor.
    intrinsic = _SKEVI_DEFAULTS["ROOT_MARKDOWN"]
    spine = set(READING_PATH["files"])
    # README.md nunca entra: intrinsic siempre lo contiene y la exigencia
    # de existencia condicional sólo cubre AGENTS/CLAUDE (ADR-041).
    pendientes = sorted(ROOT_MARKDOWN - intrinsic)
    for name in ("AGENTS.md", "CLAUDE.md"):
        # .is_file() sigue symlinks a diferencia de discover(), que los
        # excluye: asimetría aceptada y conservadora — el presupuesto
        # cuenta las líneas reales del destino; el límite por archivo de
        # §3.4 es el que un symlink podría saltar (ronda gate/v11, LOW).
        if (ROOT / name).is_file():
            pendientes.append(name)
    for name in pendientes:
        if name not in spine:
            failures.append(
                f"ruta de lectura obligatoria: {name} es lectura "
                "obligatoria del ejecutor y no figura en "
                "«reading_path.files»; absórbelo en el presupuesto por "
                "decisión escrita (la plantilla usage-guide documenta el "
                "caso con límite 1400 como ejemplo)"
            )

    def contar(name: str) -> int | None:
        path = ROOT / name
        if not path.is_file():
            failures.append(f"ruta de lectura obligatoria: falta {name}")
            return None
        try:
            return len(path.read_text(encoding="utf-8").splitlines())
        except UnicodeDecodeError:
            failures.append(
                f"ruta de lectura obligatoria: {name} no es UTF-8 válido"
            )
        except OSError:
            failures.append(
                f"ruta de lectura obligatoria: no se pudo leer {name}"
            )
        return None

    total = 0
    for name in READING_PATH["files"]:
        observado = contar(name)
        if observado is not None:
            total += observado
    # De las alternativas sólo cuenta la mayor: son excluyentes entre sí —
    # un ejecutor lee el archivo de la fase en la que está, no las cinco.
    alternativas = [
        observado
        for name in READING_PATH.get("worst_case_of", [])
        if (observado := contar(name)) is not None
    ]
    if alternativas:
        total += max(alternativas)
    if failures:
        return failures
    limit = READING_PATH["limit"]
    if total > limit:
        failures.append(
            f"ruta de lectura obligatoria: {total} líneas > límite {limit}"
        )
    else:
        # La norma (§3.4 y ADR-025) delega en el gate la cifra vigente; si
        # sólo se emitiera al fallar, el trinquete no sería auditable sin un
        # script ad-hoc. Se publica aparte, no dentro de READING_PATH: ese
        # dict modela la configuración del adoptante y no debe llevar estado
        # de salida.
        READING_PATH_OBSERVED = total
    return failures


def gate_staleness(hoy: date | None = None) -> str | None:
    """Aviso de vejez de esta copia, o None si aún no lo amerita.

    Dice «soy vieja», nunca «existe una nueva»: lo segundo exigiría observar
    el origen, y `project-manifest.yaml` §no_ofrece lo cede. Un adoptante que
    ve la edad decide si comprobar; el gate no decide por él, ni falla por
    ello — la polaridad de aviso la hereda de ADR-020.
    """
    hoy = hoy or date.today()
    try:
        generado = date.fromisoformat(GATE_GENERATED_AT)
    except (ValueError, TypeError):
        # Constante mal editada al copiar —formato roto, comillas borradas—:
        # la identidad de la copia no es frontera de seguridad y no puede
        # tumbar el gate de nadie.
        return None
    dias = (hoy - generado).days
    if dias < GATE_STALE_AFTER_DAYS:
        return None
    return (
        f"AVISO: esta copia del gate ({GATE_VERSION}, {GATE_GENERATED_AT}) "
        f"tiene {dias} días. Comprueba contra su origen si sigue vigente; "
        "este gate no consulta la red ni observa el repositorio de origen."
    )


def main() -> int:
    failures: list[str] = []

    config_error = None
    try:
        reset_to_skevi_defaults()
        apply_config(load_config())
    except _ConfigError as exc:
        config_error = str(exc)
    except UnicodeDecodeError:
        config_error = f"{CONFIG_NAME}: contenido no válido como UTF-8"
    except json.JSONDecodeError as exc:
        config_error = (
            f"{CONFIG_NAME}: JSON inválido "
            f"(línea {exc.lineno}, columna {exc.colno})"
        )
    except OSError:
        config_error = f"{CONFIG_NAME}: no se pudo leer la configuración"
    except ValueError:
        config_error = f"{CONFIG_NAME}: valor no válido en la configuración"
    if config_error is not None:
        print("BLOQ — check_sizes encontró configuración inválida")
        print(f"- {config_error}")
        return 1

    for relative in sorted(REQUIRED):
        if not (ROOT / relative).is_file():
            failures.append(f"falta archivo requerido: {relative}")

    manifest_path = ROOT / "templates" / "skevi" / TEMPLATE_MANIFEST_NAME
    if manifest_path.is_file():
        failures.extend(
            check_templates.check_template_manifest(
                manifest_path, manifest_path.parent)
        )

    scripts_manifest_path = ROOT / "scripts" / TEMPLATE_MANIFEST_NAME
    if scripts_manifest_path.is_file():
        failures.extend(check_templates.check_template_manifest(
            scripts_manifest_path, scripts_manifest_path.parent,
            expected_schema=SCRIPT_MANIFEST_SCHEMA))

    corpus_manifest_path = ROOT / "docs" / TEMPLATE_MANIFEST_NAME
    if corpus_manifest_path.is_file():
        failures.extend(
            check_templates.check_corpus_manifest(corpus_manifest_path)
        )

    # Cuarta familia (ADR-040): los ADRs inmutables, con listado exacto
    # del directorio plano.
    adr_manifest_path = ROOT / "docs" / "adr" / TEMPLATE_MANIFEST_NAME
    if adr_manifest_path.is_file():
        failures.extend(check_templates.check_template_manifest(
            adr_manifest_path, adr_manifest_path.parent,
            expected_schema=check_templates.ADR_MANIFEST_SCHEMA))

    unexpected_markdown = sorted(
        path.name
        for path in ROOT.glob("*.md")
        if path.name not in ROOT_MARKDOWN
    )
    if unexpected_markdown:
        failures.append(
            "Markdown operativo suelto en raíz: "
            + ", ".join(unexpected_markdown)
            + " (decláralo en «root_markdown» de " + CONFIG_NAME + ")"
        )

    failures.extend(check_reading_path())

    rows: list[tuple[str, int, int]] = []
    for relative in discover():
        name = relative.as_posix()
        try:
            observed = count_text_lines(relative)
            if observed is None:
                continue
            if relative.name in REGISTRY_HOSTS:
                text = (ROOT / relative).read_text(encoding="utf-8")
                failures.extend(check_registry_block(relative, text))
        except UnicodeDecodeError:
            failures.append(
                f"{name}: contenido no válido como UTF-8 "
                "(si es binario, exéntalo con «exempt_paths» o "
                f"«exempt_names» en {CONFIG_NAME})"
            )
            continue
        except OSError:
            # No volcar la excepción: puede contener rutas o datos del host.
            failures.append(f"{name}: no se pudo leer el archivo")
            continue
        limit = limit_for(name)
        rows.append((name, observed, limit))
        if observed > limit:
            failures.append(f"{name}: {observed} líneas > límite {limit}")

    aviso = gate_staleness()

    if failures:
        print(
            "BLOQ — check_sizes encontró incumplimientos "
            f"({GATE_VERSION}, {GATE_GENERATED_AT})"
        )
        for failure in failures:
            print(f"- {failure}")
        if aviso:
            print(aviso)
        return 1

    observado = READING_PATH_OBSERVED
    ruta = (
        f"; ruta de lectura {observado}/{READING_PATH['limit']}"
        if observado is not None
        else ""
    )
    print(
        "OK — "
        f"{len(rows)} archivos de texto dentro de límites; "
        f"estructura y hogares canónicos verificados{ruta}"
        f"; {GATE_VERSION} ({GATE_GENERATED_AT})"
    )
    if aviso:
        print(aviso)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
