#!/usr/bin/env python3
"""Chequeo de drift de artefactos versionados de Skevi (PROP-006@#28 D3 +
enmiendas T09; extendido a scripts/ por ADR-028).

Compara un MANIFEST fuente de Skevi contra el registro de instalación del
consumidor. El mecanismo es genérico por diseño — no depende de que el
artefacto sea una plantilla de documentación—: reconoce tres familias de
esquema, cada una con su propio espacio de nombres de versión:

  - plantillas de adopción: `skevi/template-manifest/v1` +
    `skevi/template-install/v1`, versión `plantillas/vN` (ADR-020)
  - scripts de gate:        `skevi/script-manifest/v1` +
    `skevi/script-install/v1`, versión `gate/vN` (ADR-028)
  - corpus normativo:       `skevi/corpus-manifest/v1` +
    `skevi/corpus-install/v1`, versión `corpus/vN` (ADR-032)

El señal válido de drift es la versión declarada, nunca el contenido: las
plantillas se rellenan por diseño y los scripts pueden llevar exenciones
locales del adoptante en `skevi-gate.json`; ninguno de los dos coincide
byte a byte con la fuente por diseño.

Clasificación T09: (A) obsoleto pero compatible → aviso; (B) obsoleto
incompatible → fallo `template_drift_version` (#28 D3.2 resuelta como fallo);
(C) personalizado → anula A/B por archivo declarado. Versión sin cadena
hasta la vigente → B (fail-closed) — esto también protege contra comparar
un manifiesto de una familia contra un registro de la otra: sin historia
compartida, no hay cadena, y el resultado es el mismo BLOQ que una versión
retirada. Copiable sin edición: stdlib-only, sin red, no muta archivos.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# Dos familias de esquema reconocidas (ADR-020, ADR-028). Añadir una tercera
# —otro artefacto versionado de Skevi— es extender estos tres conjuntos
# —MANIFEST_SCHEMAS, INSTALL_SCHEMAS y SCHEMA_NAMESPACE—, no tocar la lógica
# de comparación: main()/_chain() son agnósticos a la familia. Olvidar
# SCHEMA_NAMESPACE no es un error silencioso: _check_namespace falla
# cerrado ante un esquema sin namespace registrado (ronda adversarial, MED).
MANIFEST_SCHEMAS = {"skevi/template-manifest/v1", "skevi/script-manifest/v1",
                    "skevi/corpus-manifest/v1", "skevi/adr-manifest/v1"}
INSTALL_SCHEMAS = {"skevi/template-install/v1", "skevi/script-install/v1",
                   "skevi/corpus-install/v1"}
# Cada esquema exige su propio espacio de nombres de versión. Sin esto, un
# manifiesto de la familia equivocada con un namespace de versión que
# coincida por accidente con el del otro documento producía OK falso: cada
# familia es válida "en su conjunto" de esquemas, pero eso no basta para
# saber que ambos documentos hablan de lo mismo (hallazgo HIGH, 2026-09-08).
SCHEMA_NAMESPACE = {
    "skevi/template-manifest/v1": "plantillas",
    "skevi/template-install/v1": "plantillas",
    "skevi/script-manifest/v1": "gate",
    "skevi/script-install/v1": "gate",
    "skevi/corpus-manifest/v1": "corpus",
    "skevi/corpus-install/v1": "corpus",
    "skevi/adr-manifest/v1": "adr",
}
MANIFEST_KEYS = {"schema", "version", "generated_at", "files", "history"}
INSTALL_KEYS = {"schema", "version", "files", "installed_at", "source",
                "customized"}
HISTORY_KEYS = {"from", "to", "breaking", "changes"}
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
# Procedencia cerrada del registro de instalación (A-7 de PROP-002,
# aterrizada por ADR-031): <origen>@<revisión>. El origen es texto sin @
# ni espacios —URL o ruta relativa—; la revisión es hex minúsculas de 7 a
# 64 dígitos: sha de Git corto o completo, incluido SHA-256 de repo.
SOURCE_RE = re.compile(r"^[^@\s]+@[0-9a-f]{7,64}$")
# Namespace en minúsculas + /vN: cubre "plantillas/v1" y "gate/v2" con la
# misma expresión — el espacio de nombres lo declara la familia, no el regex.
VERSION_RE = re.compile(r"^[a-z]+/v\d+(\.\d+)*$")
DRIFT_REASON = "template_drift_version"


class _InputError(ValueError):
    """Entrada inválida con motivo fijo; nunca payload ni rutas del host."""


def _require(condition, message):
    if not condition:
        raise _InputError(message)


def _check_digest(value, where):
    _require(isinstance(value, str) and DIGEST_RE.match(value),
             f"{where} no es un digest con formato sha256:<hex>")


def _check_namespace(version, schema, where):
    """La versión debe llevar el espacio de nombres que su propio esquema
    declara — "gate/vN" para las familias de scripts, "plantillas/vN" para
    las de plantillas — nunca el del otro documento."""
    if version is None:
        return
    expected_namespace = SCHEMA_NAMESPACE.get(schema)
    # Fail-closed: un esquema válido sin namespace registrado es un olvido
    # de mantenimiento, no una razón para omitir la comprobación.
    _require(expected_namespace is not None,
             f"{where}: {schema} no tiene namespace de versión registrado "
             "(SCHEMA_NAMESPACE desactualizado)")
    _require(version.startswith(expected_namespace + "/"),
             f"{where}: version «{version}» no corresponde al espacio de "
             f"nombres de {schema} (se espera {expected_namespace}/vN)")


def _check_common(data, schemas, keys, label):
    _require(isinstance(data, dict), f"{label}: la raíz debe ser un objeto")
    missing = sorted(keys - set(data))
    _require(not missing,
             f"{label}: campos obligatorios ausentes: {', '.join(missing)}")
    _require(isinstance(data["schema"], str) and data["schema"] in schemas,
             f"{label}: schema desconocido (se espera uno de "
             + ", ".join(sorted(schemas)) + ")")
    unknown = sorted(set(data) - keys)
    _require(not unknown,
             f"{label}: campo desconocido: {', '.join(unknown)}")


def _load_manifest(path: Path) -> dict:
    label = "manifest"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raise _InputError(f"{label}: no se pudo leer el archivo")
    except UnicodeDecodeError:
        raise _InputError(f"{label}: contenido no válido como UTF-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _InputError(
            f"{label}: JSON inválido (línea {exc.lineno}, columna {exc.colno})"
        )
    except RecursionError:
        raise _InputError(f"{label}: JSON inválido o demasiado anidado")
    _check_common(data, MANIFEST_SCHEMAS, MANIFEST_KEYS, label)
    _require(isinstance(data["version"], str)
             and VERSION_RE.match(data["version"]),
             f"{label}: version no coincide con <namespace>/v<n>")
    _check_namespace(data["version"], data["schema"], label)
    _require(isinstance(data["generated_at"], str) and data["generated_at"],
             f"{label}: generated_at debe ser texto con fecha")
    _require(isinstance(data["files"], dict) and data["files"],
             f"{label}: files debe ser un objeto con entradas")
    for name, digest in data["files"].items():
        _check_digest(digest, f"{label}: files.{name}")
    _require(isinstance(data["history"], list),
             f"{label}: history debe ser una lista")
    for index, jump in enumerate(data["history"]):
        where = f"{label}: history[{index}]"
        _require(isinstance(jump, dict), f"{where} debe ser un objeto")
        _require(set(jump) == HISTORY_KEYS,
                 f"{where} debe tener exactamente from/to/breaking/changes")
        _require(jump["from"] is None
                 or (isinstance(jump["from"], str)
                     and VERSION_RE.match(jump["from"])),
                 f"{where}.from no es una versión válida")
        if isinstance(jump.get("from"), str):
            _check_namespace(jump["from"], data["schema"], f"{where}.from")
        _require(isinstance(jump["to"], str)
                 and VERSION_RE.match(jump["to"]),
                 f"{where}.to no es una versión válida")
        if isinstance(jump.get("to"), str):
            _check_namespace(jump["to"], data["schema"], f"{where}.to")
        _require(isinstance(jump["breaking"], bool),
                 f"{where}.breaking debe ser booleano")
        _require(isinstance(jump["changes"], dict),
                 f"{where}.changes debe ser un objeto")
        for name, summary in jump["changes"].items():
            _require(isinstance(summary, str),
                     f"{where}.changes.{name} debe ser texto")
    return data


def _load_install(path: Path) -> dict:
    label = "installed"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raise _InputError(f"{label}: no se pudo leer el archivo")
    except UnicodeDecodeError:
        raise _InputError(f"{label}: contenido no válido como UTF-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _InputError(
            f"{label}: JSON inválido (línea {exc.lineno}, columna {exc.colno})"
        )
    except RecursionError:
        raise _InputError(f"{label}: JSON inválido o demasiado anidado")
    _check_common(data, INSTALL_SCHEMAS, INSTALL_KEYS, label)
    _require(isinstance(data["version"], str)
             and VERSION_RE.match(data["version"]),
             f"{label}: version no coincide con <namespace>/v<n>")
    _check_namespace(data["version"], data["schema"], label)
    _require(isinstance(data["files"], dict) and data["files"],
             f"{label}: files debe ser un objeto con entradas")
    for name, digest in data["files"].items():
        _check_digest(digest, f"{label}: files.{name}")
    _require(isinstance(data["installed_at"], str) and data["installed_at"],
             f"{label}: installed_at debe ser texto con fecha")
    _require(isinstance(data["source"], str)
             and SOURCE_RE.match(data["source"]),
             f"{label}: source debe ser <origen>@<revisión> "
             "(p. ej. https://github.com/org/repo@0a1b2c3)")
    _require(isinstance(data["customized"], list)
             and all(isinstance(v, str) for v in data["customized"]),
             f"{label}: customized debe ser una lista de nombres de archivo")
    outside = sorted(set(data["customized"]) - set(data["files"]))
    _require(not outside,
             f"{label}: customized declara un archivo ausente de files: "
             + ", ".join(outside))
    return data


def _chain(history, start: str, current: str):
    """Devuelve (saltos, None) de start a current, o (None, motivo)."""
    jumps = []
    seen = {start}
    node = start
    while node != current:
        edges = [h for h in history if h["from"] == node]
        if len(edges) > 1:
            return None, (f"history ambigua para {node} "
                          "(varios saltos desde la misma versión)")
        if not edges:
            return None, (f"versión instalada {start} sin cadena hasta la "
                          "vigente: se trata como incompatible (fail-closed)")
        edge = edges[0]
        jumps.append(edge)
        node = edge["to"]
        if node in seen:
            return None, f"history con ciclo en {node}"
        seen.add(node)
    return jumps, None


def _detalle(texto: str) -> str:
    """El texto de `changes` viene de un manifiesto ajeno: dato no confiable
    (estándar, principio 7). Se imprime saneado —una línea, sin controles ni
    secuencias de escape, acotado— para que no pueda falsear la salida del
    gate con un `OK` inventado ni borrar la pantalla con ANSI."""
    limpio = "".join(c if c.isprintable() else " " for c in texto)
    unido = " ".join(limpio.split())
    return unido[:300] + "…" if len(unido) > 300 else unido


# ────────────────────────────────────────────────────────────────────────
# Validación estructural y cotejo contra disco de los MANIFEST fuente
# (hogar desde gate/v9; ADR-039). Vivió en check_sizes.py — 870/870,
# issue #61 — pese a que este archivo ya era el dueño del dominio. El
# modelo de fallo es lista agregable, como exige el main() del gate de
# tamaños; _load_manifest, arriba, falla al primer defecto porque es
# entrada de CLI. Mismos mensajes que siempre: adoptantes y tests los
# igualan.
# ────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
# Basura del SO que el listado exacto ignora; cerrada, nunca config
# (issue #59) — misma regla que rige el resto del listado del disco.
LISTING_JUNK = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})
TEMPLATE_MANIFEST_NAME = "MANIFEST.json"
TEMPLATE_MANIFEST_SCHEMA = "skevi/template-manifest/v1"
# Segunda familia (ADR-028): mismo check_template_manifest, sobre scripts/
# en vez de templates/skevi/, validación estricta por directorio.
SCRIPT_MANIFEST_SCHEMA = "skevi/script-manifest/v1"
# Tercera familia (ADR-032): el canon normativo (estándar + guía) con
# digests en docs/MANIFEST.json; sin listado de directorio, porque docs/
# anida subdirectorios y el contrato de ADR-020 es plano por diseño.
CORPUS_MANIFEST_SCHEMA = "skevi/corpus-manifest/v1"
# Cuarta familia (ADR-040): los ADRs inmutables de docs/adr/, con listado
# exacto — directorio plano, cada ADR nuevo exige entrada y bump. Sin
# esquema de instalación: existe para verificar descargas, no como flujo
# de adopción.
ADR_MANIFEST_SCHEMA = "skevi/adr-manifest/v1"


def _namespace_failure(version, expected_schema: str, where: str) -> str | None:
    """Gemela coleccionista de _check_namespace: devuelve el fallo en vez
    de levantarlo, porque aquí los defectos se acumulan para el gate que
    consume la lista (ADR-007: diagnóstico con campos conocidos)."""
    if not isinstance(version, str):
        return None
    # Fail-closed: esquema sin namespace registrado es olvido de
    # mantenimiento, no motivo para omitir la comprobación.
    expected_namespace = SCHEMA_NAMESPACE.get(expected_schema)
    if expected_namespace is None:
        return f"{where}: {expected_schema} no tiene namespace registrado"
    if version.startswith(expected_namespace + "/"):
        return None
    return (f"{where}: version «{version}» no corresponde al espacio de "
            f"nombres de {expected_schema} (se espera {expected_namespace}/vN)")


def _validate_template_manifest(
    data, label: str, expected_schema: str = TEMPLATE_MANIFEST_SCHEMA
) -> list[str]:
    """Esquema cerrado del MANIFEST (formato de ADR-020, familias en ADR-028).
    Falla por campo, con motivo fijo, sin volcar contenido. Validación
    estricta: cada manifiesto se valida contra un único esquema esperado,
    no contra cualquiera que Skevi reconozca — un manifiesto de scripts no
    puede colarse donde se espera uno de plantillas."""
    failures: list[str] = []
    if not isinstance(data, dict):
        return [f"{label}: la raíz debe ser un objeto"]
    missing = sorted(MANIFEST_KEYS - set(data))
    if missing:
        return [f"{label}: campos obligatorios ausentes: {', '.join(missing)}"]
    if data.get("schema") != expected_schema:
        failures.append(
            f"{label}: schema desconocido (se espera {expected_schema})"
        )
    unknown = sorted(set(data) - MANIFEST_KEYS)
    if unknown:
        failures.append(
            f"{label}: campo desconocido: {', '.join(unknown)}"
        )
        return failures
    if not isinstance(data["version"], str) \
            or not VERSION_RE.match(data["version"]):
        failures.append(f"{label}: version no coincide con <namespace>/v<n>")
    else:
        ns_fallo = _namespace_failure(data["version"], expected_schema, label)
        if ns_fallo:
            failures.append(ns_fallo)
    if not isinstance(data["generated_at"], str) or not data["generated_at"]:
        failures.append(f"{label}: generated_at debe ser texto con fecha")
    if not isinstance(data["files"], dict) or not data["files"]:
        failures.append(
            f"{label}: files debe ser un objeto con entradas"
        )
        return failures
    for name, digest in data["files"].items():
        if not isinstance(digest, str) or not DIGEST_RE.match(digest):
            failures.append(
                f"{label}: files.{name} no es un digest con formato "
                "sha256:<hex>"
            )
    if not isinstance(data["history"], list):
        failures.append(f"{label}: history debe ser una lista")
        return failures
    for index, jump in enumerate(data["history"]):
        where = f"{label}: history[{index}]"
        if not isinstance(jump, dict) or set(jump) != HISTORY_KEYS:
            failures.append(
                f"{where} debe tener exactamente from/to/breaking/changes"
            )
            continue
        for extremo in ("from", "to"):
            valor = jump[extremo]
            if extremo == "from" and valor is None:
                continue
            if not isinstance(valor, str) or not VERSION_RE.match(valor):
                failures.append(f"{where}.{extremo} no es una versión válida")
                continue
            ns_fallo = _namespace_failure(
                valor, expected_schema, f"{where}.{extremo}")
            if ns_fallo:
                failures.append(ns_fallo)
        if not isinstance(jump["breaking"], bool):
            failures.append(f"{where}.breaking debe ser booleano")
        if not isinstance(jump["changes"], dict):
            failures.append(f"{where}.changes debe ser un objeto")
            continue
        for name, summary in jump["changes"].items():
            if not isinstance(summary, str):
                failures.append(f"{where}.changes.{name} debe ser texto")
    return failures


def check_template_manifest(
    manifest_path: Path,
    templates_dir: Path,
    expected_schema: str = TEMPLATE_MANIFEST_SCHEMA,
    verify_listing: bool = True,
) -> list[str]:
    """Valida un MANIFEST fuente de Skevi (#28 D1 + T09; familias ADR-028 y
    ADR-032): esquema cerrado, digests vigentes y —para las familias planas—
    listado exacto del directorio. Fail-closed, sin tracebacks."""
    # Bajo ROOT: etiqueta real ("scripts/..."). Fuera de ROOT (tests): se
    # degrada al nombre del directorio.
    try:
        dir_label = templates_dir.relative_to(ROOT).as_posix()
    except ValueError:
        dir_label = templates_dir.name
    label = f"{dir_label}/{TEMPLATE_MANIFEST_NAME}"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return [f"{label}: contenido no válido como UTF-8"]
    except OSError:
        return [f"{label}: no se pudo leer el archivo"]
    except json.JSONDecodeError as exc:
        return [
            f"{label}: JSON inválido (línea {exc.lineno}, columna {exc.colno})"
        ]
    except RecursionError:
        return [f"{label}: JSON inválido o demasiado anidado"]
    failures = _validate_template_manifest(data, label, expected_schema)
    if failures:
        return failures
    if not verify_listing:
        # Familia corpus (ADR-032): se verifica el digest de cada archivo
        # declarado, con ruta relativa al directorio del manifiesto y sin
        # escapar de la raíz. Un archivo ausente es fallo, nunca omisión.
        for name, digest in data["files"].items():
            candidate = manifest_path.parent / name
            try:
                candidate.resolve().relative_to(ROOT.resolve())
            except ValueError:
                failures.append(
                    f"{label}: files.{name} escapa de la raíz del proyecto"
                )
                continue
            try:
                observed = "sha256:" + hashlib.sha256(
                    candidate.read_bytes()
                ).hexdigest()
            except OSError:
                failures.append(f"{label}: no se pudo leer {name}")
                continue
            if observed != digest:
                failures.append(
                    f"{label}: digest desactualizado para {name} "
                    "(¿cambió el canon sin bump?)"
                )
        return failures
    try:
        entries = sorted(templates_dir.iterdir(), key=lambda path: path.name)
    except OSError:
        return [f"{label}: no se pudo leer {dir_label}/"]
    on_disk = []
    for path in entries:
        if not path.is_file():
            continue
        if path.name == TEMPLATE_MANIFEST_NAME:
            continue
        if path.is_symlink():
            # Los symlinks no se siguen: la frontera de raíz vale también
            # para el listado de plantillas (ronda adversarial, LOW).
            failures.append(
                f"{label}: symlink no permitido en {dir_label}/: {path.name}"
            )
            continue
        if path.name not in LISTING_JUNK or path.name in data["files"]:
            on_disk.append(path.name)
    listed = sorted(data["files"])
    if listed != on_disk:
        missing = sorted(set(on_disk) - set(listed))
        extra = sorted(set(listed) - set(on_disk))
        if missing:
            failures.append(
                f"{label}: archivos sin entrada en el manifiesto: "
                + ", ".join(missing)
            )
        if extra:
            failures.append(
                f"{label}: entradas sin archivo real: " + ", ".join(extra)
            )
        return failures
    for name, digest in data["files"].items():
        try:
            actual = "sha256:" + hashlib.sha256(
                (templates_dir / name).read_bytes()
            ).hexdigest()
        except OSError:
            failures.append(f"{label}: no se pudo leer {name}")
            continue
        if digest != actual:
            failures.append(
                f"{label}: digest desactualizado para {name} "
                "(¿cambió la plantilla sin bump?)"
            )
    return failures


def check_corpus_manifest(manifest_path: Path) -> list[str]:
    """Familia corpus (ADR-032): docs/MANIFEST.json declara el canon
    (estándar + guía) y aquí se verifica su estructura y sus digests, sin
    listado de directorio — docs/ anida subdirectorios y el contrato de
    ADR-020 es plano por diseño."""
    return check_template_manifest(
        manifest_path, manifest_path.parent,
        expected_schema=CORPUS_MANIFEST_SCHEMA, verify_listing=False)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Chequeo de drift de un artefacto versionado de Skevi: "
            "plantillas de adopción (ADR-020) o scripts de gate (ADR-028)."
        )
    )
    parser.add_argument("--manifest", required=True,
                        help="MANIFEST fuente (skevi/template-manifest/v1 "
                        "o skevi/script-manifest/v1)")
    parser.add_argument("--installed", required=True,
                        help="registro del consumidor "
                        "(template-install/v1 o script-install/v1)")
    args = parser.parse_args(argv)

    try:
        manifest = _load_manifest(Path(args.manifest))
        installed = _load_install(Path(args.installed))
    except _InputError as exc:
        print(f"BLOQ — {exc}")
        return 1

    current = manifest["version"]
    start = installed["version"]
    customized = set(installed["customized"])
    if start == current:
        print(f"OK — al día: versión vigente {current}")
        return 0

    jumps, error = _chain(manifest["history"], start, current)
    if error is not None:
        print(f"BLOQ — {DRIFT_REASON}: {error}")
        return 1

    affected: set[str] = set()
    for jump in jumps:
        affected.update(jump["changes"])
    # Customizados a anunciar: los afectados declarados, o todos los
    # declarados si la cadena no registra cambios por archivo.
    custom = sorted(affected & customized) if affected else sorted(customized)
    breaking = [j for j in jumps if j["breaking"]]

    if breaking:
        # Con saltos breaking y sin registro por archivo, el fallo es
        # conservador: todos los archivos instalados cuentan como afectados
        # salvo los declarados customized (T09, bandera conservadora).
        # `stale` **no** se acota a lo declarado en installed.json, al revés
        # que el aviso de la rama compatible: ahí sobrar un nombre es ruido,
        # aquí faltar uno sería dejar pasar una migración obligatoria. Ante
        # un registro incompleto, el BLOQ se equivoca del lado seguro.
        stale = sorted((affected or set(installed["files"])) - customized)
        if stale:
            print(f"BLOQ — {DRIFT_REASON}: copia obsoleta incompatible "
                  f"respecto de {current}")
            for jump in breaking:
                print(f"- salto breaking: {jump['from']} -> {jump['to']}")
            for name in stale:
                print(f"- afectado sin customized declarado: "
                      f"{_detalle(name)}")
                # El texto de migración vive en `changes` del manifiesto y
                # nadie lo imprimía: el adoptante recibía el BLOQ y tenía que
                # abrir el JSON para saber qué hacer, justo cuando más falta
                # le hace (issue #57).
                for jump in breaking:
                    detalle = _detalle(jump["changes"].get(name) or "")
                    if detalle:
                        print(f"  {jump['from']} -> {jump['to']}: {detalle}")
            for name in custom:
                print(f"- customized (re-copia bajo responsabilidad del "
                      f"consumidor): {_detalle(name)}")
                # Quien declaró el archivo como customizado es justo quien
                # tiene que aplicar la migración a mano: necesita el detalle
                # más que nadie (issue #57).
                for jump in breaking:
                    detalle = _detalle(jump["changes"].get(name) or "")
                    if detalle:
                        print(f"  {jump['from']} -> {jump['to']}: {detalle}")
            return 1

    if breaking:
        # El detalle sale sólo de los saltos `breaking`: en los demás, la
        # re-copia es opcional y el manifiesto ya la resume en el aviso.
        # Todos los afectados están declarados `customized`, así que no hay
        # BLOQ —eso no cambia, sería romper a quien hoy pasa—, pero decir
        # «sin saltos breaking» sería falso: los hay, y la migración es del
        # consumidor. Sin esto, el adoptante que customizó todo no se entera
        # de que existe (issue #57).
        print(f"OK — copia obsoleta con saltos breaking cubiertos por "
              f"customized, hasta {current}")
        for jump in breaking:
            print(f"- salto breaking: {jump['from']} -> {jump['to']}")
            for name in sorted(set(jump["changes"]) & customized):
                print(f"  {_detalle(name)}: "
                      f"{_detalle(jump['changes'][name])}")
    else:
        print(f"OK — copia obsoleta pero compatible: sin saltos breaking "
              f"aplicables hasta {current}")
    if not affected:
        print("- aviso: la cadena no registra cambios por archivo; "
              "re-copia opcional")
    else:
        # El aviso se acota a lo que el consumidor declaró instalado: decirle
        # «re-copia» de un archivo que nunca copió es ruido, y señal ruidosa
        # es señal que se ignora (issue #57). Lo que cambió y no figura en su
        # registro se anuncia aparte, sin llamarlo «nuevo»: el manifiesto
        # lleva cambios por salto, no inventario por versión, así que desde
        # aquí no se sabe si el archivo es nuevo o si nunca lo copió.
        instalado = set(installed["files"])
        for name in sorted((affected - customized) & instalado):
            print(f"- aviso: re-copia opcional; cambia en la cadena: "
                  f"{_detalle(name)}")
        for name in sorted((affected - customized) - instalado):
            print(f"- aviso: cambia en la cadena y no está en tu "
                  f"installed.json: {_detalle(name)}")
    for name in custom:
        print(f"- aviso: customized — re-copia bajo responsabilidad del "
              f"consumidor: {_detalle(name)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
