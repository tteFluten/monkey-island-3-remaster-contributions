# Monkey Sprite Painter

Editor local independiente para retocar PNG con tableta. No necesita npm, servicios de IA ni conexión a Internet. Requiere Python 3.11 o posterior y un navegador moderno (Chrome o Edge recomendados para tableta).

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
