## Problema

El hook local `scripts/hooks/pre-push` (y el shebang `#!/usr/bin/env python3`
de los `check_*.py`) invoca `python3` desnudo. En macOS eso resuelve a
`/usr/bin/python3` **3.9.6** aunque el proyecto consumidor haya fijado un
runtime superior, así que el gate local corre con un intérprete distinto
del declarado y no falla al hacerlo.

Observado en el consumidor LFM3-Omni-FK (adopción de Skevi en
`41e4e8c`, fuente `skevi@74a4714`): el Operador fijó el runtime en
Python 3.12+ (2026-11-04), pero el pre-push sigue corriendo
`check_sizes`, `check_plans`, `check_reports` y `unittest` con 3.9.6. Hoy
pasa por coincidencia; nada garantiza que el gate pruebe lo que corre el
proyecto.

```text
$ command -v python3; python3 --version
/usr/bin/python3
Python 3.9.6
$ command -v python3.12
/opt/homebrew/bin/python3.12
```

## Requisito

**El intérprete debe ser Python 3.12 o posterior.**

## Propuesta

1. El hook resuelve el intérprete explícitamente y falla cerrado: usa
   `python3.12` (o el primero ≥ 3.12 disponible), comprueba
   `sys.version_info >= (3, 12)` y aborta el push con mensaje claro si no
   lo hay. Nunca cae en silencio a `python3`.
2. Los `check_*.py` validan la versión al arrancar (fail-closed) en vez de
   confiar en el shebang.
3. Revisar ADR-034: hoy la matriz de CI declara Python 3.9 y 3.12 como
   soportados (`README.md:155`, `.github/workflows/skevi-gate.yml`). Con
   un piso de 3.12, la matriz pasa a 3.12+ (por ejemplo 3.12 y 3.13) y el
   ADR registra el cambio y su motivo.
4. Documentar en la guía de adopción (`usage-guide`) el runtime mínimo y
   cómo se resuelve el intérprete, para que los consumidores no tengan que
   registrar una desviación local para lo mismo.

## Notas

- El hook no aparece en `scripts/MANIFEST.json` ni en
  `.skevi/scripts-installed.json` del consumidor, así que el control de
  drift no lo vigila: un parche local no se detectaría ni se propagaría.
  Convendría incluirlo en el manifiesto.
- Antecedente: otro consumidor (ADRC, `scripts/adrc/ci_local.sh`) ya tuvo
  que resolver `python3.12` explícitamente, fallando cerrado, para correr
  los gates de Skevi.
