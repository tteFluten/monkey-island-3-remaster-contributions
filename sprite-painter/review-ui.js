'use strict';
// Icons are bundled Lucide SVGs (ISC, see LUCIDE-LICENSE); no CDN dependency.
const ReviewUI={
  icons:{},
  icon(name){const span=document.createElement('span');span.className='ar-icon';span.setAttribute('aria-hidden','true');span.dataset.icon=name;span.innerHTML=this.icons[name]||'';return span;},
  button(label,icon,handler,className='ar-icon-button'){
    const button=document.createElement('button');button.type='button';button.className=className;
    button.title=label;button.setAttribute('aria-label',label);button.append(this.icon(icon));button.onclick=handler;return button;
  },
  async blob(url){const response=await fetch(url);if(!response.ok)throw new Error('No se pudo cargar el PNG.');return new Blob([await response.arrayBuffer()],{type:'image/png'});},
  async download(url,filename){
    const blob=await this.blob(url),href=URL.createObjectURL(blob),link=document.createElement('a');
    link.href=href;link.download=filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(href),30000);
  },
  async copy(url){
    if(!navigator.clipboard?.write||typeof ClipboardItem==='undefined')throw new Error('Este navegador no permite copiar imágenes. Usá Descargar PNG.');
    // Pass a promise while the user gesture is still active (needed by WebKit).
    await navigator.clipboard.write([new ClipboardItem({'image/png':this.blob(url)})]);
  },
  dataURL(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('No se pudo leer el PNG.'));reader.readAsDataURL(file);});},
  tools(host,run,getSource){
    const localTechniques=new Set(['trim','tint','magenta','outline']);
    const section=document.createElement('section');section.className='ar-toolbox';section.setAttribute('aria-label','Herramientas de la versión');
    section.innerHTML='<div class="ar-toolbox-heading"><strong>Herramientas</strong><small>Preview en vivo · OK para guardar</small></div><div class="ar-tool-groups"></div><div class="ar-tool-settings"></div><div class="ar-tool-preview-bar" hidden><button data-preview-ok class="accent">OK · Guardar versión</button><button data-preview-cancel>Cancelar</button><span data-preview-status role="status"></span></div><p class="ar-tool-feedback" role="status" hidden></p>';
    const groups=section.querySelector('.ar-tool-groups'),settings=section.querySelector('.ar-tool-settings'),previewBar=section.querySelector('.ar-tool-preview-bar');
    settings.innerHTML='<label data-group="trim">Recortar <input data-trim type="range" min="0" max="3" step="0.25" value="0.5"><output>0.5 px</output></label><label data-group="tint">Oscurecer <input data-tint type="range" min="0" max="100" step="5" value="70"><output>70%</output></label><label data-group="edge"><input data-dark type="checkbox" checked> Proteger trazo oscuro</label><label data-group="edge" title="Evita modificar los cortes rectos que empalman con otra pieza del sprite."><input data-seams type="checkbox" checked> Proteger empalmes</label><label data-group="outline">Color <select data-outline-color><option value="ffffff">Blanco</option><option value="ff3b0f">Rojo</option><option value="000000">Negro</option></select></label><label data-group="outline">Radio <input data-outline-radius type="range" min="1" max="8" step="1" value="2"><output>2 px</output></label>';
    // Wire slider outputs
    for(const input of settings.querySelectorAll('input[type=range]')){const out=input.nextElementSibling;const update=()=>{out.textContent=input.value+' px';};input.addEventListener('input',update);}
    settings.hidden=true;
    let previewMode=null,previewTimer=null,previewAbort=null;
    function outlineSettings(){return {color:settings.querySelector('[data-outline-color]').value,radius:Number(settings.querySelector('[data-outline-radius]').value)};}
    function previewUrl(){
      const src=getSource();if(!src||!src.id)return null;
      const s=currentSettings();
      const params=new URLSearchParams({id:src.id,trim:s.trim_pixels,tint:s.tint_strength,dark:s.protect_dark?'1':'0',seams:s.protect_seams?'1':'0',magenta:previewMode==='magenta'?'1':'0'});
      if(src.job_id)params.set('job_id',src.job_id);
      if(src.history)params.set('history',src.history);
      if(previewMode==='outline'){const ol=outlineSettings();params.set('outline','custom');params.set('outline_color',ol.color);params.set('outline_radius',ol.radius);}
      return '/api/preview/alpha?'+params;
    }
    function requestPreview(){
      clearTimeout(previewTimer);if(previewAbort)previewAbort.abort();
      const url=previewUrl();if(!url)return;
      const status=previewBar.querySelector('[data-preview-status]');
      status.textContent='Calculando…';status.className='ar-preview-loading';
      previewAbort=new AbortController();
      fetch(url,{signal:previewAbort.signal}).then(r=>{if(!r.ok)throw new Error('Error');return r.blob();}).then(blob=>{
        const objUrl=URL.createObjectURL(blob);
        section.dispatchEvent(new CustomEvent('preview-update',{detail:{url:objUrl}}));
        status.textContent='Preview listo';status.className='';
      }).catch(e=>{if(e.name!=='AbortError'){status.textContent='Error en preview';status.className='ar-preview-error';}});
    }
    function debouncedPreview(){clearTimeout(previewTimer);previewTimer=setTimeout(requestPreview,120);}
    function currentSettings(){return {trim_pixels:Number(settings.querySelector('[data-trim]').value),tint_strength:Number(settings.querySelector('[data-tint]').value)/100,protect_dark:settings.querySelector('[data-dark]').checked,protect_seams:settings.querySelector('[data-seams]').checked};}
    // Live update on any setting change
    for(const input of settings.querySelectorAll('input,select')){input.addEventListener('input',()=>{if(previewMode)debouncedPreview();});input.addEventListener('change',()=>{if(previewMode)debouncedPreview();});}
    const settingGroups={trim:['trim'],tint:['tint'],magenta:['edge'],outline:['outline']};
    function enterPreview(technique){
      previewMode=technique;previewBar.hidden=false;
      const visible=new Set(settingGroups[technique]||[]);
      for(const el of settings.querySelectorAll('[data-group]'))el.hidden=!visible.has(el.dataset.group);
      settings.hidden=visible.size===0;
      for(const b of buttons)b.classList.toggle('ar-tool-active',b.dataset.technique===technique);
      requestPreview();
    }
    function exitPreview(){
      previewMode=null;previewBar.hidden=true;settings.hidden=false;clearTimeout(previewTimer);if(previewAbort)previewAbort.abort();
      for(const b of buttons)b.classList.remove('ar-tool-active');
      for(const el of settings.querySelectorAll('[data-group]'))el.hidden=false;
      section.dispatchEvent(new CustomEvent('preview-update',{detail:{url:null}}));
    }
    previewBar.querySelector('[data-preview-cancel]').onclick=exitPreview;
    previewBar.querySelector('[data-preview-ok]').onclick=()=>{const technique=previewMode;exitPreview();run(technique);};
    const specs=[
      ['Bordes',[
        ['trim','Quitar borde','Preview','scissors','Recorta el halo semitransparente del contorno.'],
        ['tint','Oscurecer halo','Preview','paintbrush','Tiñe el halo con tinta oscura cercana.']]],
      ['Transparencia',[
        ['alphaoriginal','Alpha del original','Local','scan-line','Escala el alpha del original al 4x con antialiasing. Sin AI, sin créditos.'],
        ['imagelab','Crear alpha','ImageLab','wand-sparkles','Extrae alpha con ImageLab. Consume créditos.'],
        ['bria','Crear alpha','Bria','scan-line','Extrae alpha con Bria / Replicate.'],
        ['magenta','Quitar magenta','Preview','pipette','Elimina el fondo magenta conectado al exterior.']]],
      ['Contornos',[
        ['outline','Agregar contorno','Preview','circle','Agrega un borde sólido con antialias. Elegí color y radio.']]]
    ];
    const buttons=[];
    for(const [name,items] of specs){
      const group=document.createElement('section');group.className='ar-tool-group';const heading=document.createElement('h3');heading.textContent=name;
      const row=document.createElement('div');row.className='ar-tool-row';row.style.setProperty('--tool-count',items.length);
      for(const [key,label,engine,icon,description] of items){
        const handler=localTechniques.has(key)?()=>enterPreview(key):()=>run(key);
        const button=this.button(label+' · '+engine,icon,handler,'ar-tool-card');button.dataset.technique=key;button.title=description;
        const title=document.createElement('strong');title.textContent=label;const meta=document.createElement('small');meta.textContent=engine;button.append(title,meta);row.append(button);buttons.push(button);
      }
      group.append(heading,row);groups.append(group);
    }
    host.append(section);
    return {
      setDisabled(disabled){for(const b of buttons)b.disabled=disabled;},
      settings:currentSettings,outlineSettings,
      feedback(text,state='pending'){const out=section.querySelector('.ar-tool-feedback');out.textContent=text;out.dataset.state=state;out.hidden=!text;},
      section,exitPreview,isPreview(){return !!previewMode;}
    };
  }
};
fetch('/lucide-icons.json').then(r=>r.json()).then(icons=>{ReviewUI.icons=icons;for(const el of document.querySelectorAll('.ar-icon[data-icon]'))el.innerHTML=icons[el.dataset.icon]||'';}).catch(()=>{});
