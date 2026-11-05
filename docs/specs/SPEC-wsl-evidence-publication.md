# Cierre de pruebas Dell G7 7700 y publicación

TAREA WSL-PUBLISH, 2026-11-04 (fecha local). Clase Architectural por
versionar los ejemplos exploratorios probados fuera del árbol.
Base: `9c0035bbd831822f9dcc4894d3619e2ac3546cc0`.
Rama: `chore/wsl-dell-g7-evidence`. La fuente inicial recuperada por
conector vuelve a tener metadatos Git, restaurados desde un clon público
sin checkout; los archivos de trabajo se preservaron.

## Autoridad y alcance

Operador: «en proximas se guardaran trascripciones para verificacion» y
«subir todo a github con los resultados y pruebas para retomar despues».
Autoriza guardar código y evidencia de estas pruebas y publicar en el
repositorio existente. No autoriza reconstruir transcripciones inexistentes
ni publicar voz, imagen o transcripciones personales futuras sin revisión.

Permitido: cambios locales de instalación ya probados, ejemplos WSL,
pruebas focales sin micrófono/cámara, documentación de hardware/resultados,
metadatos Git, commit y publicación de rama y PR para retoma.
Superficie: este workspace y /tmp; terminal; GitHub conector y fetch/clone
del repo existente; loopback 8091 sólo para regresiones no personales;
consulta CIM de fabricante/modelo/RAM, sin identidad ni números de serie.
Prohibido: nuevas capturas reales, modificar motor/pesos, activar modalidades
en el gateway, publicar datos personales, merge a main o alterar el host.
No se consumen APIs de inferencia tarifadas.
Parada: rama publicada, enlace verificable y retoma documentada.

Lote: WSL-PUB-20261104-01 — commit local si procede; publicar rama
`chore/wsl-dell-g7-evidence` y PR hacia main. Aceptación: instrucción
directa del Operador en esta conversación, vigente para este lote.
No se solicita nueva confirmación para operaciones ya autorizadas.

## Criterios

- REQ-P1: hardware observado y revisión/hashes exactos del artefacto.
  Modelo Dell 7700 no se confunde con el identificador de CPU.
- REQ-P2: publicar mediciones existentes con procedencia, distinguir
  pruebas automáticas, veredictos humanos y métricas de consola resumidas.
  No inventar contenido de conversaciones ni logs crudos no guardados.
- REQ-P3: conservar ejemplos en rutas relativas, sin depender de /tmp
  ni rutas del usuario; consentimiento D-09 explícito al ejecutarlos.
  Reusar los algoritmos probados y revisar la adaptación a archivos.
- REQ-P4: registrar persistencia futura de transcripciones local y privada,
  pendiente de implementación. No habilitar grabación de audio/video.
- REQ-P5: suite focal y regresión, cinco gates, revisión fresca sin
  HIGH/BLOCKER y revisión de archivos antes del primer efecto remoto.

Amenazas: publicación accidental de pesos o datos reales, rutas privadas,
ejemplos que activan dispositivos al importar, referencias rotas al mover
scripts y errores de protocolo ocultos por mocks. Controles: allowlist de
archivos Git, ignores de runtime/privado, import seguro y guardas de
consentimiento, pruebas VAD/WS/limpieza y revisión independiente.

DoD: criterios anteriores con evidencia; rama/commit y PR consultables;
ninguna captura nueva ni promoción de gates I1-V. Los resultados de
instalación y la sesión se documentan sin reescribir evidencia histórica.
RED/GREEN: nueva prueba de empaquetado antes de copiar los scripts;
las regresiones de protocolo/VAD se ejercitan sin dispositivos reales.
