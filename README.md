# Busca Airbnb – Réveillon 2026/27

Busca anúncios do Airbnb em 22 destinos de serra, litoral e ilha perto do RJ e de SP. As buscas são para 4 adultos, 7 noites, com check-in em 29, 30 ou 31/12/2026. O script gera `reveillon_2026.html`, com mapa, faixa de preços por destino e por data, e a lista de anúncios.

**Resultados publicados:** https://bitencourte.github.io/airbnb_reveillon27/ (GitHub Pages; o `index.html` abre `reveillon_2026.html`). Para atualizar, rode a busca, faça commit do novo `reveillon_2026.html` e dê push.

A fonte padrão é o actor **Airbnb Scraper** da Apify (`tri_angle/airbnb-scraper`). A API Airbnb19 do RapidAPI continua disponível com `--fonte rapidapi`, mas devolveu listas vazias nos testes.

## Instalação
```
pip3 install requests
```

Pegue seu token da Apify em **console.apify.com → Settings → API & Integrations → Personal API tokens** e defina no terminal. Ele vale enquanto o terminal estiver aberto:
```
export APIFY_TOKEN="seu-token-da-apify"
```

## Uso
Teste pequeno (1 execução, 10 anúncios, menos de US$ 0,02):
```
python3 airbnb_search.py --destinos Paraty --datas 2026-12-30 --max-resultados 10
open reveillon_2026.html
```
Uma data para todos os destinos (21 execuções, até 840 anúncios, ~US$ 1):
```
python3 airbnb_search.py --datas 2026-12-30
```
Busca completa (21 buscas × 3 datas = 63 execuções, até 2.520 anúncios, ~US$ 3):
```
python3 airbnb_search.py
```
Reprocessar sem gastar créditos (usa a pasta `cache/`):
```
python3 airbnb_search.py --from-cache --orcamento 4500 --tolerancia 0.15
```

Opções úteis:
- `--max-resultados 80` traz mais anúncios por destino/data, mas custa proporcionalmente mais.
- `--paralelo 3` roda mais execuções ao mesmo tempo. O plano gratuito da Apify tem limite de memória, então 2 ou 3 é o seguro.
- `--tipos litoral,ilha` limita os tipos de destino.
- `--refresh` ignora o cache e busca de novo (preços atualizados).
- `--fonte rapidapi` usa a API Airbnb19 (precisa de `RAPIDAPI_KEY`). Com essa fonte, `--diagnostico` testa a API em Paraty.

Para editar destinos, coordenadas ou o raio de busca, altere `DESTINOS` no início de `airbnb_search.py`. O texto pesquisado de cada destino fica em `BUSCA_NOME`.

## Custo
A Apify cobra por anúncio retornado: entre US$ 1,00 e 1,25 por mil, conforme a página do actor. O plano gratuito inclui US$ 5 de crédito por mês. Antes de rodar, o script mostra quantas execuções vai fazer e uma estimativa do custo. Resultados que já estão no cache não são cobrados de novo.

## Observações
- O Airbnb não tem API oficial. Os dois serviços são de terceiros, e o formato da resposta pode mudar.
- Na Apify, o preço usado é o "total antes dos impostos" da estadia, que já inclui taxa de limpeza e de serviço. O relatório informa a origem do valor. Confira sempre o total final no site.
- Anúncios para menos de 4 hóspedes são descartados.
