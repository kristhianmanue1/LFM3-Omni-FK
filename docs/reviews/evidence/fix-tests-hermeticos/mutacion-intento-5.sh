#!/bin/bash
# Script de mutación — fix-tests-hermeticos, intento 5 (extiende al de
# intento 3 con el mutante 4 del hallazgo HIGH r17b de la ronda 4).
#
# Trabaja SOLO en un clon temporal (git clone --local del worktree con el
# trabajo sin commit copiado encima): el worktree no se toca. Primero
# corrobora que el clon está en verde (BASELINE) y después aplica cada
# mutación, corre sólo el test afectado y espera FAIL. Imprime una línea
# «MUTANTE <n> <muere|sobrevive>» por mutante.
#
#   (1) quitar «detener_puerto 8443» de la copia de stop.sh  → test_11
#   (2) hacer permisiva la función kill del fixture            → test_11
#   (3) sonda que devuelve error tomado como ausencia          → sonda
#   (4) curl sustituto que falla en /health                    → r17b
set -euo pipefail

WORKTREE="$(cd "$(dirname "$0")/../../../.." && pwd)"
TEST11="tests.test_piloto_live_i2.TestPilotoPrivadoLive.test_11_rollback_parada_limpia"
SONDA="tests.test_engine_probe"
R17B="tests.test_ciclo_arranque.Readiness.test_r17b_atajo_idempotente_exige_modelo"
CLON="$(mktemp -d "${TMPDIR:-/tmp}/mutacion-i5.XXXXXX")"
trap 'rm -rf "$CLON"' EXIT

echo "== clon temporal: $CLON =="
git clone --local --quiet "$WORKTREE" "$CLON/repo"

# Trabajo sin commit del worktree encima del clon: diff de archivos
# seguidos (incluye el borrado de tests/test_sonda_motor.py) y copia de
# los nuevos aún sin seguimiento.
git -C "$WORKTREE" diff HEAD > "$CLON/tracked.patch"
git -C "$CLON/repo" apply "$CLON/tracked.patch"
git -C "$WORKTREE" ls-files --others --exclude-standard -z \
| while IFS= read -r -d '' f; do
  mkdir -p "$CLON/repo/$(dirname "$f")"
  cp "$WORKTREE/$f" "$CLON/repo/$f"
done

correr() {  # correr <etiqueta> <objetivo unittest>; deja el rc en $rc
  (cd "$CLON/repo" && python3 -m unittest -v "$2" \
     >"$CLON/corrida-$1.txt" 2>&1) && rc=0 || rc=$?
}

resumen() {
  echo "-- últimas líneas de la corrida ($1) --"
  tail -n 12 "$CLON/corrida-$1.txt"
}

veredicto() {  # veredicto <n> : FAIL esperado
  if [ "$rc" -ne 0 ]; then
    echo "MUTANTE $1 muere"
  else
    echo "MUTANTE $1 sobrevive"
  fi
}

echo "== BASELINE (clon sin mutar; debe estar en verde) =="
correr base11 "$TEST11"
BASELINE_11=$rc
correr baseSONDA "$SONDA"
BASELINE_SONDA=$rc
correr baseR17B "$R17B"
BASELINE_R17B=$rc
echo "BASELINE test_11 rc=$BASELINE_11 ; sonda rc=$BASELINE_SONDA ; r17b rc=$BASELINE_R17B"
if [ "$BASELINE_11" -ne 0 ] || [ "$BASELINE_SONDA" -ne 0 ] \
   || [ "$BASELINE_R17B" -ne 0 ]; then
  echo "BASELINE en rojo: el clon no reproduce el verde; aborto sin veredicto"
  resumen base11
  resumen baseR17B
  exit 9
fi

echo "== MUTANTE 1: quitar detener_puerto 8443 de run/stop.sh =="
sed -i '' '/detener_puerto 8443/d' "$CLON/repo/run/stop.sh"
correr mut1 "$TEST11"
veredicto 1
resumen mut1
git -C "$CLON/repo" checkout -- run/stop.sh

echo "== MUTANTE 2: kill del fixture permisivo (rc de negativa anulado) =="
if ! grep -q 'rc=1' "$CLON/repo/tests/hermetic_fixture.py"; then
  echo "MUTANTE 2 sobrevive (patrón no encontrado: revisar el fixture)"
else
  sed -i '' 's/rc=1/rc=0/g' "$CLON/repo/tests/hermetic_fixture.py"
  correr mut2 "$TEST11"
  veredicto 2
  resumen mut2
  cp "$WORKTREE/tests/hermetic_fixture.py" "$CLON/repo/tests/hermetic_fixture.py"
fi

echo "== MUTANTE 3: error de sonda tomado como ausencia =="
sed -i '' 's/return False, f"error de sonda: {exc.reason!r}"/return False, None/' \
  "$CLON/repo/tests/engine_probe.py"
if ! grep -q 'return False, None' "$CLON/repo/tests/engine_probe.py"; then
  echo "MUTANTE 3 sobrevive (la mutación no se aplicó: revisar engine_probe)"
else
  correr mut3 "$SONDA"
  veredicto 3
  resumen mut3
  cp "$WORKTREE/tests/engine_probe.py" "$CLON/repo/tests/engine_probe.py"
fi

echo "== MUTANTE 4: el curl sustituto falla en /health =="
# El printf de /health del curl sustituto pasa a «exit 7»: serve.sh ya no
# ve el /health del servicio ajeno y salta el atajo hacia la rama de
# puerto ocupado. r17b exige en stderr el rechazo por modelo efectivo,
# así que DEBE fallar (hallazgo HIGH ronda 4: verde por la rama
# equivocada).
sed -i '' "s|printf '%s\\\\n' '{\"status\":\"ok\"}'|exit 7|" \
  "$CLON/repo/tests/hermetic_fixture.py"
if grep -q 'status.:.ok' "$CLON/repo/tests/hermetic_fixture.py"; then
  echo "MUTANTE 4 sobrevive (la mutación no se aplicó: revisar el fixture)"
else
  correr mut4 "$R17B"
  veredicto 4
  resumen mut4
  cp "$WORKTREE/tests/hermetic_fixture.py" "$CLON/repo/tests/hermetic_fixture.py"
fi

echo "== fin del script de mutación =="
