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
  tools(host,run){
    const section=document.createElement('section');section.className='ar-toolbox';section.setAttribute('aria-label','Herramientas de la versión');
    section.innerHTML='<div class="ar-toolbox-heading"><strong>Herramientas</strong><small>Cada acción crea una versión</small></div><div class="ar-tool-groups"></div><div class="ar-tool-settings" hidden></div><p class="ar-tool-feedback" role="status" hidden></p>';
    const groups=section.querySelector('.ar-tool-groups'),settings=section.querySelector('.ar-tool-settings');
    settings.innerHTML='<label>Recortar <input data-trim type="number" min="0" max="3" step="0.25" value="0.5" aria-label="Píxeles a recortar del borde"> px</label><label>Oscurecer <input data-tint type="number" min="0" max="100" step="10" value="70" aria-label="Intensidad de tinte del borde"> %</label><label><input data-dark type="checkbox" checked> Proteger trazo oscuro</label><label title="Evita modificar los cortes rectos que empalman con otra pieza del sprite."><input data-seams type="checkbox" checked> Proteger empalmes</label>';
    const adjust=this.button('Ajustes de borde','sliders-horizontal',()=>{settings.hidden=!settings.hidden;adjust.setAttribute('aria-expanded',String(!settings.hidden));},'ar-settings-button');
    adjust.append(document.createTextNode('Ajustes'));adjust.setAttribute('aria-expanded','false');section.querySelector('.ar-toolbox-heading').append(adjust);
    const specs=[
      ['Bordes',[
        ['trim','Quitar borde','Local · recorte','scissors','Reduce el contorno transparente. No tiñe ni cambia el interior.'],
        ['tint','Oscurecer halo','Local · tinte','paintbrush','Tiñe el halo con tinta oscura cercana. No recorta la silueta.']]],
      ['Transparencia',[
        ['imagelab','Crear alpha','ImageLab · créditos','wand-sparkles','Extrae alpha con ImageLab sin regenerar el dibujo. Consume ImageLab.'],
        ['bria','Crear alpha','Bria · Replicate','scan-line','Extrae alpha con Bria. Conserva RGB y tamaño; consume Replicate.'],
        ['magenta','Quitar magenta','Local · chroma','pipette','Elimina el fondo magenta y descontamina su borde. Sin créditos.']]],
      ['Contornos',[
        ['white-2','Borde blanco','Local · 2 px','circle','Agrega un borde blanco exterior de 2 px sin agrandar el lienzo.'],
        ['red-4','Borde rojo','Local · 4 px','circle','Agrega un borde rojo exterior de 4 px sin agrandar el lienzo.']]]
    ];
    const buttons=[];
    for(const [name,items] of specs){
      const group=document.createElement('section');group.className='ar-tool-group';const heading=document.createElement('h3');heading.textContent=name;
      const row=document.createElement('div');row.className='ar-tool-row';row.style.setProperty('--tool-count',items.length);
      for(const [key,label,engine,icon,description] of items){
        const button=this.button(label+' · '+engine,icon,()=>run(key),'ar-tool-card');button.dataset.technique=key;button.title=description;
        const title=document.createElement('strong');title.textContent=label;const meta=document.createElement('small');meta.textContent=engine;button.append(title,meta);row.append(button);buttons.push(button);
      }
      group.append(heading,row);groups.append(group);
    }
    host.append(section);
    return {
      setDisabled(disabled){for(const b of buttons)b.disabled=disabled;},
      settings(){return {trim_pixels:Number(settings.querySelector('[data-trim]').value),tint_strength:Number(settings.querySelector('[data-tint]').value)/100,protect_dark:settings.querySelector('[data-dark]').checked,protect_seams:settings.querySelector('[data-seams]').checked};},
      feedback(text,state='pending'){const out=section.querySelector('.ar-tool-feedback');out.textContent=text;out.dataset.state=state;out.hidden=!text;},
      section
    };
  }
};
fetch('/lucide-icons.json').then(r=>r.json()).then(icons=>{ReviewUI.icons=icons;for(const el of document.querySelectorAll('.ar-icon[data-icon]'))el.innerHTML=icons[el.dataset.icon]||'';}).catch(()=>{});
