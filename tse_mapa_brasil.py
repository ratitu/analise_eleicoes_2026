"""Mapa do Brasil inteiro por municipio, colorido pelo vencedor da eleicao
presidencial de 2026 (eleicao 6257, cargo 1, 1o turno).

Uso:
    python tse_mapa_brasil.py

Funcao:
    Junta os GeoJSONs ja prontos das cinco regioes (nordeste, sudeste,
    centro_oeste, norte, sul), soma os CSVs brutos para o rodape de votos e
    desenha o pais inteiro com os mesmos parametros do mapa de Sao Paulo:
    dpi 200, fundo #f4f1ea, contornos brancos de 0,35, cores #1f5fbf / #d92b2b /
    #b9b9b9, mesma tipografia de titulo, legenda e rodape.

    Gera tambem a versao interativa em HTML (Leaflet, popup e tooltip com o
    percentual por municipio), reusando tse_regiao_mapa_html.montar.
"""

import csv
import json
import os
import sys
import unicodedata
from collections import defaultdict

import geopandas as gpd
import shapely

import tse_regiao_mapa as mapa
import tse_regiao_mapa_html as htmlmapa

RAIZ = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(RAIZ, "tse_2026_resultados")

REGIOES = ["nordeste", "sudeste", "centro_oeste", "norte", "sul"]

ORDEM_UF = [
    "ac", "al", "ap", "am", "ba", "ce", "df", "es", "go", "ma", "mt", "ms",
    "mg", "pa", "pb", "pr", "pe", "pi", "rj", "rn", "rs", "ro", "rr", "sc",
    "sp", "se", "to",
]

CAPITAIS = {
    "ac": "Rio Branco", "al": "Maceio", "ap": "Macapa", "am": "Manaus",
    "ba": "Salvador", "ce": "Fortaleza", "df": "Brasilia", "es": "Vitoria",
    "go": "Goiania", "ma": "Sao Luis", "mt": "Cuiaba", "ms": "Campo Grande",
    "mg": "Belo Horizonte", "pa": "Belem", "pb": "Joao Pessoa", "pr": "Curitiba",
    "pe": "Recife", "pi": "Teresina", "rj": "Rio de Janeiro", "rn": "Natal",
    "rs": "Porto Alegre", "ro": "Porto Velho", "rr": "Boa Vista",
    "sc": "Florianopolis", "sp": "Sao Paulo", "se": "Aracaju", "to": "Palmas",
}

MAIORES_EXTRAS = 30
QUANTIDADE_PROXIMOS_EMPATE = 5
LADO = 16.0
MINIMO = 10.0
ALVO_BYTES_HTML = 9_000_000
FASES_HTML = (0.0015, 0.0025, 0.004, 0.008, 0.015, 0.03, 0.06)

LIMITES_FAIXA = (2.0, 5.0, 10.0, 20.0)
FAIXAS_TXT = (
    "0 a 2 pp",
    "2 a 5 pp",
    "5 a 10 pp",
    "10 a 20 pp",
    "20 pp ou mais",
)

RAMPAS = {
    "pt": ("#f5d6d2", "#fdada4", "#fd8377", "#f2544c", "#d92b2b"),
    "pl": ("#cedff9", "#9ec7ff", "#6eaaff", "#4083ec", "#1f5fbf"),
}

TITULO_FAMILIA = {"pt": "LULA — PT", "pl": "FLAVIO BOLSONARO — PL"}

POS_INSET_BRASIL = (0.80, 0.80, 0.18, 0.18)


def sem_acento(texto):
    base = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in base if unicodedata.category(c) != "Mn").upper()


def descartar_ilhas_distantes(geom):
    partes = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    if len(partes) < 2:
        return geom
    partes = sorted(partes, key=lambda p: -p.area)
    maior = partes[0]
    centro = maior.centroid
    manter = [
        p
        for p in partes
        if p is maior
        or p.area / maior.area >= mapa.RAZAO_AREA_MINIMA
        or p.centroid.distance(centro) < mapa.PARTES_DISTANTES_GRAUS
    ]
    if len(manter) == len(partes):
        return geom
    return shapely.union_all(manter) if len(manter) > 1 else manter[0]


def somente_poligonos(geom):
    if geom is None or geom.is_empty:
        return geom
    if geom.geom_type == "GeometryCollection":
        partes = [c for c in geom.geoms if c.geom_type in ("Polygon", "MultiPolygon")]
        if not partes:
            return geom
        if len(partes) == 1:
            return partes[0]
        partes_expandidas = []
        for p in partes:
            if p.geom_type == "MultiPolygon":
                partes_expandidas.extend(list(p.geoms))
            else:
                partes_expandidas.append(p)
        return shapely.geometry.MultiPolygon(partes_expandidas)
    return geom


def juntar_geojsons():
    feats = []
    for regiao in REGIOES:
        caminho = os.path.join(
            BASE, f"mapa_{regiao}", f"mapa_vencedor_presidencial_{regiao}.geojson"
        )
        if not os.path.exists(caminho):
            raise SystemExit(f"Falta o GeoJSON: {caminho}")
        dados = json.load(open(caminho, encoding="utf-8"))["features"]
        feats.extend(dados)
        print(f"  {regiao}: {len(dados)} municipios")
    return feats


def juncao_chaves(dicionario):
    return {sem_acento(k): v for k, v in dicionario.items()}


def ler_limites_estados():
    caminho = os.path.join(BASE, "mapa_brasil", "Estados_Brasil.shp")
    if not os.path.exists(caminho):
        print(f"  shapefile de estados ausente: {caminho}")
        return None
    grade = gpd.read_file(caminho)
    grade["geometry"] = grade.geometry.apply(
        lambda g: somente_poligonos(
            shapely.make_valid(g) if g is not None and not g.is_valid else g
        )
    )
    linhas = []
    for geom in grade.geometry:
        if geom is None or geom.is_empty:
            continue
        contorno = geom.boundary
        if contorno is None or contorno.is_empty:
            continue
        partes = (
            [contorno]
            if contorno.geom_type == "LineString"
            else list(contorno.geoms)
        )
        for parte in partes:
            if parte.is_empty:
                continue
            coords = [[round(x, 4), round(y, 4)] for x, y in parte.coords]
            if len(coords) > 1:
                linhas.append(coords)
    print(f"  limites de estado: {len(linhas)} segmentos de {len(grade)} estados")
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "MultiLineString", "coordinates": linhas},
            }
        ],
    }


def numero(valor):
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def chave_codigo(valor):
    texto = str(valor if valor is not None else "").strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto


def familia_por_vencedor(venceu):
    nome = " ".join(str(venceu or "").upper().split())
    tem_bolso = "BOLSONARO" in nome
    tem_lula = "LULA" in nome
    if tem_bolso and not tem_lula:
        return "pl"
    if tem_lula and not tem_bolso:
        return "pt"
    return "empate"


def indice_faixa(margem_pp):
    if margem_pp is None:
        return 0
    for indice, limite in enumerate(LIMITES_FAIXA):
        if margem_pp < limite:
            return indice
    return len(FAIXAS_TXT) - 1


def grau_por_margem(margem_pp, venceu):
    familia = familia_por_vencedor(venceu)
    if familia == "empate":
        return "empate", 0
    return familia, indice_faixa(margem_pp)


def cor_por_margem(margem_pp, venceu):
    familia, indice = grau_por_margem(margem_pp, venceu)
    if familia == "empate":
        return mapa.COR_EMPATE
    return RAMPAS[familia][indice]


def ler_margens():
    por_codigo = {}
    for regiao in REGIOES:
        caminho = os.path.join(
            BASE, f"dados_{regiao}", f"vencedor_presidente_{regiao}.csv"
        )
        with open(caminho, encoding="utf-8") as fh:
            for linha in csv.DictReader(fh):
                codigo = chave_codigo(linha.get("codigo_ibge"))
                margem = numero(linha.get("margem_pp"))
                if codigo and margem is not None:
                    por_codigo[codigo] = margem
    return por_codigo


def aplicar_rampa(gdf):
    margens = ler_margens()
    gdf = gdf.copy()
    gdf["margem_pp"] = gdf["codigo_ibge"].map(
        lambda c: margens.get(chave_codigo(c))
    )
    sem_margem = int(gdf["margem_pp"].isna().sum())
    graus = [
        grau_por_margem(m, v)
        for m, v in zip(gdf["margem_pp"], gdf["venceu"])
    ]
    gdf["familia"] = [d[0] for d in graus]
    gdf["faixa_pp"] = [FAIXAS_TXT[d[1]] for d in graus]
    gdf["margem_txt"] = [
        "—" if m is None else f"{mapa.br(m)} pp"
        for m in gdf["margem_pp"]
    ]
    gdf["cor"] = [
        cor_por_margem(m, v)
        for m, v in zip(gdf["margem_pp"], gdf["venceu"])
    ]
    return gdf, sem_margem


def montar_legenda(gdf):
    legenda = []
    for familia in ("pt", "pl"):
        mascara = gdf["familia"] == familia
        for indice, faixa in enumerate(FAIXAS_TXT):
            n = int((mascara & (gdf["faixa_pp"] == faixa)).sum())
            legenda.append(
                (f"{TITULO_FAMILIA[familia]}  ·  {faixa}", RAMPAS[familia][indice], n)
            )
    n_empate = int((gdf["familia"] == "empate").sum())
    if n_empate:
        legenda.append(("Empate  ·  sem margem definida", mapa.COR_EMPATE, n_empate))
    return legenda


def conferir_faixas(gdf):
    total = len(gdf)
    contagem = gdf["faixa_pp"].value_counts().to_dict()
    impresso = sum(contagem.values())
    print(f"  municipios coloridos: {total} (sem cor: "
          f"{int(gdf['cor'].isna().sum())}, sem margem: "
          f"{int(gdf['margem_pp'].isna().sum())})")
    for familia in ("pt", "pl"):
        mascara = gdf["familia"] == familia
        partes = [
            f"{faixa}={int((mascara & (gdf['faixa_pp'] == faixa)).sum())}"
            for faixa in FAIXAS_TXT
        ]
        print(f"  {TITULO_FAMILIA[familia]} ({int(mascara.sum())}): " + "  ".join(partes))
    print(f"  empates: {int((gdf['familia'] == 'empate').sum())}")
    print(f"  soma das faixas: {impresso} / {total}")
    if impresso != total:
        raise SystemExit("ERRO: a contagem por faixa nao soma o total de municipios")
    if int(gdf["cor"].isna().sum()):
        raise SystemExit("ERRO: existe municipio sem cor")


def maior_por(gdf, familia, coluna):
    alvo = gdf[gdf["familia"] == familia]
    if alvo.empty:
        return None
    return alvo.loc[alvo[coluna].idxmax()]


def proximos_empate(gdf, quantidade):
    alvo = gdf[gdf["familia"] != "empate"]
    alvo = alvo[alvo["margem_pp"].notna()]
    if alvo.empty:
        return None
    return alvo.nsmallest(quantidade, "margem_pp").sort_values("margem_pp")


def nome_municipio(linha):
    return f"{linha['municipio']} ({linha['uf'].upper()})"


def link_municipio(linha):
    return nome_municipio(linha), chave_codigo(linha["codigo_ibge"])


def municipios_empate(gdf):
    alvo = gdf[gdf["familia"] == "empate"]
    if alvo.empty:
        return None
    return alvo.sort_values("municipio")


def analises_destaque(gdf):
    mais_votos_lula = maior_por(gdf, "pt", "votos")
    mais_votos_bolso = maior_por(gdf, "pl", "votos")
    maior_margem_lula = maior_por(gdf, "pt", "margem_pp")
    maior_margem_bolso = maior_por(gdf, "pl", "margem_pp")
    proximos = proximos_empate(gdf, QUANTIDADE_PROXIMOS_EMPATE)

    analises = []
    if mais_votos_lula is not None:
        analises.append((
            "Mais votos para LULA",
            [
                link_municipio(mais_votos_lula),
                f" · {mapa.br(mais_votos_lula['votos'], 0)} votos",
            ],
        ))
    if mais_votos_bolso is not None:
        analises.append((
            "Mais votos para FLAVIO BOLSONARO",
            [
                link_municipio(mais_votos_bolso),
                f" · {mapa.br(mais_votos_bolso['votos'], 0)} votos",
            ],
        ))
    if maior_margem_lula is not None:
        analises.append((
            "Maior vantagem para LULA",
            [
                link_municipio(maior_margem_lula),
                f" · {mapa.br(maior_margem_lula['margem_pp'])} pp",
            ],
        ))
    if maior_margem_bolso is not None:
        analises.append((
            "Maior vantagem para FLAVIO BOLSONARO",
            [
                link_municipio(maior_margem_bolso),
                f" · {mapa.br(maior_margem_bolso['margem_pp'])} pp",
            ],
        ))
    if proximos is not None:
        partes = []
        for indice, (_, linha) in enumerate(proximos.iterrows()):
            if indice:
                partes.append(" · ")
            partes.append(link_municipio(linha))
            partes.append(f" {mapa.br(linha['margem_pp'])} pp")
        analises.append((
            f"Mais próximos de um empate ({len(proximos)})",
            partes,
        ))
    empates = municipios_empate(gdf)
    if empates is not None:
        partes = []
        nomes = []
        for indice, (_, linha) in enumerate(empates.iterrows()):
            if indice:
                partes.append(" · ")
            partes.append(link_municipio(linha))
            nomes.append(linha["municipio"])
        margens = sorted({round(float(v), 2) for v in empates["margem_pp"]})
        if len(margens) == 1:
            sufixo = f" · {mapa.br(margens[0])} pp cada"
        else:
            sufixo = " · margens " + ", ".join(mapa.br(m) for m in margens) + " pp"
        partes.append(sufixo)
        analises.append((
            f"Municípios empatados ({len(empates)})",
            partes,
        ))
    return analises


def ler_votos_brutos():
    por_municipio = defaultdict(int)
    por_candidato = defaultdict(int)
    total = 0
    for regiao in REGIOES:
        caminho = os.path.join(
            BASE, f"dados_{regiao}", f"municipios_{regiao}_2026.csv"
        )
        with open(caminho, encoding="utf-8") as fh:
            for linha in csv.DictReader(fh):
                votos = int(linha["votos"] or 0)
                chave = (linha["uf"], linha["municipio"])
                por_municipio[chave] += votos
                por_candidato[linha["nome_urna"]] += votos
                total += votos
    return por_municipio, por_candidato, total


def escolher_etiquetas(gdf, por_municipio):
    uf_por_mun = dict(zip(gdf["municipio"], gdf["uf"]))
    nomes_chave = juncao_chaves(dict(zip(gdf["municipio"], gdf["municipio"])))
    escolhidos = set()
    for uf, capital in CAPITAIS.items():
        alvo = sem_acento(capital)
        for municipio in gdf["municipio"]:
            if uf_por_mun.get(municipio) != uf:
                continue
            if sem_acento(municipio) == alvo:
                escolhidos.add(municipio)
                break
    faltando = [uf for uf, c in CAPITAIS.items() if sem_acento(c) not in nomes_chave]
    if faltando:
        print(f"  capitais nao localizados no CSV: {faltando}")

    ordena = sorted(
        gdf["municipio"].to_list(),
        key=lambda m: -por_municipio.get((uf_por_mun[m], m), 0),
    )
    extras = [m for m in ordena if m not in escolhidos][:MAIORES_EXTRAS]
    escolhidos.update(extras)
    return escolhidos, uf_por_mun, ordena


def main():
    print("Juntando os GeoJSONs das cinco regioes:")
    feats = juntar_geojsons()
    gdf = gpd.GeoDataFrame.from_features(feats)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4674")
    print(f"Total: {len(gdf)} municipios")

    gdf["geometry"] = gdf.geometry.map(somente_poligonos)
    gdf["geometry"] = gdf.geometry.make_valid()
    gdf["geometry"] = gdf.geometry.map(descartar_ilhas_distantes)
    nulos = int(gdf.geometry.isna().sum())
    invalidos = int((~gdf.geometry.is_valid).sum())
    tipos = gdf.geom_type.value_counts().to_dict()
    print(f"  geometrias nulas: {nulos} · invalidas: {invalidos} · tipos: {tipos}")
    if nulos:
        gdf = gdf[~gdf.geometry.isna()].copy()

    faltando_uf = [uf for uf in ORDEM_UF if uf not in set(gdf["uf"])]
    if faltando_uf:
        print(f"  ATENCAO — UF sem municipio no mapa: {faltando_uf}")

    print("Aplicando a rampa de margem de vitoria:")
    gdf, sem_margem = aplicar_rampa(gdf)
    if sem_margem:
        print(f"  ATENCAO — {sem_margem} municipios sem margem no CSV")
    conferir_faixas(gdf)

    saida = os.path.join(BASE, "mapa_brasil")
    os.makedirs(saida, exist_ok=True)
    destino_geojson = os.path.join(saida, "mapa_vencedor_presidencial_brasil.geojson")
    gdf.to_file(destino_geojson, driver="GeoJSON")
    print(f"  GeoJSON gravado: {len(gdf)} features "
          f"({os.path.getsize(destino_geojson):,} bytes)".replace(",", "."))

    print("Somando os votos dos CSVs brutos:")
    por_municipio, por_candidato, total = ler_votos_brutos()
    print(f"  total: {total:,}".replace(",", "."))

    etiquetas, uf_por_mun, ordena = escolher_etiquetas(gdf, por_municipio)
    print(f"  rotulos: {len(etiquetas)} ({len(CAPITAIS)} capitais + "
          f"{len(etiquetas) - len(CAPITAIS)} maiores cidades)")

    lim = gdf.total_bounds
    figsize = mapa.figsize_para(lim, lado=LADO, minimo=MINIMO)
    print(f"  bbox lon {lim[0]:.2f}..{lim[2]:.2f} lat {lim[1]:.2f}..{lim[3]:.2f}")
    print(f"  figsize {figsize[0]:.2f} x {figsize[1]:.2f} pol")

    pct_bolso = 100 * por_candidato.get("FLAVIO BOLSONARO", 0) / (total or 1)
    pct_lula = 100 * por_candidato.get("LULA", 0) / (total or 1)
    rodape = (
        f"Votos somados no Brasil: {total:,}".replace(",", ".")
        + f"\nBolsonaro {mapa.br(pct_bolso)}  ·  Lula {mapa.br(pct_lula)}"
    )

    mapa.desenhar(
        gdf,
        "brasil",
        "Brasil por município — eleição presidencial, 1º turno (04/10/2026)",
        f"{len(gdf)} municípios em {len(ORDEM_UF)} estados · resultado apurado "
        f"pelo TSE (eleição 6257, cargo 1)",
        rodape,
        etiquetas,
        saida,
        figsize=figsize,
        legenda=montar_legenda(gdf),
        nomes_inset=["FERNANDO DE NORONHA"],
        pos_inset=POS_INSET_BRASIL,
    )

    print("\nHTML interativo:")
    htmlmapa.FASES_TOLERANCIA = FASES_HTML
    feats_html = json.loads(gdf.to_json())["features"]
    feats_html, tol = htmlmapa.decidir_tolerancia(feats_html, ALVO_BYTES_HTML)
    print(f"  tolerancia adotada: {tol}")
    limites = ler_limites_estados()
    htmlmapa.montar(
        "Brasil",
        feats_html,
        por_candidato,
        total,
        ["FERNANDO DE NORONHA"],
        os.path.join(saida, "mapa_vencedor_presidencial_brasil.html"),
        4,
        campos_extras=[("margem_txt", "Margem:"), ("faixa_pp", "Faixa:")],
        usar_cor_prop=True,
        analises=analises_destaque(gdf),
        legenda=montar_legenda(gdf),
        tiles="Esri.WorldImagery",
        limites=limites,
    )

    print("\nArquivos em " + saida)
    for nome in sorted(os.listdir(saida)):
        caminho = os.path.join(saida, nome)
        if os.path.isfile(caminho):
            print(f"  {nome}: {os.path.getsize(caminho):,} bytes".replace(",", "."))


if __name__ == "__main__":
    main()