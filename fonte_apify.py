"""Busca anúncios do Airbnb pelo actor da Apify "tri_angle/airbnb-scraper" (API REST, sem SDK).

Cada busca (local + data de check-in) é uma execução ("run") do actor. A Apify cobra por
anúncio retornado (~US$ 1,00–1,25 por mil), então o número de anúncios por busca é limitado
por maxResults.
"""

import json
import re
import time
import unicodedata

ACTOR = "tri_angle~airbnb-scraper"
API = "https://api.apify.com/v2"
FINAIS = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


def _slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def arquivo_cache(cache_dir, consulta, checkin):
    # a chave é o texto da busca: destinos que usam a mesma consulta reaproveitam o resultado
    return cache_dir / f"apify_{_slug(consulta)}_{checkin}.json"


def _req(metodo, caminho, token, **kw):
    import warnings
    warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
    import requests
    r = requests.request(metodo, API + caminho, headers={"Authorization": f"Bearer {token}"}, timeout=120, **kw)
    if r.status_code in (401, 403):
        raise SystemExit(f"Apify recusou o token ({r.status_code}): {r.text[:200]}")
    if r.status_code == 402:
        raise SystemExit(f"Créditos da Apify esgotados (402): {r.text[:200]}")
    r.raise_for_status()
    return r.json()


def executar(consulta, checkin, checkout, args, token, log=print):
    """Roda o actor para um local e uma data e devolve a lista de anúncios."""
    entrada = {
        "locationQueries": [consulta],
        "checkIn": checkin,
        "checkOut": checkout,
        "adults": args.adultos,
        "currency": args.moeda,
        "locale": "pt-BR",
        "maxResults": args.max_resultados,
    }
    run = _req("POST", f"/acts/{ACTOR}/runs", token, params={"waitForFinish": 60}, json=entrada)["data"]
    inicio = time.time()
    while run["status"] not in FINAIS:
        if time.time() - inicio > args.timeout_apify:
            log(f"    {consulta} {checkin}: tempo esgotado ({args.timeout_apify}s); a execução segue na Apify")
            return None
        run = _req("GET", f"/actor-runs/{run['id']}", token, params={"waitForFinish": 60})["data"]
    if run["status"] != "SUCCEEDED":
        log(f"    {consulta} {checkin}: execução terminou como {run['status']}")
        return None
    return _req("GET", f"/datasets/{run['defaultDatasetId']}/items", token,
                params={"clean": "true", "format": "json"})


def buscar_todos(tarefas, args, token, cache_dir, log=print):
    """Executa em paralelo as buscas (consulta, checkin, checkout) que ainda não estão no cache."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    pendentes = [t for t in tarefas if args.refresh or not arquivo_cache(cache_dir, t[0], t[1]).exists()]
    if not pendentes:
        return
    estimativa = len(pendentes) * args.max_resultados
    log(f"Apify: {len(pendentes)} buscas a executar (até {estimativa} anúncios, "
        f"~US$ {estimativa * 1.25 / 1000:.2f}), {args.paralelo} por vez...")
    cache_dir.mkdir(exist_ok=True)

    def uma(t):
        consulta, checkin, checkout = t
        itens = executar(consulta, checkin, checkout, args, token, log)
        if itens:  # não guarda vazio/erro, para tentar de novo na próxima execução
            arquivo_cache(cache_dir, consulta, checkin).write_text(json.dumps(itens, ensure_ascii=False))
        return t, itens

    feitas = 0
    with ThreadPoolExecutor(max_workers=args.paralelo) as ex:
        for fut in as_completed([ex.submit(uma, t) for t in pendentes]):
            (consulta, checkin, _), itens = fut.result()
            feitas += 1
            log(f"  [{feitas}/{len(pendentes)}] {consulta:<35} {checkin}: "
                f"{len(itens) if itens is not None else 'falhou'} anúncios")


def ler_cache(cache_dir, consulta, checkin):
    arq = arquivo_cache(cache_dir, consulta, checkin)
    return json.loads(arq.read_text()) if arq.exists() else []


def _texto_preco(v):
    """O preço pode vir como texto ("R$ 5.000") ou como objeto {"price": "R$ 5.000", ...}."""
    if isinstance(v, dict):
        return v.get("price") or v.get("amount") or v.get("label") or v.get("description")
    return v


def preco(item, noites, parse_valor):
    """Retorna (total, por_noite, origem) a partir do campo price do actor."""
    p = item.get("price") or {}
    if not isinstance(p, dict):
        valor = parse_valor(p)
        return (valor * noites, valor, "price (por noite × noites)") if valor else (None, None, "")
    qualificador = str(p.get("qualifier") or "").lower()
    rotulo = str(p.get("label") or "")
    quebra = p.get("breakDown") or {}

    # Formato real (locale pt-BR), diferente do exemplo da documentação:
    #   label "Total: R$ 8.818" ou "O preço original era R$ 9.300 e o novo preço total é R$ 7.440"
    #   breakDown.total.price "R$ 8.817,12" (total exato, já com descontos e taxas)
    candidatos = [
        (_texto_preco(quebra.get("total")), "breakDown.total"),
        (_texto_preco(quebra.get("totalBeforeTaxes")), "breakDown.totalBeforeTaxes"),
        (p.get("discountedPrice"), "price.discountedPrice"),
    ]
    if "total" in qualificador or "total" in rotulo.lower():
        candidatos.append((p.get("price") or p.get("amount"), "price total"))
        # num rótulo com desconto o último valor é o preço novo
        valores = re.findall(r"R?\$\s*[\d.,]+", rotulo)
        if valores:
            candidatos.append((valores[-1], "label total"))
    total, origem = None, ""
    for texto, nome in candidatos:
        total = parse_valor(texto)
        if total:
            origem = nome
            break

    noite = None
    if "night" in qualificador or "noite" in qualificador:
        noite = parse_valor(p.get("amount") or p.get("price"))

    if total is None and noite:
        total, origem = noite * noites, "por noite × noites (estimado, sem taxas)"
    if total and not noite:
        noite = total / noites  # média por noite do total pago (com descontos e taxas)
    return total, noite, origem if total else ""


def normalizar_campos(item, noites, parse_valor):
    """Extrai os campos que o relatório usa de um item do actor."""
    coord = item.get("coordinates") or {}
    nota = item.get("rating") or {}
    total, noite, origem = preco(item, noites, parse_valor)
    capacidade = item.get("personCapacity")
    sub = [s for s in (item.get("roomType"), f"até {capacidade} hóspedes" if capacidade else None) if s]
    return {
        "id": str(item.get("id") or ""),
        "titulo": item.get("title") or item.get("name") or "Sem título",
        "subtitulo": " · ".join(sub),
        "lat": coord.get("latitude"),
        "lng": coord.get("longitude"),
        "nota": nota.get("guestSatisfaction") if isinstance(nota, dict) else None,
        "avaliacoes": nota.get("reviewsCount") if isinstance(nota, dict) else None,
        "total": total,
        "noite": noite,
        "origem_preco": origem,
        "foto": item.get("thumbnail") or next(
            (i.get("imageUrl") for i in item.get("images") or [] if isinstance(i, dict)), None),
        "capacidade": capacidade,
    }
