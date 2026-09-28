from __future__ import annotations


def review_portal_html(token: str) -> str:
    safe_token = token.replace("\\", "").replace("'", "").replace('"', "")
    return f"""<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"referrer\" content=\"no-referrer\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>CONN Pilot review</title>
<style>
body{{margin:0;background:#f5f7fb;color:#18212f;font:15px system-ui}}header,main{{max-width:1180px;margin:auto;padding:20px}}
header{{display:flex;justify-content:space-between;align-items:center}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}}
.card{{background:white;border:1px solid #dfe5ee;border-radius:12px;padding:16px;box-shadow:0 2px 10px #1831530d}}
img{{width:100%;height:auto;border-radius:8px;border:1px solid #e5e9f0}}button{{padding:9px 13px;margin:4px;border:0;border-radius:8px;cursor:pointer}}
.accept{{background:#d9f7e5}}.exclude{{background:#ffe2e0}}.review{{background:#fff0c2}}input,textarea{{width:100%;box-sizing:border-box;padding:8px;margin:6px 0}}
code{{word-break:break-all}}.status{{padding:4px 8px;border-radius:999px;background:#e8eef9}}table{{width:100%;border-collapse:collapse}}td{{border-top:1px solid #edf0f4;padding:7px}}
.pipeline{{display:flex;align-items:stretch;gap:8px;overflow:auto;padding:4px 0 10px}}.node{{min-width:145px;background:#eef4ff;border-radius:10px;padding:10px}}.arrow{{align-self:center;color:#65758b}}
</style></head><body><header><div><h1>CONN Pilot</h1><div id=meta>Cargando revisión…</div></div><span id=status class=status></span></header>
<main><section class=card><h2>Pipeline ejecutado</h2><div id=pipeline class=pipeline></div></section><section class=card><h2>Muestra y segundo nivel</h2><div id=sample></div><button id=recalc>Recalcular segundo nivel</button><button id=package>Generar paquete reproducible</button><a id=download hidden>Descargar paquete</a></section>
<h2>Sujetos</h2><div id=subjects class=grid></div><section class=card><h2>Aceptación científica</h2><textarea id=rationale placeholder=\"Justificación científica\"></textarea>
<button onclick=scientific('accept') class=accept>Aceptar análisis</button><button onclick=scientific('needs_review') class=review>Requiere revisión</button><button onclick=scientific('reject') class=exclude>Rechazar</button></section></main>
<script>
const token='{safe_token}', api=`/review-api/${{token}}`; let state;
async function call(path='', options={{}}){{const r=await fetch(api+path,{{headers:{{'content-type':'application/json'}},...options}});const j=await r.json();if(!r.ok)throw Error(j.error||'Error');return j}}
function esc(x){{return String(x??'').replace(/[&<>\"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]))}}
async function load(){{state=await call();const d=state.data;document.querySelector('#meta').innerHTML=`Trabajo <code>${{esc(d.job_id)}}</code> · resultado <code>${{esc(d.result_version)}}</code>`;document.querySelector('#status').textContent=d.review.second_level.status;
const nodes=d.pipeline_graph?.nodes||[];document.querySelector('#pipeline').innerHTML=nodes.map((n,i)=>`${{i?'<span class=arrow>→</span>':''}}<div class=node><strong>${{esc(n.category)}}</strong><br>${{esc(n.id)}}<br><small>v${{esc(n.version)}} · ${{esc(n.status)}}</small></div>`).join('');
const s=d.review.sample;document.querySelector('#sample').innerHTML=`<p>Incluidos: ${{esc(s.included_subject_ids.join(', '))}}</p><p>Excluidos: ${{esc(s.excluded_subject_ids.join(', ')||'ninguno')}}</p><p><code>${{esc(s.version)}}</code></p>`;
document.querySelector('#subjects').innerHTML=d.review.subject_quality.subjects.map(subjectCard).join('');}}
function subjectCard(s){{const images=(s.art_images||[]).map(a=>`<figure><img src=\"${{esc(a.download_url)}}\"><figcaption>${{esc(a.metadata?.qc_type||a.name)}}</figcaption></figure>`).join('');return `<article class=card><h3>${{esc(s.subject_id)}}</h3>${{images}}<table>${{Object.entries(s.metrics||{{}}).map(([k,v])=>`<tr><td>${{esc(k)}}</td><td>${{esc(v)}}</td></tr>`).join('')}}</table><textarea id=\"why-${{esc(s.subject_id)}}\" placeholder=\"Justificación obligatoria al excluir\"></textarea><button class=accept onclick=decide('${{esc(s.subject_id)}}','accept')>Aceptar</button><button class=review onclick=decide('${{esc(s.subject_id)}}','needs_review')>Revisar</button><button class=exclude onclick=decide('${{esc(s.subject_id)}}','exclude')>Excluir</button><p>Actual: ${{esc(s.decision?.decision||'sin decidir')}}</p></article>`}}
async function decide(id,decision){{await call('/decision',{{method:'POST',body:JSON.stringify({{result_version:state.data.result_version,subject_id:id,decision,justification:document.querySelector(`#why-${{id}}`).value}})}});await load()}}
document.querySelector('#recalc').onclick=async()=>{{await call('/recalculate',{{method:'POST',body:JSON.stringify({{result_version:state.data.result_version,sample_version:state.data.review.sample.version}})}});await load()}};
document.querySelector('#package').onclick=async()=>{{const j=await call('/package',{{method:'POST',body:JSON.stringify({{result_version:state.data.result_version,sample_version:state.data.review.sample.version}})}});const a=document.querySelector('#download');a.href=j.data.download_url;a.hidden=false;a.textContent='Descargar ZIP'}};
async function scientific(decision){{await call('/scientific',{{method:'POST',body:JSON.stringify({{result_version:state.data.result_version,sample_version:state.data.review.sample.version,decision,rationale:document.querySelector('#rationale').value}})}});await load()}}
load().catch(e=>document.querySelector('#meta').textContent=e.message);
</script></body></html>"""
