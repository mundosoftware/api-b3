PROMOTION_PANEL_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Trade Alert Promotions</title>
  <style>
    :root { color-scheme: light dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; background: #0b1020; color: #eef2ff; }
    header { padding: 24px max(24px, calc((100vw - 1280px)/2)); background: #111831; display:flex; gap:16px; align-items:center; justify-content:space-between; }
    h1,h2 { margin:0; } .muted { color:#aab3d1; } main { max-width:1280px; margin:0 auto; padding:24px; }
    .grid { display:grid; grid-template-columns: minmax(280px, .8fr) minmax(420px, 1.6fr); gap:20px; }
    .card { background:#141c36; border:1px solid #293354; border-radius:16px; padding:18px; box-shadow:0 12px 35px #0004; }
    .stats { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:16px 0; }
    .stat { padding:12px; background:#0e152b; border-radius:12px; } .stat strong { display:block; font-size:1.4rem; }
    label { display:block; font-size:.84rem; color:#b7c1df; margin:12px 0 5px; }
    input,textarea,select,button { font:inherit; } input,textarea,select { width:100%; box-sizing:border-box; padding:10px 12px; border-radius:10px; border:1px solid #354267; background:#0d1428; color:#fff; }
    textarea { min-height:82px; resize:vertical; } input[type=checkbox] { width:auto; accent-color:#7c9cff; }
    .checks { display:flex; flex-wrap:wrap; gap:14px; margin:14px 0; } .checks label { margin:0; display:flex; gap:7px; align-items:center; }
    button { border:0; border-radius:10px; padding:10px 14px; background:#6f8cff; color:white; font-weight:700; cursor:pointer; }
    button.secondary { background:#293554; } button.danger { background:#a83d55; }
    .toolbar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin:14px 0; }
    .promo { padding:14px; border:1px solid #334064; border-radius:12px; margin-top:10px; cursor:pointer; }
    .promo.active { border-color:#7c9cff; background:#1c294d; }
    table { width:100%; border-collapse:collapse; font-size:.88rem; } th,td { text-align:left; padding:10px 8px; border-bottom:1px solid #2b3658; vertical-align:top; } th { color:#b8c3e2; }
    code { font-family:ui-monospace,monospace; } .pill { display:inline-block; padding:3px 8px; border-radius:999px; background:#293554; }
    #toast { position:fixed; right:20px; bottom:20px; max-width:440px; padding:13px 16px; border-radius:12px; background:#21305b; display:none; box-shadow:0 10px 30px #0008; }
    @media(max-width:850px){ .grid{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)} table{display:block;overflow:auto} }
  </style>
</head>
<body>
<header><div><h1>Promotions</h1><div class="muted">Reusable App Store offer-code control panel</div></div><button class="secondary" id="tokenButton">Admin token</button></header>
<main>
  <div class="grid">
    <section class="card"><div class="toolbar"><h2 style="margin-right:auto">Campaigns</h2><button class="secondary" id="newPromotion">New</button></div><div id="promotions"></div></section>
    <section class="card" id="editor" hidden>
      <h2 id="editorTitle">Promotion</h2>
      <div class="stats" id="stats"></div>
      <div class="checks">
        <label><input id="enabled" type="checkbox"> Enabled</label>
        <label><input id="show_on_home" type="checkbox"> Home modal</label>
        <label><input id="allow_home_suppression" type="checkbox"> Allow “don’t show again”</label>
        <label><input id="show_on_paywall" type="checkbox"> Plans/paywall</label>
      </div>
      <div class="grid">
        <div><label>Name</label><input id="name"><label>Product ID</label><input id="product_id"><label>Brazil price</label><input id="promotional_price_brl" type="number" step="0.01"><label>Discount %</label><input id="discount_percent" type="number" step="0.01"></div>
        <div><label>Starts at (ISO 8601)</label><input id="starts_at"><label>Ends at (ISO 8601)</label><input id="ends_at"><label>Portuguese title</label><input id="title_pt"><label>English title</label><input id="title_en"></div>
      </div>
      <label>Portuguese body</label><textarea id="body_pt"></textarea><label>English body</label><textarea id="body_en"></textarea>
      <div class="grid"><div><label>CTA (PT)</label><input id="cta_pt"><label>Home suppression label (PT)</label><input id="home_suppression_label_pt"><label>Plans notice (PT)</label><textarea id="plans_notice_pt"></textarea></div><div><label>CTA (EN)</label><input id="cta_en"><label>Home suppression label (EN)</label><input id="home_suppression_label_en"><label>Plans notice (EN)</label><textarea id="plans_notice_en"></textarea></div></div>
      <div class="toolbar"><button id="save">Save settings</button><span class="muted" id="updated"></span></div>
    </section>
  </div>
  <section class="card" id="codesCard" hidden style="margin-top:20px">
    <div class="toolbar"><h2 style="margin-right:auto">Offer codes</h2><input id="csvFile" type="file" accept=".csv,text/csv" hidden><button class="secondary" id="importCsv">Import CSV</button><select id="statusFilter" style="width:auto"><option value="">All states</option><option>available</option><option>reserved</option><option>redeemed</option></select><button class="secondary" id="reloadCodes">Reload</button></div>
    <div class="muted">Codes are imported idempotently from the configured CSV. A redeemed row links the code to the app user and StoreKit transaction reported by the device.</div>
    <div style="overflow:auto"><table><thead><tr><th>Code</th><th>State</th><th>Enabled</th><th>Reserved user</th><th>Redeemed user</th><th>Redeemed</th><th>Transaction</th><th></th></tr></thead><tbody id="codes"></tbody></table></div>
  </section>
</main><div id="toast"></div>
<script>
const fields=['name','product_id','promotional_price_brl','discount_percent','starts_at','ends_at','show_on_home','allow_home_suppression','show_on_paywall','enabled','title_pt','title_en','body_pt','body_en','cta_pt','cta_en','home_suppression_label_pt','home_suppression_label_en','plans_notice_pt','plans_notice_en'];
let promotions=[], selected=null;
function token(){let t=localStorage.getItem('trade-alert-admin-token');if(!t){t=prompt('Enter X-Admin-Token')||'';if(t)localStorage.setItem('trade-alert-admin-token',t)}return t}
const apiPrefix=window.location.pathname.replace(/\/admin\/promotions\/?$/,'');
async function api(path,options={}){options.headers={...(options.headers||{}),'X-Admin-Token':token(),'Content-Type':'application/json'};const r=await fetch(`${apiPrefix}${path}`,options);if(!r.ok){if(r.status===401)localStorage.removeItem('trade-alert-admin-token');throw new Error(`${r.status}: ${await r.text()}`)}return r.status===204?null:r.json()}
function toast(message,bad=false){const e=document.querySelector('#toast');e.textContent=message;e.style.background=bad?'#802f46':'#21305b';e.style.display='block';setTimeout(()=>e.style.display='none',4200)}
function text(tag,value){const e=document.createElement(tag);e.textContent=value??'';return e}
async function load(){try{promotions=await api('/admin/promotions/api');renderPromotions();if(selected){selected=promotions.find(p=>p.id===selected.id)||promotions[0]}else selected=promotions[0];if(selected)select(selected.id)}catch(e){toast(e.message,true)}}
function renderPromotions(){const root=document.querySelector('#promotions');root.replaceChildren();promotions.forEach(p=>{const d=document.createElement('div');d.className='promo'+(selected?.id===p.id?' active':'');d.append(text('strong',p.name));d.append(text('div',`${p.enabled?'Enabled':'Disabled'} · ${p.available_code_count} available · ${p.redeemed_code_count} redeemed`));d.onclick=()=>select(p.id);root.append(d)})}
function select(id){selected=promotions.find(p=>p.id===id);renderPromotions();document.querySelector('#editor').hidden=false;document.querySelector('#codesCard').hidden=false;document.querySelector('#editorTitle').textContent=selected.name;fields.forEach(k=>{const e=document.querySelector('#'+k);if(!e)return;if(e.type==='checkbox')e.checked=!!selected[k];else e.value=selected[k]??''});document.querySelector('#stats').replaceChildren(...[['Total',selected.code_count],['Available',selected.available_code_count],['Reserved',selected.reserved_code_count],['Redeemed',selected.redeemed_code_count]].map(([a,b])=>{const d=document.createElement('div');d.className='stat';d.append(text('strong',b));d.append(text('span',a));return d}));document.querySelector('#updated').textContent=`Updated ${selected.updated_at}`;loadCodes()}
async function save(){const body={};fields.forEach(k=>{const e=document.querySelector('#'+k);body[k]=e.type==='checkbox'?e.checked:(e.type==='number'?Number(e.value):e.value)});try{await api(`/admin/promotions/${selected.id}`,{method:'PATCH',body:JSON.stringify(body)});toast('Promotion saved');await load()}catch(e){toast(e.message,true)}}
async function createPromotion(){const slug=prompt('Campaign slug (lowercase, for example summer-2027)');if(!slug)return;const name=prompt('Campaign name',slug)||slug;const product_id=prompt('App Store product ID','lifetime_unlock')||'lifetime_unlock';const start=new Date(),end=new Date(start.getTime()+30*86400000);try{const created=await api('/admin/promotions',{method:'POST',body:JSON.stringify({slug,name,product_id,starts_at:start.toISOString(),ends_at:end.toISOString()})});selected=created;toast('Campaign created disabled; configure it before enabling');await load()}catch(e){toast(e.message,true)}}
async function importCsv(file){if(!selected||!file)return;const rows=(await file.text()).split(/\r?\n/).filter(Boolean).map(line=>{const comma=line.indexOf(',');const code=(comma<0?line:line.slice(0,comma)).trim();const redeem_url=(comma<0?`https://apps.apple.com/redeem?ctx=offercodes&code=${encodeURIComponent(code)}`:line.slice(comma+1)).trim();return {code,redeem_url}}).filter(x=>x.code);if(!rows.length){toast('The CSV has no codes',true);return}try{const result=await api(`/admin/promotions/${selected.id}/codes/import`,{method:'POST',body:JSON.stringify({codes:rows})});toast(`Imported ${result.imported}; updated ${result.updated}`);await load()}catch(e){toast(e.message,true)}finally{document.querySelector('#csvFile').value=''}}
async function loadCodes(){if(!selected)return;try{const status=document.querySelector('#statusFilter').value;const rows=await api(`/admin/promotions/${selected.id}/codes?limit=2000${status?'&status='+encodeURIComponent(status):''}`);const root=document.querySelector('#codes');root.replaceChildren();rows.forEach(c=>{const tr=document.createElement('tr');[c.code,c.status,c.enabled?'yes':'no',c.reserved_by_user_id||'—',c.redeemed_by_user_id||'—',c.redeemed_at||'—',c.transaction_id||'—'].forEach((v,i)=>{const td=document.createElement('td');td.append(i===0?text('code',v):text('span',v));tr.append(td)});const td=document.createElement('td'),b=text('button',c.enabled?'Disable':'Enable');b.className=c.enabled?'danger':'secondary';b.onclick=async()=>{try{await api(`/admin/promotions/${selected.id}/codes/${c.id}`,{method:'PATCH',body:JSON.stringify({enabled:!c.enabled})});await load();toast('Code updated')}catch(e){toast(e.message,true)}};td.append(b);tr.append(td);root.append(tr)})}catch(e){toast(e.message,true)}}
document.querySelector('#save').onclick=save;document.querySelector('#newPromotion').onclick=createPromotion;document.querySelector('#importCsv').onclick=()=>document.querySelector('#csvFile').click();document.querySelector('#csvFile').onchange=e=>importCsv(e.target.files[0]);document.querySelector('#reloadCodes').onclick=loadCodes;document.querySelector('#statusFilter').onchange=loadCodes;document.querySelector('#tokenButton').onclick=()=>{localStorage.removeItem('trade-alert-admin-token');token();load()};load();
</script></body></html>"""
