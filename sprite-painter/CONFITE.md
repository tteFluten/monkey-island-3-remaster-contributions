# Confite conectado al taller de Monkey

## Mesa de assets

El taller inicia en una grilla sobre canvas con pan por arrastre, desplazamiento
con rueda y zoom con Ctrl+rueda o botones. Clic en una tarjeta abre su secuencia
directamente en Confite; **← Assets** guarda el PNG y vuelve a la posición anterior.
Cada tarjeta compara el PNG actual con su original extraído. Si falta, utiliza la
referencia previa al upscale y lo rotula **ORIGINAL · ALFA LIMPIO**. No se inventan
asociaciones para recursos sin correspondencia exacta.

Se dibujan solo tarjetas visibles, con seis descargas simultáneas y caché acotada.
Pillow genera miniaturas de hasta 240×180 con proporciones conservadas; si no está
instalado se sirven los PNG completos como alternativa menos eficiente.

Las marcas provienen de `assets/metadata/artwork-review.json`, asociadas por ruta
y hash del manifiesto: rojo para rechazados, ámbar para borradores o validación
fallida. No son una nueva evaluación visual ni un ranking numérico de daño. Los
retoques no heredan una aprobación del master; se indica que deben revisarse.
Filtros por colección, texto, revisión y retoques; orden por prioridad o secuencia.

La timeline dispone de **Onion skin ⚙**: activar/desactivar, anterior/siguiente,
colores, opacidad y alineación. Preferencias locales persistentes. Preview conserva
la relación de aspecto del canvas, sin estirar el sprite.

El taller local de `D:\monkey-island-3-remaster-4k\sprite-painter` abre Confite real
en un iframe del mismo origen. No requiere MCP ni un segundo servicio para pintar.
Compilar desde `confite`: `node node_modules/vite/bin/vite.js build --mode sprite`.
El HTML autónomo se genera en `artifacts/monkey-sprite-painter-build/confite`.
En Monkey, `sprite-painter/Actualizar Confite.ps1` reconstruye y copia ese HTML.
Los builds quedan ignorados por Git. El código de Confite permanece en Basement.

## Flujo

1. Elegir un cuadro en la biblioteca y pulsar **Retocar en Confite**.
2. Usar pinceles, presión, capas, máscaras y deshacer de Confite. El onion skin
   muestra hasta dos vecinos alineados por los pies, solo como referencia.
3. **Ctrl+S** guarda un borrador PNG en el taller con su historial y revisión.
4. **Guardar y volver a preview** devuelve el resultado al comparador y reproductor.

La timeline de Monkey permanece visible abajo mientras se pinta en Confite.
Las miniaturas, **Anterior/Siguiente** y **Alt + flecha izquierda/derecha** cambian
de cuadro guardando primero el PNG, sin recargar el iframe. **Preview** reproduce
en el panel inferior derecho; allí se ajustan FPS y rango Desde/Hasta.
Cambiar de cuadro carga su PNG aplanado: guardar `.confite` antes del cambio si
se necesita conservar una estructura de capas. El guardado fallido bloquea el salto.

Se conserva el alfa y se rechazan cambios de dimensiones. Los originales y masters
no se reemplazan. Si hay un conflicto de revisión, el editor permanece abierto
con el trabajo. La conexión trabaja sobre un cuadro: la secuencia se controla
desde la biblioteca, no se importa como animación de Confite. Los números de cels
no representan por sí solos las animaciones del motor SCUMM.

El borrador del taller es un PNG aplanado. Para conservar capas, guardar también
un `.confite` mediante **Save project** antes de volver al taller. No hay autosave
de documentos por capas en esta primera conexión. La presión requiere comprobarse
con una tableta física. Los vecinos de tamaño distinto pueden quedar recortados
en el lienzo actual; no alteran la exportación.

## Contrato local

## Comparación y variantes

En la revisión de una variante, **Usar esta configuración en el botón directo**
copia su prompt, modelo, ejemplo y método de alfa a las preferencias de ese asset.
La cola muestra modelo/ejemplo/alfa para auditar el envío. Se migran prompts
predeterminados antiguos sin alterar instrucciones personalizadas. Validación del
botón real para frame 26: trabajo `54c5b65aeb5236cdea2f7586`, referencia frame 45,
alfa IA, PNG 140×60. No implica validación de otros cels ni aprobación automática.

El modo predeterminado de transparencia es **IA · extraer del resultado**. Reutiliza
el enfoque de Gemini de Basement Alpha Extractor (matte blanco/negro), mediante un
segundo llamado a `imagelab-generate` del MCP. No utiliza la ruta HTTP de sesión de
Alpha Extractor ni el removedor Replicate. Guarda la máscara en `alpha.png`, valida
proporciones/fondo y la adapta con el mismo viewport que el color. No impone el
contorno original sobre el dibujo generado. **Reextraer alfa con IA** crea otra
variante del mismo color, sin repetir la generación del dibujo. Cada extracción
consume un llamado adicional al proveedor. El contorno local sigue disponible.

`spriteprep.py` reconstruye contornos a partir del alfa, simplifica polígonos,
conserva huecos/componentes y rasteriza con antialias dentro del bounding box
original. Los efectos con alfa complejo conservan interpolación suave. La base
de color usa interpolación bicúbica y un filtrado ligero para evitar inducir pixel
art. ImageLab recibe instrucciones de reconstruir superficies pintadas continuas.
Validación visual inicial: tres generaciones del cuadro 26, usando el cuadro 45
aprobado como referencia; la tercera conserva un acabado oscuro y bordes continuos.
La simplificación es geométrica, no reconocimiento semántico universal; revisar
detalles finos y cada variante antes de aprobarla.

Preparación `square-v1`: el original se amplía sin suavizado dentro de un lienzo
1024×1024 con fondo gris y margen, y se guarda su viewport. Se pide a ImageLab una
salida cuadrada. La adaptación recupera ese mismo viewport normalizado y el alfa
original; ya no hace `contain` sobre el objeto generado. Una proporción de salida
incompatible se rechaza. Esto verifica geometría del lienzo, no fidelidad visual.
En ⚙ puede elegirse explícitamente una referencia aprobada, ver la base preparada
y guardar prompt/modelo/referencia por asset para los envíos directos siguientes.

La grilla destaca En cola, Generando y Resultado listo. **Aprobar como referencia**
en un asset guarda el PNG actual; en la cola aprueba la variante sin aplicarla.
La aprobación conserva una copia por hash en `.context/sprite-painter/imagelab/references`
y persiste en `references.json`. Ediciones posteriores no alteran esa copia. Se
puede retirar desde la grilla. Nuevos trabajos consideran estas copias como
referencias de estilo de la misma secuencia, además de los masters ya aceptados;
las peticiones que estaban en cola conservan sus referencias originales.

Las nuevas generaciones usan exclusivamente el original asociado como sujeto y
su máscara de transparencia. El master defectuoso no se envía. Si falta el original
o sus proporciones no coinciden, el envío se bloquea. Opcionalmente se busca un
master `accepted` de la misma secuencia con hash vigente, cel cercano y proporciones
similares: se envía solo como `style ref`. Si no existe, se utiliza únicamente el
original. Es una selección por metadatos, no una garantía de semejanza semántica.
Los trabajos previos conservan sus resultados y se identifican como flujo anterior.

**Agregar a la cola** guarda el envío y vuelve a la grilla para continuar con otros
assets. **Cola ImageLab** muestra pendientes, generación activa, resultados y errores
con comparativas del PNG enviado y la variante. Procesa un trabajo a la vez en orden
de envío; permite quitar pendientes. Los pendientes se retoman al iniciar el servidor.
Una generación interrumpida nunca se reintenta automáticamente. El servidor local
debe permanecer abierto para procesar; cerrar la pestaña no detiene la cola.

La capa **Original** acompaña al cuadro de la timeline. Se carga arriba del sprite,
oculta y bloqueada, ampliada sin suavizado y conservando las proporciones. Se puede
mostrar desde Layers para comparar y desbloquear para editar o duplicar. Si solo
existe la referencia con alfa limpio, se identifica como tal. Es una capa normal:
si se deja visible, participa en la exportación. Se recrea al cambiar de cuadro;
guardar `.confite` para conservar la estructura de capas del documento.

Debajo del sprite se agrega **Fondo magenta · contraste**, relleno `#ff00ff`,
oculto y bloqueado por defecto. Su ojo permite inspeccionar transparencia y bordes.
Como cualquier capa normal, participa en el PNG si se deja visible al guardar.

Cada tarjeta de la grilla ofrece **Editar en Confite** y **Retocar con ImageLab**.
ImageLab usa el MCP configurado en `.mcp.json` del proyecto o de Basement y el SDK
instalado en `app` o `hub`. Permite elegir modelo e instrucciones. Generar envía
las referencias al proveedor y puede consumir créditos. El resultado se guarda
aparte en `.context/sprite-painter/imagelab`; se aplica únicamente al pulsar
**Usar variante y editar en Confite**. Se conserva la salida del proveedor y una
variante ajustada sin estirar al tamaño del sprite, con alfa protegido por defecto.
Revisar encuadre y alineación antes de adoptarla. Una variante anterior no puede
sobrescribir un retoque más reciente. Las pruebas usan un proveedor simulado.

`lib/spriteBridge.ts` se activa únicamente con `?spriteBridge=1` dentro de un iframe.
Todos los mensajes verifican padre, origen y sesión. Eventos: `CONFITE_SPRITE_READY`,
`OPEN`, `LOADED`, `EXPORT`, `PNG`, `ONION`, `ERROR` (los últimos usan el mismo prefijo).
La aplicación anfitriona conserva rutas, revisiones y permisos; Confite recibe PNGs,
no acceso al disco. El guardado usa la API existente del taller.

Un MCP futuro puede exponer catálogo, apertura de cuadros, inspección y exportación
usando este contrato y una cola de comandos local. No está implementado: no hace
falta para el flujo manual y no se debe transmitir cada trazo a través de MCP.
