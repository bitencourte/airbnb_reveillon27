#!/usr/bin/env python3
"""
Busca de acomodações no Airbnb para o Réveillon 2026/27.

Fonte padrão: actor da Apify "tri_angle/airbnb-scraper" (fonte_apify.py, token em APIFY_TOKEN).
Alternativa: API Airbnb19 do RapidAPI (--fonte rapidapi, chave em RAPIDAPI_KEY).

Busca cada destino em cada data de check-in, filtra pelo orçamento total e gera uma página
HTML com mapa, estatísticas por destino e por data, e lista de anúncios.

Uso:
    export APIFY_TOKEN="seu-token"
    python3 airbnb_search.py --destinos Paraty --datas 2026-12-30 --max-resultados 10
    python3 airbnb_search.py                         # busca completa (22 destinos x 3 datas)
    python3 airbnb_search.py --from-cache            # reprocessa sem gastar créditos
"""

import argparse
import base64
import json
import math
import os
import re
import statistics
import sys
import time
from datetime import date, timedelta
from pathlib import Path

API_HOST = "airbnb19.p.rapidapi.com"
GEO_URL = f"https://{API_HOST}/api/v2/searchPropertyByGEO"
PLACE_URL = f"https://{API_HOST}/api/v1/searchPropertyByPlace"
LOCATION_URL = f"https://{API_HOST}/api/v1/searchPropertyByLocationV2"
DESTINO_URL = f"https://{API_HOST}/api/v1/searchDestination"

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"

CAPITAIS = {
    "Rio de Janeiro": (-22.9068, -43.1729),
    "São Paulo": (-23.5505, -46.6333),
}

# nome, tipo, latitude, longitude, raio de busca (km), capital de referência, distância aprox. por estrada (km)
DESTINOS = [
    ("Ilha Grande",            "ilha",    -23.160, -44.230, 10.0, "Rio de Janeiro", 150),
    ("Ilhabela",               "ilha",    -23.815, -45.370, 10.0, "São Paulo",      210),
    ("Ilha do Cardoso",        "ilha",    -25.130, -47.950,  9.0, "São Paulo",      270),
    ("Paraty",                 "litoral", -23.219, -44.713,  9.0, "Rio de Janeiro", 250),
    ("Trindade",               "litoral", -23.354, -44.722,  3.0, "Rio de Janeiro", 270),
    ("Búzios",                 "litoral", -22.750, -41.885,  6.0, "Rio de Janeiro", 170),
    ("Arraial do Cabo",        "litoral", -22.966, -42.027,  5.0, "Rio de Janeiro", 165),
    ("Saquarema",              "litoral", -22.920, -42.510,  7.0, "Rio de Janeiro", 100),
    ("Ubatuba",                "litoral", -23.434, -45.071, 12.0, "São Paulo",      230),
    ("Camburi",                "litoral", -23.776, -45.648,  2.5, "São Paulo",      180),
    ("Juquehy",                "litoral", -23.766, -45.733,  2.5, "São Paulo",      175),
    ("Barra do Sahy",          "litoral", -23.771, -45.687,  2.0, "São Paulo",      178),
    ("Boiçucanga",             "litoral", -23.784, -45.623,  2.5, "São Paulo",      185),
    ("Maresias",               "litoral", -23.791, -45.566,  3.0, "São Paulo",      195),
    ("Barra do Una",           "litoral", -23.763, -45.763,  2.5, "São Paulo",      170),
    ("Cananéia",               "litoral", -25.015, -47.927,  6.0, "São Paulo",      270),
    ("Visconde de Mauá",       "serra",   -22.330, -44.560,  7.0, "Rio de Janeiro", 210),
    ("Lumiar",                 "serra",   -22.360, -42.318,  3.5, "Rio de Janeiro", 160),
    ("São Pedro da Serra",     "serra",   -22.323, -42.345,  3.0, "Rio de Janeiro", 160),
    ("Cunha",                  "serra",   -23.075, -44.960, 10.0, "São Paulo",      230),
    ("São Bento do Sapucaí",   "serra",   -22.689, -45.731,  8.0, "São Paulo",      190),
    ("Santo Antônio do Pinhal", "serra",  -22.827, -45.663,  7.0, "São Paulo",      170),
]

DATAS_PADRAO = ["2026-12-29", "2026-12-30", "2026-12-31"]

# Texto usado para achar o destino na busca por nome (--modo location ou place). Praias pequenas usam o
# município; os anúncios depois são filtrados pelo raio em volta das coordenadas acima.
BUSCA_NOME = {
    "Ilha Grande": "Ilha Grande, Angra dos Reis",
    "Ilha do Cardoso": "Cananéia",  # mesma busca de Cananéia (reaproveita o resultado)
    "Trindade": "Trindade, Paraty",
    "Camburi": "Camburi, São Sebastião",
    "Juquehy": "Juquehy, São Sebastião",
    "Barra do Sahy": "Barra do Sahy, São Sebastião",
    "Boiçucanga": "Boiçucanga, São Sebastião",
    "Maresias": "Maresias, São Sebastião",
    "Barra do Una": "Barra do Una, São Sebastião",
    "Visconde de Mauá": "Visconde de Mauá, Resende",
    "Lumiar": "Lumiar, Nova Friburgo",
    "São Pedro da Serra": "São Pedro da Serra, Nova Friburgo",
}


# ---------------------------------------------------------------- utilidades

def haversine_km(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def bbox(lat, lng, raio_km):
    dlat = raio_km / 111.0
    dlng = raio_km / (111.0 * math.cos(math.radians(lat)))
    return {"neLat": lat + dlat, "neLng": lng + dlng, "swLat": lat - dlat, "swLng": lng - dlng}


def slug(texto):
    import unicodedata
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def parse_valor(texto):
    """Converte 'R$ 5.123', 'R$5,123.50', '5.123,50' em float."""
    if isinstance(texto, (int, float)):
        return float(texto)
    if not isinstance(texto, str):
        return None
    m = re.search(r"\d[\d.,\s]*", texto.replace("\xa0", " "))
    if not m:
        return None
    s = m.group(0).replace(" ", "").rstrip(".,")
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        mil = "." if dec == "," else ","
        s = s.replace(mil, "").replace(dec, ".")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        partes = s.split(sep)
        if all(len(p) == 3 for p in partes[1:]):
            s = "".join(partes)          # separador de milhar
        else:
            s = s.replace(",", ".")      # separador decimal
    try:
        return float(s)
    except ValueError:
        return None


def brl(v):
    return "R$ " + f"{v:,.0f}".replace(",", ".")


def walk(obj, path=()):
    """Percorre todos os pares (caminho, chave, valor) de um JSON aninhado."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path, k, v
            yield from walk(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, path + (i,))


def find_first(obj, keys):
    keys_l = {k.lower() for k in keys}
    for _, k, v in walk(obj):
        if str(k).lower() in keys_l and v not in (None, "", [], {}):
            return v
    return None


# ---------------------------------------------------------------- API

def chamar_api(url, params, api_key, tentativas=3):
    import warnings
    warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")  # aviso inofensivo do Python do macOS
    import requests  # importado aqui para --from-cache funcionar sem requests instalado
    headers = {"X-RapidAPI-Key": api_key, "X-RapidAPI-Host": API_HOST}
    for i in range(tentativas):
        r = requests.get(url, headers=headers, params=params, timeout=60)
        restantes = r.headers.get("X-RateLimit-Requests-Remaining")
        if restantes is not None and int(restantes) <= 10:
            print(f"    atenção: restam {restantes} requisições no plano "
                  f"(limite {r.headers.get('X-RateLimit-Requests-Limit')}).")
        if r.status_code == 429:
            try:
                motivo = r.json().get("message", r.text)
            except ValueError:
                motivo = r.text
            if "quota" in str(motivo).lower() or restantes == "0":
                sys.exit(f"\nCota do plano RapidAPI esgotada: {motivo}\n"
                         f"Veja o uso e o plano em https://rapidapi.com/developer/billing/subscriptions-and-usage")
            espera = 5 * (i + 1)
            print(f"    limite de requisições (429): {motivo} — aguardando {espera}s...")
            time.sleep(espera)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("Limite de requisições excedido repetidamente (429).")


def extrair_lista(resp):
    """Acha a lista de anúncios na resposta, independente do formato exato."""
    if isinstance(resp, dict):
        data = resp.get("data", resp)
        if isinstance(data, dict):
            for k in ("list", "listings", "results", "items", "searchResults"):
                if isinstance(data.get(k), list):
                    return data[k], data.get("nextPageCursor") or resp.get("nextPageCursor")
        if isinstance(data, list):
            return data, None
    if isinstance(resp, list):
        return resp, None
    return [], None


def primeiro_destino(resp):
    """Retorna (id, nome) do primeiro destino de uma resposta do searchDestination."""
    data = resp.get("data") if isinstance(resp, dict) else resp
    for item in data if isinstance(data, list) else [data]:
        if isinstance(item, dict) and item.get("id"):
            nome = item.get("display_name") or item.get("displayName") or item.get("name") or ""
            return str(item["id"]), nome
    return None, None


def consulta_local(nome):
    # Texto simples, como na caixa de busca do Airbnb ("Paraty, Brasil" volta vazio; "Paraty" funciona)
    return BUSCA_NOME.get(nome, nome)


def resolver_destino(nome, api_key):
    """Acha o id do destino na API (searchDestination), com cache em cache/_destinos.json."""
    arq = CACHE_DIR / "_destinos.json"
    ids = json.loads(arq.read_text()) if arq.exists() else {}
    if nome in ids:
        return ids[nome]["id"], ids[nome]["encontrado"]
    consulta = BUSCA_NOME.get(nome, nome)
    resp = chamar_api(DESTINO_URL, {"query": consulta, "country": "BR"}, api_key)
    (CACHE_DIR / f"_bruto_destino_{slug(nome)}.json").write_text(json.dumps(resp, ensure_ascii=False, indent=1))
    dest_id, achado = primeiro_destino(resp)
    if not dest_id:
        print(f"\n    Destino '{consulta}' não encontrado na API.")
        return None, None
    print(f"[{achado}] ", end="", flush=True)
    ids[nome] = {"id": dest_id, "consulta": consulta, "encontrado": achado}
    arq.write_text(json.dumps(ids, ensure_ascii=False, indent=1))
    return dest_id, achado


def diagnostico(args, api_key):
    """Testa variações de busca para Paraty e mostra quais trazem anúncios (até 4 requisições)."""
    if not api_key:
        sys.exit("Defina a variável de ambiente RAPIDAPI_KEY.")
    CACHE_DIR.mkdir(exist_ok=True)
    ci, co = "2026-12-30", "2027-01-06"

    def resumo(n, titulo, url, params):
        print(f"\n[{n}] {titulo}")
        try:
            resp = chamar_api(url, params, api_key)
        except Exception as e:
            print(f"    ERRO: {e}")
            return None
        (CACHE_DIR / f"_diag_{n}.json").write_text(json.dumps(resp, ensure_ascii=False, indent=1))
        msg = resp.get("message") if isinstance(resp, dict) else ""
        lista, _ = extrair_lista(resp)
        print(f"    status={resp.get('status') if isinstance(resp, dict) else '?'} message={msg!r} itens={len(lista)}")
        if not lista:
            print(f"    início: {json.dumps(resp, ensure_ascii=False)[:250]}")
        time.sleep(args.pausa)
        return resp

    # Parte da requisição exata do exemplo do RapidAPI e muda um parâmetro por vez;
    # para no primeiro degrau que voltar vazio (é ele o culpado) para não gastar cota.
    local = consulta_local("Paraty")
    params = {"location": local, "totalRecords": 10, "currency": "USD", "adults": 1}
    degraus = [
        ("igual ao exemplo do RapidAPI (USD, 1 adulto, sem datas)", {}),
        ("+ moeda BRL", {"currency": "BRL"}),
        ("+ 4 adultos", {"adults": args.adultos}),
        ("+ datas 30/12 → 06/01", {"checkin": ci, "checkout": co}),
    ]
    for n, (titulo, mudanca) in enumerate(degraus, 1):
        params.update(mudanca)
        resp = resumo(n, f"'{local}' {titulo}", LOCATION_URL, dict(params))
        if resp is None or not extrair_lista(resp)[0]:
            if n == 1:
                print("\n=> Nem a requisição igual ao exemplo trouxe anúncios. A API pode estar instável;"
                      " tente de novo em alguns minutos.")
            else:
                print(f"\n=> O degrau {n} ({titulo}) zerou a lista: é esse parâmetro que está causando o problema.")
            break
    else:
        print("\n=> Todos os degraus trouxeram anúncios: a busca completa deve funcionar.")
    print(f"\nRespostas salvas em {CACHE_DIR}/_diag_*.json")


def buscar(dest, checkin, checkout, args, api_key):
    nome, _tipo, lat, lng, raio, *_ = dest
    cache = CACHE_DIR / f"{slug(nome)}_{checkin}.json"
    if cache.exists() and not args.refresh:
        return json.loads(cache.read_text())
    if args.from_cache:
        return []
    if not api_key:
        sys.exit("Defina a variável de ambiente RAPIDAPI_KEY (ou use --from-cache).")

    lo, hi = faixa_total(args)
    CACHE_DIR.mkdir(exist_ok=True)
    params = {
        "checkin": checkin,
        "checkout": checkout,
        "adults": args.adultos,
        "currency": args.moeda,
        "totalRecords": args.por_pagina,
    }
    if args.modo == "location":
        url = LOCATION_URL
        params["location"] = consulta_local(nome)
    elif args.modo == "place":
        url = PLACE_URL
        dest_id, display_name = resolver_destino(nome, api_key)
        if not dest_id:
            return []
        params["id"] = dest_id
        params["display_name"] = display_name
    else:
        url = GEO_URL
        params.update({k: round(v, 6) for k, v in bbox(lat, lng, raio).items()})
    if args.filtro_preco_api:
        # Desligado por padrão: não está claro se a API filtra por noite ou pelo total da viagem
        # (a resposta diz "Trip price, includes all fees"). O orçamento é filtrado localmente.
        params["priceMin"] = int(lo * 0.6 / args.noites)
        params["priceMax"] = int(math.ceil(hi * 1.1 / args.noites))

    itens, cursor = [], None
    for pagina in range(args.max_pages):
        if args.modo == "place" and pagina > 0:
            params["offset"] = pagina * args.por_pagina
        elif cursor:
            params["nextPageCursor"] = cursor
        resp = chamar_api(url, params, api_key)
        # guarda a resposta original para diagnóstico
        bruto = CACHE_DIR / f"_bruto_{slug(nome)}_{checkin}_p{pagina + 1}.json"
        bruto.write_text(json.dumps(resp, ensure_ascii=False, indent=1))
        if pagina == 0 and isinstance(resp, dict) and resp.get("status") is False:
            print(f"\n    API retornou erro: {resp.get('message')}")
            break
        lista, cursor = extrair_lista(resp)
        if not lista and pagina == 0:
            resumo = json.dumps(resp, ensure_ascii=False)[:300]
            print(f"\n    Nenhum anúncio reconhecido na resposta. Início da resposta: {resumo}")
            print(f"    Resposta completa salva em {bruto}")
        itens.extend(lista)
        if not lista or (args.modo != "place" and not cursor) or (args.modo == "place" and len(lista) < args.por_pagina):
            break
        time.sleep(args.pausa)

    if itens:  # não guarda cache vazio, para a próxima execução tentar de novo
        cache.write_text(json.dumps(itens, ensure_ascii=False))
    time.sleep(args.pausa)
    return itens


# ---------------------------------------------------------------- normalização

def decodificar_id(v):
    if v is None:
        return None
    s = str(v)
    if s.isdigit():
        return s
    try:  # IDs novos do Airbnb vêm como base64 de "DemandStayListing:123..."
        dec = base64.b64decode(s + "=" * (-len(s) % 4)).decode()
        if ":" in dec and dec.split(":")[-1].isdigit():
            return dec.split(":")[-1]
    except Exception:
        pass
    return s


def preco_estruturado(item, noites):
    """Lê o formato do searchPropertyByLocationV2 (structuredDisplayPrice).

    primaryLine.accessibilityLabel: "$2,165 USD total, originally ..." -> total
    explanationData: "5 nights x $464.09 USD" -> por noite
    """
    sdp = item.get("structuredDisplayPrice") if isinstance(item, dict) else None
    if not isinstance(sdp, dict):
        return None
    total = noite = None
    linha = sdp.get("primaryLine") or {}
    rotulo = linha.get("accessibilityLabel") or ""
    if "total" in rotulo.lower():
        total = parse_valor(rotulo)
    for _, k, v in walk(sdp.get("explanationData") or {}):
        if k != "description" or not isinstance(v, str):
            continue
        m = re.search(r"\d+\s*(?:nights?|noites?)\s*x\s*(.+)", v, re.I)
        if m and noite is None:
            noite = parse_valor(m.group(1))
    if total is None:
        return None
    return total, noite or total / noites, "structuredDisplayPrice (total com taxas e descontos)"


def extrair_preco(item, noites):
    """Retorna (total, por_noite, origem). Prioriza valores explicitamente 'total'."""
    preco = preco_estruturado(item, noites)
    if preco:
        return preco
    total = noite = None
    origem = ""
    textos = []
    for path, k, v in walk(item):
        kl = str(k).lower()
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if total is None and kl in ("totalprice", "total", "pricetotal", "total_price", "amount_total"):
                total, origem = float(v), f"campo {k}"
            elif noite is None and kl in ("pricepernight", "nightlyprice", "rate", "price_per_night"):
                noite = float(v)
            elif noite is None and kl == "amount" and path and str(path[-1]).lower() == "price":
                noite = float(v)  # formato {"price": {"amount": 450, "qualifier": "nightly"}}
        elif isinstance(v, str) and re.search(r"\d", v) and ("R$" in v or "$" in v or "total" in v.lower()):
            textos.append((kl, v))
    if total is None:
        for kl, v in textos:
            if "total" in v.lower() or "total" in kl:
                total, origem = parse_valor(v), f"texto '{v[:40]}'"
                if total:
                    break
    if total is None:
        for kl, v in textos:
            vl = v.lower()
            if re.search(r"(noites|nights)", vl) and not re.search(r"(/|por|per)\s*(noite|night)\b", vl):
                total, origem = parse_valor(v), f"texto '{v[:40]}'"
                if total:
                    break
    if noite is None:
        for kl, v in textos:
            if "total" in v.lower():
                continue
            if re.search(r"(/|por|per|a)\s*(noite|night)\b", v.lower()) or kl in ("price", "discountedprice", "originalprice"):
                noite = parse_valor(v)
                if noite:
                    break
    if total is None and noite is not None:
        total, origem = noite * noites, "por noite × noites (estimado, sem taxas)"
    if noite is None and total is not None:
        noite = total / noites
    return total, noite, origem


def normalizar(item, dest, checkin, checkout, args):
    nome_dest, tipo, dlat, dlng, raio, capital, dist_estrada = dest
    if getattr(args, "fonte", "") == "apify":
        import fonte_apify
        c = fonte_apify.normalizar_campos(item, args.noites, parse_valor)
        return montar_anuncio(c, dest, checkin, checkout, args)
    listing = item.get("listing", item) if isinstance(item, dict) else {}
    lid = decodificar_id(listing.get("id") or item.get("id") or find_first(item, ["listingId", "propertyId", "id"]))
    lat = find_first(item, ["latitude", "lat"])
    lng = find_first(item, ["longitude", "lng", "lon"])
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return None

    titulo = find_first(item, ["name", "title", "listingName"]) or "Sem título"
    subtitulo = (item.get("subtitle") if isinstance(item, dict) else None) or \
        find_first(item, ["title", "roomTypeCategory", "roomType", "listingObjType"]) or ""

    nota, avaliacoes = None, None
    r = find_first(item, ["avgRating", "rating", "starRating"])
    if isinstance(r, (int, float)):
        nota = float(r)
    rl = find_first(item, ["avgRatingLocalized", "avgRatingA11yLabel"])
    if isinstance(rl, str):
        m = re.search(r"(\d[.,]\d+)\s*\((\d+)\)", rl)
        if m:
            nota = nota or float(m.group(1).replace(",", "."))
            avaliacoes = int(m.group(2))
    rc = find_first(item, ["reviewsCount", "reviewCount", "visibleReviewCount", "ratingCount"])
    if avaliacoes is None and isinstance(rc, (int, float, str)) and str(rc).isdigit():
        avaliacoes = int(rc)

    total, noite, origem = extrair_preco(item, args.noites)
    foto = find_first(item, ["picture", "pictureUrl", "baseUrl", "xlPictureUrl"])
    if isinstance(foto, dict):
        foto = foto.get("picture") or foto.get("baseUrl")

    c = {"id": lid, "titulo": titulo, "subtitulo": subtitulo if subtitulo != titulo else "", "lat": lat, "lng": lng,
         "nota": nota, "avaliacoes": avaliacoes, "total": total, "noite": noite, "origem_preco": origem,
         "foto": foto, "capacidade": None}
    return montar_anuncio(c, dest, checkin, checkout, args)


def montar_anuncio(c, dest, checkin, checkout, args):
    """Formato comum usado pelo relatório, independente da fonte dos dados."""
    nome_dest, tipo, dlat, dlng, raio, capital, dist_estrada = dest
    try:
        lat, lng = float(c["lat"]), float(c["lng"])
    except (TypeError, ValueError):
        return None
    lid, total, noite, foto = c["id"], c["total"], c["noite"], c["foto"]
    dist_capitais = {cap: round(haversine_km((lat, lng), pos)) for cap, pos in CAPITAIS.items()}
    return {
        "id": lid,
        "titulo": str(c["titulo"])[:120],
        "subtitulo": str(c["subtitulo"] or "")[:80],
        "capacidade": c["capacidade"],
        "destino": nome_dest,
        "tipo": tipo,
        "lat": lat,
        "lng": lng,
        "dist_destino_km": round(haversine_km((lat, lng), (dlat, dlng)), 1),
        "dist_capitais": dist_capitais,
        "capital": capital,
        "dist_estrada": dist_estrada,
        "checkin": checkin,
        "checkout": checkout,
        "total": round(total) if total else None,
        "noite": round(noite) if noite else None,
        "origem_preco": c["origem_preco"],
        "nota": c["nota"],
        "avaliacoes": c["avaliacoes"],
        "foto": foto if isinstance(foto, str) and foto.startswith("http") else None,
        "link": f"https://www.airbnb.com.br/rooms/{lid}?check_in={checkin}&check_out={checkout}&adults={args.adultos}",
    }


def faixa_total(args):
    return args.orcamento * (1 - args.tolerancia), args.orcamento * (1 + args.tolerancia)


def score(a, args):
    """Quanto maior, melhor: perto do orçamento, boa nota e muitas avaliações."""
    proximidade = 1 - min(abs(a["total"] - args.orcamento) / (args.orcamento * args.tolerancia), 1)
    nota = ((a["nota"] or 4.5) - 4.0) / 1.0
    confianca = min(math.log10((a["avaliacoes"] or 0) + 1) / 2, 1)
    return round(0.45 * proximidade + 0.35 * max(nota, 0) + 0.20 * confianca, 4)


# ---------------------------------------------------------------- principal

def main():
    p = argparse.ArgumentParser(description="Busca Airbnb Réveillon 2026/27 via Apify ou RapidAPI.")
    p.add_argument("--destinos", help="Lista separada por vírgula (padrão: todos). Ex.: 'Paraty,Ilhabela'")
    p.add_argument("--tipos", help="Filtrar por tipo: serra,litoral,ilha")
    p.add_argument("--datas", default=",".join(DATAS_PADRAO), help="Datas de check-in (AAAA-MM-DD), separadas por vírgula")
    p.add_argument("--noites", type=int, default=7)
    p.add_argument("--adultos", type=int, default=4)
    p.add_argument("--orcamento", type=float, default=5000, help="Total desejado da estadia (R$)")
    p.add_argument("--tolerancia", type=float, default=0.2, help="Faixa aceita em torno do orçamento (0.2 = ±20%%)")
    p.add_argument("--moeda", default="BRL")
    p.add_argument("--max-km", type=float, default=300, help="Distância máxima em linha reta até RJ ou SP")
    p.add_argument("--max-pages", type=int, default=1, help="Páginas por destino/data (cada uma = 1 requisição)")
    p.add_argument("--por-pagina", type=int, default=40)
    p.add_argument("--pausa", type=float, default=2.5, help="Segundos entre requisições (plano básico: 2–3 s)")
    p.add_argument("--filtro-preco-api", action="store_true",
                   help="Envia priceMin/priceMax (por noite) à API; por padrão o orçamento é filtrado só no script")
    p.add_argument("--from-cache", action="store_true", help="Usa apenas o cache local, sem chamar a API")
    p.add_argument("--refresh", action="store_true", help="Ignora o cache e consulta a API de novo")
    p.add_argument("--saida", default="reveillon_2026.html")
    p.add_argument("--modo", choices=["location", "geo", "place"], default="location",
                   help="location = busca pelo nome do local (padrão); geo = por área no mapa; place = por id do destino")
    p.add_argument("--fonte", choices=["apify", "rapidapi"], default="apify",
                   help="apify = actor tri_angle/airbnb-scraper (padrão, token em APIFY_TOKEN); rapidapi = Airbnb19")
    p.add_argument("--max-resultados", type=int, default=40,
                   help="Apify: anúncios por destino/data (custo ~US$ 1,25 por mil)")
    p.add_argument("--paralelo", type=int, default=2, help="Apify: execuções simultâneas")
    p.add_argument("--timeout-apify", type=int, default=600, help="Apify: segundos máximos por execução")
    p.add_argument("--diagnostico", action="store_true", help="Testa a busca por local em Paraty, um parâmetro por vez (até 4 requisições)")
    args = p.parse_args()

    if args.diagnostico:
        if args.fonte == "apify":
            sys.exit("O --diagnostico é só para a RapidAPI. Para testar a Apify, rode uma busca pequena:\n"
                     "  python3 airbnb_search.py --destinos Paraty --datas 2026-12-30 --max-resultados 10")
        diagnostico(args, os.environ.get("RAPIDAPI_KEY"))
        return

    destinos = DESTINOS
    if args.destinos:
        pedidos = {slug(d) for d in args.destinos.split(",")}
        destinos = [d for d in DESTINOS if slug(d[0]) in pedidos]
        faltando = pedidos - {slug(d[0]) for d in destinos}
        if faltando:
            sys.exit(f"Destino(s) não encontrado(s) na lista: {', '.join(faltando)}")
    if args.tipos:
        tipos = {t.strip() for t in args.tipos.split(",")}
        destinos = [d for d in destinos if d[1] in tipos]

    datas = [d.strip() for d in args.datas.split(",") if d.strip()]
    api_key = os.environ.get("RAPIDAPI_KEY")
    lo, hi = faixa_total(args)

    def checkout_de(checkin):
        return (date.fromisoformat(checkin) + timedelta(days=args.noites)).isoformat()

    total_reqs = len(destinos) * len(datas)
    if args.fonte == "apify":
        import fonte_apify
        print(f"Fonte: Apify ({fonte_apify.ACTOR}), até {args.max_resultados} anúncios por destino/data.")
        tarefas = sorted({(consulta_local(d[0]), ci, checkout_de(ci)) for d in destinos for ci in datas})
        if not args.from_cache:
            token = os.environ.get("APIFY_TOKEN")
            if not token:
                sys.exit("Defina a variável de ambiente APIFY_TOKEN (ou use --from-cache).")
            fonte_apify.buscar_todos(tarefas, args, token, CACHE_DIR)
        print()
    else:
        print(f"Fonte: RapidAPI (Airbnb19). {len(destinos)} destinos × {len(datas)} datas = {total_reqs} buscas "
              f"(até {total_reqs * args.max_pages} requisições; cache evita repetir).")
    print(f"Faixa de orçamento: {brl(lo)} – {brl(hi)} para {args.noites} noites, {args.adultos} adultos.\n")

    candidatos, sem_preco, fora_area, pequenos = [], 0, 0, 0
    for dest in destinos:
        for checkin in datas:
            checkout = checkout_de(checkin)
            print(f"  {dest[0]:<25} {checkin} → {checkout} ", end="", flush=True)
            if args.fonte == "apify":
                itens = fonte_apify.ler_cache(CACHE_DIR, consulta_local(dest[0]), checkin)
            else:
                itens = buscar(dest, checkin, checkout, args, api_key)
            ok = 0
            for it in itens:
                a = normalizar(it, dest, checkin, checkout, args)
                if not a:
                    continue
                # descarta o que a busca por área trouxe longe demais da localidade
                if a["dist_destino_km"] > dest[4] * 1.5:
                    fora_area += 1
                    continue
                if min(a["dist_capitais"].values()) > args.max_km:
                    fora_area += 1
                    continue
                if a["capacidade"] and a["capacidade"] < args.adultos:
                    pequenos += 1
                    continue
                if a["total"] is None:
                    sem_preco += 1
                    continue
                a["_prox"] = a["dist_destino_km"] / dest[4]
                candidatos.append(a)
                ok += 1
            print(f"{len(itens):>3} resultados, {ok} na área com preço")

    # o mesmo anúncio pode cair em destinos vizinhos (ex.: Cananéia e Ilha do Cardoso);
    # fica no destino mais próximo, proporcionalmente ao raio de cada um
    melhor = {}
    for a in candidatos:
        k = (a["id"], a["checkin"])
        if k not in melhor or a["_prox"] < melhor[k]["_prox"]:
            melhor[k] = a
    todos = list(melhor.values())

    dentro = [a for a in todos if lo <= a["total"] <= hi]
    for a in dentro:
        a["score"] = score(a, args)

    # agrupa o mesmo anúncio em datas diferentes
    por_id = {}
    for a in dentro:
        por_id.setdefault(a["id"], []).append(a)
    anuncios = []
    for lst in por_id.values():
        lst.sort(key=lambda x: (-x["score"], x["total"]))
        melhor = dict(lst[0])
        melhor["datas"] = sorted({x["checkin"]: x["total"] for x in lst}.items())
        anuncios.append(melhor)
    anuncios.sort(key=lambda x: -x["score"])

    print(f"\n{len(todos)} anúncios com preço; {len(dentro)} combinações dentro da faixa; "
          f"{len(anuncios)} anúncios únicos. ({sem_preco} sem preço, {fora_area} fora da área, "
          f"{pequenos} para menos de {args.adultos} hóspedes)")
    if todos:
        totais = sorted(a["total"] for a in todos)
        print(f"Total da estadia (todos): mín {brl(totais[0])} · mediana {brl(statistics.median(totais))} · máx {brl(totais[-1])}")

    meta = {
        "orcamento": args.orcamento, "faixa": [lo, hi], "noites": args.noites, "adultos": args.adultos,
        "datas": datas, "destinos": [
            {"nome": d[0], "tipo": d[1], "lat": d[2], "lng": d[3], "capital": d[5], "dist_estrada": d[6]}
            for d in destinos
        ],
        "total_com_preco": len(todos),
        "origens_preco": sorted({a["origem_preco"].split("'")[0].strip() for a in todos}),
        "gerado_em": time.strftime("%d/%m/%Y %H:%M"),
    }
    # todos os anúncios (inclusive fora da faixa) para o contexto de preços por destino
    contexto = [{"destino": a["destino"], "checkin": a["checkin"], "total": a["total"]} for a in todos]

    from relatorio_html import gerar_html
    saida = BASE_DIR / args.saida
    saida.write_text(gerar_html(anuncios, contexto, meta), encoding="utf-8")
    print(f"\nRelatório: {saida}")


if __name__ == "__main__":
    main()
