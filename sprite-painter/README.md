# Monkey Sprite Painter

Refinador local para revisar assets, comparar versiones y retocar con Confite. Requiere Python 3.11 o posterior, Pillow y NumPy (`python -m pip install -r requirements.txt`). Las operaciones locales no consumen créditos; generar con proveedores externos requiere conexión y credenciales locales.

## Entregas

En la grilla, **Entregas** prepara una copia de las versiones en uso. El alcance completo toma las escenas 9, 10 y 11 del plan, sus dependencias compartidas, fondos e inventario. Permite filtrar agua, bordes, halos y aprobaciones pendientes y abrir cada asset para revisarlo.

Las aprobaciones se verifican contra el hash del PNG actual. Un análisis estricto compara forma, color, trazo y alpha; sus alertas son sugerencias de revisión, no una certificación artística. Los fondos sin original asociado quedan pendientes. La reproducción en el juego y las animaciones deben revisarse antes de considerar final una entrega.

**Crear rama revisada** exige que no queden pendientes. **Crear rama como borrador** conserva los pendientes en el informe. La rama sale del commit `origin/main` registrado al preparar la entrega; actualizá esa referencia antes de analizar si necesitás incorporar cambios nuevos del remoto. El proceso usa un índice Git temporal y conserva el checkout, los cambios locales y lo que ya estuviera staged. Los PNG pasan por Git LFS. Solo incluye masters seleccionados, derivados de copia, el manifiesto actualizado y el informe; no incluye credenciales, historial local ni el código del editor. **Enviar rama** publica esa rama sin force-push.

Antes de crear la rama se vuelven a verificar los hashes de imágenes y originales. Si cambió algo, prepará otra entrega. Las copias quedan en `.context/sprite-painter/deliveries/` y no se incluyen en el Git general.

## Abrir

Doble clic en **Abrir editor.cmd**. Abre http://127.0.0.1:5215. Dejá abierta la ventana del servidor mientras trabajás; cerrala para detenerlo.

Alternativa: `python server.py --root D:\monkey-island-3-remaster-4k`.

## Dibujar

- Elegí una colección y secuencia a la izquierda, o importá uno o varios PNG con **+**. Los nombres `nombre_frame_0.png`, `nombre_frame_1.png`, etc., forman una secuencia ordenada.
- Pincel **B**, goma **E**, cuentagotas **I** (también Alt/clic derecho) y mano **H**.
- La presión del lápiz controla el tamaño. El indicador muestra la presión recibida. Se ignoran los contactos táctiles sobre el lienzo para evitar marcas de la palma. La compatibilidad final depende del controlador y del navegador; no se comprobó con una tableta física.
- Tamaño, opacidad, dureza y bloqueo de alfa. **[ / ]** ajustan el tamaño.
- Rueda para zoom alrededor del cursor. **Espacio + arrastrar** desplaza el lienzo; **F** ajusta la vista.
- **Ctrl Z / Ctrl Shift Z** deshacen y rehacen. El historial en memoria tiene un límite de 96 MB por pila y hasta 30 pasos, según las dimensiones.
- **Antes / después** compara el PNG base y el retoque con un deslizador. Volvé a desactivarlo para pintar.
- Onion skin anterior rosa y siguiente celeste. Configurá intensidad, anclaje y offsets de comparación. No modifica el tamaño del PNG ni las coordenadas del motor. No se importan automáticamente los offsets del motor.
- Elegí rango y FPS en Preview. Los archivos se reproducen por su número de cuadro: no son automáticamente los ciclos de acciones del motor. Usá rangos cortos para revisar una acción.
- **A / D** o las flechas cambian de cuadro. Se guarda el retoque pendiente antes de cambiar. Si falla el guardado, el cuadro permanece abierto.

## Guardado seguro

**Guardar retoque / Ctrl S** escribe en `.context/sprite-painter/edits/`. Conserva tamaño y transparencia; los masters y el manifiesto del juego no se reemplazan. **Exportar PNG** descarga una copia con nombre legible.

Cada guardado posterior conserva la versión anterior en `.context/sprite-painter/history/`. El selector de versiones permite recuperar sus píxeles como un nuevo retoque; los offsets actuales de comparación permanecen. Las imágenes importadas se conservan en `.context/sprite-painter/imports/`.

El editor detecta conflictos si otra ventana guarda el mismo cuadro. En ese caso exportá el PNG de tu lienzo antes de recargar. Los archivos originales no se borran. Las versiones se conservan sin limpieza automática y pueden ocupar espacio.

La carpeta `.context/` está ignorada por Git en este proyecto: estos retoques son locales. Para incorporarlos al juego y compartirlos, habrá que revisar los PNG, actualizar masters/runtime y el manifiesto mediante el flujo del proyecto. Guardar aquí no cambia el estado de aprobación del remaster.

Los recursos que sigan siendo punteros LFS mostrarán un error explicativo al abrirlos. Importar PNG permite trabajar incluso sin el paquete del juego.

## Escalado e historial de Confite

El recorrido principal es **grilla → comparación → versiones → retoque manual**.
Tocar una tarjeta abre la mesa de comparación, no Confite. Original y resultado
tienen zoom/desplazamiento sincronizados y fondos de contraste. El lateral reúne
modelos Topaz e ImageLab, variantes generadas y guardados manuales. Seleccionar una
versión solo cambia la vista; **Usar esta versión** conserva el trabajo reemplazado
en el historial. **Retocar esta versión en Confite** carga la selección como borrador
y permite volver a la comparación al guardar. Las variantes con alertas pueden
abrirse para corrección manual, pero no quedan aprobadas automáticamente.

En la grilla, **Escalar ×4 · Replicate** encola Topaz CGI desde el original asociado,
nunca desde el borrador o remaster. La credencial se lee únicamente en el servidor
desde `.context/secrets/replicate-api-token`. No hay reenvíos automáticos de pagos.
El resultado conserva dimensiones exactas y usa alfa original interpolado; queda
como variante para comparar, sin sustituir trabajo manual automáticamente.
Desde su revisión se puede aplicar y editar en Confite, o elegir **Limpiar este
escalado con ImageLab…**. Ese envío usa el escalado y el original intacto como
referencia de pose, paleta y línea; no garantiza fidelidad artística.

El botón **Historial** dentro de Confite guarda primero el trabajo actual, muestra
versiones PNG con vista previa y restaura también el offset de esa versión.
Restaurar conserva el PNG reemplazado como otra versión. El primer guardado
también respalda el master. Las capas requieren guardar el proyecto `.confite`.
Original y magenta son capas de referencia: aunque estén visibles, no se incluyen
en **Guardar borrador** del taller.

## Pruebas automatizadas

`python -m unittest discover -s tests -v`

El servidor escucha solo en 127.0.0.1, valida rutas, origen, dimensiones y checksums PNG, guarda de forma atómica y verifica revisiones para evitar sobrescrituras entre ventanas.
