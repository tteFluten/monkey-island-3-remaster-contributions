# Continuación del refinador · 27 de septiembre de 2026

Branch de código: `codex/confite-refinador`. La entrega de imágenes vive separada
en `scene-1-ship-v1`. La aplicación local se sirve desde
`D:\monkey-island-3-remaster-4k\sprite-painter`, puerto 5215. El checkout principal
puede seguir en `ragojose/scene-sprite-sheets` con numerosos assets modificados;
no hacer reset/checkout forzado ni incluirlos en commits del editor.

## Cambios recientes

- Sincronización SSE entre pestañas: cambios de versión, miniaturas y aprobaciones.
- Vista Assets/Secuencias por el `frame.group` existente (traje/recurso), selección
  completa incluso con filtros, y navegación al grupo con regreso conservado.
- Acciones visibles para selección: generación directa Wonder ×4 → Bria,
  alpha por Bria o ImageLab, limpieza, magenta, contornos, modelos avanzados y
  aprobación. Generar incluye aprobados seleccionados; no aplica resultados.
- Detalle en pestaña separada y URL persistente de asset/versión.
- Detalle: Versiones / Generar (Wonder directo) / Avanzado.

## Implementación y pruebas

`asset-browser.js` conserva selección y canvas; `sequence-tools.js` construye
grupos y recetas de lote; `asset-review.js` maneja el detalle. `live-assets.js` y
`live_updates.py` sincronizan vistas sin volver a cargar todo el catálogo.

Pruebas: 76 de Python y 10 de Node. Ver comandos en README. UI verificada con
servidor temporal de 10 cuadros y proveedores simulados: selección de 5 cuadros,
Wonder directo por lote, alpha por lote, detalle en otra pestaña. No se gastaron
créditos ni se modificaron assets del usuario en esas pruebas.

Las secuencias son agrupaciones de recursos; no representan necesariamente una
acción completa del juego. El flujo y los envíos fueron verificados; la calidad
artística de los proveedores requiere revisar cada resultado. Las animaciones de
agua siguen requiriendo revisión para cerrar la entrega del barco.

Los tokens de los proveedores y el historial local quedan fuera de Git. Evitar
pruebas de generación pagas o reenvíos automáticos tras respuestas inciertas.
