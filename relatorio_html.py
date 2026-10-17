"""Gera a página HTML (mapa Leaflet + tabelas) a partir dos anúncios normalizados."""

import json

TEMPLATE = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Réveillon 2026 Airbnb</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
:root {
  --bg: #f7f6f3; --surface: #ffffff; --text: #1d1d1f; --muted: #6b6b70; --border: #e3e1dc;
  --accent: #d1495b; --p1: #2a9d8f; --p2: #8ab17d; --p3: #e9c46a; --p4: #e76f51;
  --serra: #6a8d73; --litoral: #2f7fb5; --ilha: #b5762f;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #141416; --surface: #1e1e21; --text: #ececee; --muted: #a0a0a8; --border: #333338;
    --serra: #8fb89a; --litoral: #6cb3e6; --ilha: #e0a35e;
  }
}
:root[data-theme="dark"] {
  --bg: #141416; --surface: #1e1e21; --text: #ececee; --muted: #a0a0a8; --border: #333338;
  --serra: #8fb89a; --litoral: #6cb3e6; --ilha: #e0a35e;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
.wrap { max-width: 1200px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 26px; margin: 0 0 4px; }
h2 { font-size: 18px; margin: 32px 0 12px; }
.sub { color: var(--muted); margin: 0 0 20px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }
.card .k { color: var(--muted); font-size: 13px; }
.card .v { font-size: 22px; font-weight: 650; font-variant-numeric: tabular-nums; }
.filters { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; margin: 20px 0 12px;
  background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px; }
.filters label { display: inline-flex; gap: 6px; align-items: center; cursor: pointer; }
.filters select, .filters input[type=range] { accent-color: var(--accent); }
select { background: var(--surface); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 4px 6px; }
#map { height: 520px; border-radius: 12px; border: 1px solid var(--border); }
.legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 13px; color: var(--muted); margin-top: 8px; }
.dot { display: inline-block; width: 11px; height: 11px; border-radius: 50%; margin-right: 5px; vertical-align: -1px; }
.tbl-wrap { overflow-x: auto; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { padding: 9px 12px; text-align: left; border-bottom: 1px solid var(--border); white-space: nowrap; }
th { font-size: 13px; color: var(--muted); font-weight: 600; cursor: pointer; user-select: none; }
th[data-k]:hover { color: var(--text); }
th.num, td.num { text-align: right; }
tr:last-child td { border-bottom: 0; }
td.t { white-space: normal; min-width: 220px; }
a { color: var(--accent); }
.tag { font-size: 12px; padding: 2px 8px; border-radius: 99px; border: 1px solid currentColor; }
.tag.serra { color: var(--serra); } .tag.litoral { color: var(--litoral); } .tag.ilha { color: var(--ilha); }
.bar { height: 8px; border-radius: 4px; background: var(--border); position: relative; min-width: 120px; }
.bar span { position: absolute; top: 0; height: 8px; border-radius: 4px; background: var(--accent); opacity: .75; }
.muted { color: var(--muted); }
.popup img { width: 220px; height: 130px; object-fit: cover; border-radius: 8px; display: block; margin-bottom: 6px; }
.popup b { display: block; margin-bottom: 2px; }
.note { font-size: 13px; color: var(--muted); margin-top: 24px; }
@media (max-width: 600px) { #map { height: 380px; } h1 { font-size: 21px; } }
</style>
</head>
<body>
<div class="wrap">
  <h1>Réveillon 2026/27 · Airbnb</h1>
  <p class="sub" id="sub"></p>

  <div class="cards" id="cards"></div>

  <div class="filters">
    <strong>Tipo:</strong>
    <label><input type="checkbox" class="f-tipo" value="serra" checked> Serra</label>
    <label><input type="checkbox" class="f-tipo" value="litoral" checked> Litoral</label>
    <label><input type="checkbox" class="f-tipo" value="ilha" checked> Ilha</label>
    <label>Check-in: <select id="f-data"><option value="">Qualquer</option></select></label>
    <label>Nota mín.: <select id="f-nota">
      <option value="0">Qualquer</option><option value="4.5">4,5+</option>
      <option value="4.7">4,7+</option><option value="4.9">4,9+</option></select></label>
    <label>Total até <b id="f-max-v"></b> <input type="range" id="f-max"></label>
  </div>

  <div id="map"></div>
  <div class="legend" id="legend"></div>

  <h2>Por destino</h2>
  <div class="tbl-wrap"><table id="t-dest"></table></div>

  <h2>Por data de check-in</h2>
  <div class="tbl-wrap"><table id="t-data"></table></div>

  <h2>Anúncios <span class="muted" id="n-anuncios"></span></h2>
  <div class="tbl-wrap"><table id="t-anuncios"></table></div>

  <p class="note" id="note"></p>
</div>

<script>
const ANUNCIOS = __ANUNCIOS__;
const CONTEXTO = __CONTEXTO__;
const META = __META__;

const brl = v => v == null ? "—" : "R$ " + Math.round(v).toLocaleString("pt-BR");
const dm = s => s.slice(8, 10) + "/" + s.slice(5, 7);
const nota = v => v == null ? "—" : v.toFixed(2).replace(".", ",");
const median = a => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y), m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

const [LO, HI] = META.faixa;
document.getElementById("sub").textContent =
  `${META.adultos} adultos · ${META.noites} noites · check-in ${META.datas.map(dm).join(", ")} · ` +
  `orçamento ${brl(META.orcamento)} (faixa ${brl(LO)}–${brl(HI)}) · gerado em ${META.gerado_em}`;

// filtros
const fData = document.getElementById("f-data");
META.datas.forEach(d => fData.add(new Option(dm(d) + " → " + META.noites + " noites", d)));
const fMax = document.getElementById("f-max");
fMax.min = Math.floor(LO); fMax.max = Math.ceil(HI); fMax.step = 50; fMax.value = Math.ceil(HI);

function priceColor(total) {
  const q = (total - LO) / (HI - LO);
  return q < .25 ? css("--p1") : q < .5 ? css("--p2") : q < .75 ? css("--p3") : css("--p4");
}

// mapa
const map = L.map("map", { scrollWheelZoom: false });
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap", maxZoom: 18 }).addTo(map);
const layer = L.layerGroup().addTo(map);
const destLayer = L.layerGroup().addTo(map);
META.destinos.forEach(d => L.circleMarker([d.lat, d.lng], { radius: 4, color: css("--muted"), weight: 1, fillOpacity: .2 })
  .bindTooltip(d.nome).addTo(destLayer));
map.fitBounds(META.destinos.map(d => [d.lat, d.lng]), { padding: [30, 30] });

document.getElementById("legend").innerHTML = [
  ["--p1", `${brl(LO)}–${brl(LO + (HI - LO) * .25)}`], ["--p2", `até ${brl(LO + (HI - LO) * .5)}`],
  ["--p3", `até ${brl(LO + (HI - LO) * .75)}`], ["--p4", `até ${brl(HI)}`]
].map(([c, t]) => `<span><span class="dot" style="background:${css(c)}"></span>${t}</span>`).join("")
  + `<span class="muted">· círculos cinza = centro dos destinos</span>`;

let sortState = { key: "score", dir: -1 };
let destSort = { key: null, dir: 1 };  // null = ordem padrão da tabela "Por destino"

function filtrados() {
  const tipos = [...document.querySelectorAll(".f-tipo:checked")].map(e => e.value);
  const data = fData.value, nmin = +document.getElementById("f-nota").value, max = +fMax.value;
  return ANUNCIOS.map(a => {
    if (!data) return a;
    const hit = a.datas.find(([d]) => d === data);
    return hit ? { ...a, checkin: data, total: hit[1], noite: hit[1] / META.noites,
      link: a.link.replace(/check_in=[^&]+&check_out=[^&]+/, `check_in=${data}&check_out=${addDays(data, META.noites)}`) } : null;
  }).filter(a => a && tipos.includes(a.tipo) && a.total <= max && (nmin === 0 || (a.nota ?? 0) >= nmin));
}
function addDays(iso, n) { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); }

function render() {
  const lista = filtrados();
  document.getElementById("f-max-v").textContent = brl(+fMax.value);

  // cards
  const tot = lista.map(a => a.total);
  const destCount = new Set(lista.map(a => a.destino)).size;
  document.getElementById("cards").innerHTML = [
    ["Opções na faixa", lista.length], ["Destinos com opções", destCount + " / " + META.destinos.length],
    ["Menor total", brl(Math.min(...tot))], ["Mediana", brl(median(tot))], ["Maior total", brl(Math.max(...tot))],
  ].map(([k, v]) => `<div class="card"><div class="k">${k}</div><div class="v">${tot.length || k.startsWith("Op") || k.startsWith("Dest") ? v : "—"}</div></div>`).join("");

  // mapa
  layer.clearLayers();
  lista.forEach(a => {
    L.circleMarker([a.lat, a.lng], { radius: 7, color: "#fff", weight: 1.5, fillColor: priceColor(a.total), fillOpacity: .95 })
      .bindPopup(`<div class="popup">${a.foto ? `<img src="${esc(a.foto)}" alt="">` : ""}
        <b>${esc(a.titulo)}</b>${esc(a.destino)} · ${esc(a.tipo)}<br>
        <b>${brl(a.total)}</b> total · ${brl(a.noite)}/noite<br>
        ★ ${nota(a.nota)} ${a.avaliacoes ? `(${a.avaliacoes})` : ""} · check-in ${dm(a.checkin)}<br>
        <a href="${esc(a.link)}" target="_blank" rel="noopener">Abrir no Airbnb</a></div>`)
      .addTo(layer);
  });

  // por destino (inclui contexto: quantos anúncios no total e mediana geral)
  const data = fData.value;
  const tiposOn = [...document.querySelectorAll(".f-tipo:checked")].map(e => e.value);
  const linhas = META.destinos.filter(d => tiposOn.includes(d.tipo)).map(d => {
    const ls = lista.filter(a => a.destino === d.nome).map(a => a.total);
    const ctx = CONTEXTO.filter(c => c.destino === d.nome && (!data || c.checkin === data)).map(c => c.total);
    return { ...d, n: ls.length, min: ls.length ? Math.min(...ls) : null, med: median(ls),
      max: ls.length ? Math.max(...ls) : null, ctxN: ctx.length, ctxMed: median(ctx),
      pct: ctx.length ? Math.round(100 * ls.length / ctx.length) : null,
      faixaPos: ls.length ? Math.min(...ls) : null };  // coluna "Faixa" ordena pelo início da barra
  });
  if (destSort.key) {
    // valores vazios ("—") ficam sempre no fim, em qualquer direção
    const dk = destSort.key, dd = destSort.dir;
    linhas.sort((a, b) => {
      const va = a[dk], vb = b[dk];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      return (typeof va === "string" ? va.localeCompare(vb, "pt-BR") : va - vb) * dd;
    });
  } else {
    // ordem padrão: destinos com opções primeiro, pela mediana mais baixa
    linhas.sort((a, b) => (b.n > 0) - (a.n > 0) || (a.med ?? 1e9) - (b.med ?? 1e9));
  }
  const thd = (key, label, num) => `<th class="${num ? "num" : ""}" data-k="${key}" title="Ordenar por ${label}">${label}${
    destSort.key === key ? (destSort.dir > 0 ? " ▲" : " ▼") : ""}</th>`;
  document.getElementById("t-dest").innerHTML =
    `<tr>${thd("nome", "Destino")}${thd("tipo", "Tipo")}${thd("n", "Na faixa", 1)}${thd("min", "Mín", 1)}${thd("med", "Mediana", 1)}
     ${thd("max", "Máx", 1)}${thd("faixaPos", "Faixa")}${thd("ctxMed", "Mediana geral*", 1)}${thd("pct", "% na faixa", 1)}${thd("dist_estrada", "Distância", 1)}</tr>` +
    linhas.map(d => `<tr><td>${esc(d.nome)}</td><td><span class="tag ${d.tipo}">${d.tipo}</span></td>
      <td class="num">${d.n}</td><td class="num">${brl(d.min)}</td><td class="num">${brl(d.med)}</td><td class="num">${brl(d.max)}</td>
      <td>${d.n ? `<div class="bar"><span style="left:${100 * (d.min - LO) / (HI - LO)}%;width:${Math.max(2, 100 * (d.max - d.min) / (HI - LO))}%"></span></div>` : ""}</td>
      <td class="num">${brl(d.ctxMed)} <span class="muted">(${d.ctxN})</span></td><td class="num">${d.pct == null ? "—" : d.pct + "%"}</td>
      <td class="num">~${d.dist_estrada} km de ${d.capital === "São Paulo" ? "SP" : "RJ"}</td></tr>`).join("");
  document.querySelectorAll("#t-dest th[data-k]").forEach(el => el.onclick = () => {
    const key = el.dataset.k;
    // 1º clique: texto e preços/distância em ordem crescente; contagens e % em decrescente
    const inicial = ["n", "pct"].includes(key) ? -1 : 1;
    destSort = { key, dir: destSort.key === key ? -destSort.dir : inicial };
    render();
  });

  // por data
  document.getElementById("t-data").innerHTML =
    `<tr><th>Check-in → check-out</th><th class="num">Opções na faixa</th><th class="num">Mín</th><th class="num">Mediana</th><th class="num">Mediana geral*</th></tr>` +
    META.datas.map(dt => {
      const ls = ANUNCIOS.filter(a => tiposOn.includes(a.tipo)).flatMap(a => a.datas.filter(([d]) => d === dt).map(([, t]) => t));
      const ctx = CONTEXTO.filter(c => c.checkin === dt).map(c => c.total);
      return `<tr><td>${dm(dt)} → ${dm(addDays(dt, META.noites))}</td><td class="num">${ls.length}</td>
        <td class="num">${brl(ls.length ? Math.min(...ls) : null)}</td><td class="num">${brl(median(ls))}</td>
        <td class="num">${brl(median(ctx))} <span class="muted">(${ctx.length})</span></td></tr>`;
    }).join("");

  // anúncios
  const k = sortState.key, dir = sortState.dir;
  lista.sort((a, b) => ((a[k] ?? -1) > (b[k] ?? -1) ? 1 : (a[k] ?? -1) < (b[k] ?? -1) ? -1 : 0) * dir);
  document.getElementById("n-anuncios").textContent = `(${lista.length})`;
  const th = (key, label, num) => `<th class="${num ? "num" : ""}" data-k="${key}">${label}${k === key ? (dir > 0 ? " ▲" : " ▼") : ""}</th>`;
  document.getElementById("t-anuncios").innerHTML =
    `<tr>${th("titulo", "Anúncio")}${th("destino", "Destino")}${th("total", "Total", 1)}${th("noite", "Por noite", 1)}
      ${th("nota", "Nota", 1)}${th("avaliacoes", "Avaliações", 1)}<th>Datas disponíveis na faixa</th>${th("score", "Score", 1)}</tr>` +
    lista.slice(0, 400).map(a => `<tr><td class="t"><a href="${esc(a.link)}" target="_blank" rel="noopener">${esc(a.titulo)}</a>
      ${a.subtitulo ? `<br><span class="muted">${esc(a.subtitulo)}</span>` : ""}</td>
      <td>${esc(a.destino)} <span class="tag ${a.tipo}">${a.tipo}</span></td>
      <td class="num"><b>${brl(a.total)}</b></td><td class="num">${brl(a.noite)}</td><td class="num">${nota(a.nota)}</td>
      <td class="num">${a.avaliacoes ?? "—"}</td><td>${a.datas.map(([d, t]) => `${dm(d)}: ${brl(t)}`).join(" · ")}</td>
      <td class="num">${(a.score * 100).toFixed(0)}</td></tr>`).join("");
  document.querySelectorAll("#t-anuncios th[data-k]").forEach(el => el.onclick = () => {
    sortState = { key: el.dataset.k, dir: sortState.key === el.dataset.k ? -sortState.dir : (el.dataset.k === "titulo" || el.dataset.k === "destino" || el.dataset.k === "total" || el.dataset.k === "noite" ? 1 : -1) };
    render();
  });
}

document.querySelectorAll(".filters input, .filters select").forEach(el => el.addEventListener("input", render));
document.getElementById("note").innerHTML =
  `* "Mediana geral" considera todos os anúncios retornados pela API para o destino/data (${META.total_com_preco} no total), ` +
  `inclusive fora da faixa de orçamento — mostra se o orçamento está acima ou abaixo do típico ali. ` +
  `Score combina proximidade de ${brl(META.orcamento)}, nota e nº de avaliações. ` +
  `Origem do preço: ${esc(META.origens_preco.join("; ") || "—")}. Confira sempre o valor final no Airbnb (taxas podem variar).`;
render();
</script>
</body>
</html>
"""


def gerar_html(anuncios, contexto, meta):
    dump = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
    return (TEMPLATE
            .replace("__ANUNCIOS__", dump(anuncios))
            .replace("__CONTEXTO__", dump(contexto))
            .replace("__META__", dump(meta)))
