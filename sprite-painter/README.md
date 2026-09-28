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

Para generar solo el dibujo, elegí un modelo **ImageLab**, **Base: Original**, tu
prompt y **Alpha después · conservar fondo** (predeterminado). Hace una sola
generación, conserva el fondo y no aplica la máscara original. El resultado se
adapta al tamaño del asset y queda en el historial como **alpha pendiente**;
el control de fidelidad se pospone hasta tener transparencia.
Al seleccionar ese resultado, **Extraer alpha · ImageLab** crea otra versión
sin volver a generar el color. Esa extracción consume ImageLab por separado.
También podés resolver la transparencia manualmente en Confite. El modo
**Extraer alpha con ImageLab** hace ambas etapas automáticamente si lo elegís.

La comparación separa **Versiones** y **Generar**. En Generar elegí la técnica
(escalado o redibujo con prompt) y después el motor/modelo. La tarjeta azul
**BASE** identifica la imagen que se modifica; **REFERENCIA · original** muestra
la guía fija de pose, paleta y trazo. Seleccionar una versión también permite
usarla como base de un redibujo.

Las herramientas se agrupan en **Bordes**, **Transparencia** y **Contornos**.
Recortar y oscurecer son acciones independientes; Ajustes controla cantidad y
protecciones. Quitar magenta no hereda recorte ni tinte. ImageLab y Bria pueden
extraer alpha de cualquier versión seleccionada, conservando RGB y dimensiones;
son procesos pagos separados. Las técnicas locales no consumen créditos.

Cada versión terminada tiene botones para descargar PNG y copiar la imagen al
portapapeles (requiere soporte/permisos del navegador). **Subir PNG** o arrastrar
archivos sobre la comparación agrega versiones sin reemplazar el asset en uso.
Admite hasta 16 PNG por carga, 32 MB por archivo, con las dimensiones exactas que
indica la zona de importación; no deforma ni recorta imágenes silenciosamente.

El botón **Historial** dentro de Confite guarda primero el trabajo actual, muestra
versiones PNG con vista previa y restaura también el offset de esa versión.
Restaurar conserva el PNG reemplazado como otra versión. El primer guardado
también respalda el master. Las capas requieren guardar el proyecto `.confite`.
Original y magenta son capas de referencia: aunque estén visibles, no se incluyen
en **Guardar borrador** del taller.

## Selección de assets y acciones por lote

En la grilla, las casillas seleccionan assets sin aprobarlos. **Shift + clic**
marca un rango, **Ctrl/Cmd + clic** alterna un asset y **Seleccionar** permite
marcar con clic sobre cualquier tarjeta. Arrastrar sigue moviendo el canvas.
**Visibles** suma los que están en pantalla; **Todo el listado** o **Ctrl/Cmd+A**
suma todos los filtrados. **Espacio** marca el asset recorrido con las flechas.
**Quitar selección** deja el lote vacío; **Terminar selección** o **Esc** vuelve
a las acciones sobre el listado. Abrir un detalle conserva la selección.

Mientras hay modo de selección, aprobar, limpiar, rehacer y analizar listado
sólo toman los marcados. Los conteos excluyen los no elegibles para cada acción.
Cambiar filtros conserva la selección e indica cuántos quedaron fuera del filtro.
Ninguna selección vacía se convierte automáticamente en un lote de todo el listado.

La grilla recibe cambios en vivo del servidor: generación terminada, versión
aplicada, guardado y aprobación. Se sincroniza también entre ventanas, conservando
selección, filtros, zoom y desplazamiento. Las miniaturas se cachean por versión;
una nueva imagen cambia su URL. Si se corta la conexión, se recupera el estado al
reconectar y se usa una consulta periódica de respaldo. Una generación pendiente
de revisión no reemplaza automáticamente la versión en uso.

## Pruebas automatizadas

`python -m unittest discover -s tests -v`

`node --test tests/test-asset-selection.cjs tests/test-imagelab-ui.cjs tests/test-live-assets.cjs tests/test-sequences.cjs`

## Secuencias y lotes

En **Secuencias**, cada tarjeta reúne los cuadros del mismo traje/recurso, ordenados
por número. No reconstruye las acciones de los scripts del juego. Marcar una
secuencia incluye todos sus cuadros, incluso los ocultos por un filtro. **Cuadros**
abre el grupo; **Secuencias** vuelve conservando filtros y posición.

La selección muestra **Generar · Wonder ×4 → Bria**, **Alpha**, **Bordes**,
**Avanzado** y **Aprobar selección**. Generar envía directamente los originales a
Wonder y Bria; consume créditos. Incluye los seleccionados aprobados, omite los
que están en proceso o no tienen original. Alpha/Bordes usan la versión en uso de
cada cuadro; Avanzado permite cambiar motor, prompt y base. Los lotes crean
versiones para revisar y no las aplican automáticamente. Detener envío conserva
los trabajos que ya entraron en la cola.

Abrir un asset desde la grilla crea otra pestaña, preservando posición, filtros y
selección de la grilla. El enlace `?asset=…&version=…` permite recargar el detalle.
En el detalle, **Generar** envía a Wonder ×4 → Bria; **Avanzado** contiene los demás
modelos y la generación con prompt.

El servidor escucha solo en 127.0.0.1, valida rutas, origen, dimensiones y checksums PNG, guarda de forma atómica y verifica revisiones para evitar sobrescrituras entre ventanas.
