"""Mapa dos municipios de uma regiao coloridos pelo vencedor da eleicao
presidencial de 2026 (eleicao 6257, cargo 1, 1o turno).

Uso:
    python tse_regiao_mapa.py <regiao> <uf1,uf2,...>

Exemplo:
    python tse_regiao_mapa.py sudeste mg,rj,es,sp

Azul = FLAVIO BOLSONARO (PL)
Vermelho = LULA (PT)
Cinza = empate

Mesmos parametros do mapa de Sao Paulo (tse_mapa_sp.py): dpi 200, fundo #f4f1ea,
contornos brancos de 0,35, cores #1f5fbf / #d92b2b / #b9b9b9, mesma tipografia
de titulo, legenda e rodape. A figsize acompanha o aspecto do estado para nao
deixar tela vazia, e municipios muito distantes que esticam a bbox (como Fernando
de Noronha em PE) ganham um inset.

Os poligonos vem da API de malhas do IBGE, um request por municipio, qualidade
intermediaria, com cache em disco. O codigo do IBGE ja vem no CSV (coluna
codigo_ibge, que e o campo `cdi` do mun-e006257-cm.jws).
"""

import csv
import gzip
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

RAIZ = os.path.dirname(os.path.abspath(__file__))
DPI = 200
FUNDO = "#f4f1ea"
FUNDO_EIXOS = "#dfe6ee"
BORDA = "#ffffff"
LARGURA_BORDA = 0.35
RAIO_ROTULO = 0.12

CORES = {"FLAVIO BOLSONARO": "#1f5fbf", "LULA": "#d92b2b"}
COR_EMPATE = "#b9b9b9"

UFS = {
    "ac": "Acre", "al": "Alagoas", "ap": "Amapá", "am": "Amazonas",
    "ba": "Bahia", "ce": "Ceará", "df": "Distrito Federal", "es": "Espírito Santo",
    "go": "Goiás", "ma": "Maranhão", "mt": "Mato Grosso", "ms": "Mato Grosso do Sul",
    "mg": "Minas Gerais", "pa": "Pará", "pb": "Paraíba", "pr": "Paraná",
    "pe": "Pernambuco", "pi": "Piauí", "rj": "Rio de Janeiro", "rn": "Rio Grande do Norte",
    "rs": "Rio Grande do Sul", "ro": "Rondônia", "rr": "Roraima", "sc": "Santa Catarina",
    "sp": "São Paulo", "se": "Sergipe", "to": "Tocantins",
}

INSETS = {"pe": ["FERNANDO DE NORONHA"]}

QUANTIDADE_ROTULOS = 15

IBGE_MALHA = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{cod}"
    "?formato=application/vnd.geo+json&qualidade=intermediaria"
)


def http(url, tentativas=4):
    ultimo = None
    for tentativa in range(tentativas):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip"}
            )
            with urllib.request.urlopen(req, timeout=90) as r:
                bruto = r.read()
            if bruto[:2] == b"\x1f\x8b":
                bruto = gzip.decompress(bruto)
            return bruto
        except Exception as erro:
            ultimo = erro
            time.sleep(0.6 * (tentativa + 1))
    raise ultimo


def carregar_malha(cod_ibge, saida):
    cache = os.path.join(saida, "malhas", f"{cod_ibge}.json")
    if os.path.exists(cache) and os.path.getsize(cache) > 0:
        bruto = open(cache, "rb").read()
    else:
        bruto = http(IBGE_MALHA.format(cod=cod_ibge))
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "wb") as fh:
            fh.write(bruto)
    return json.loads(bruto.decode("utf-8"))["features"][0]


def br(valor, casas=2):
    return f"{valor:,.{casas}f}".replace(".", "X").replace(",", ".").replace("X", ",")


def totais_por_municipio(caminho_bruto):
    totais = defaultdict(int)
    with open(caminho_bruto, encoding="utf-8") as fh:
        for linha in csv.DictReader(fh):
            totais[(linha["uf"], linha["municipio"])] += int(linha["votos"] or 0)
    return totais


def rotulos_por_uf(venc, totais):
    por_uf = defaultdict(list)
    for linha in venc:
        por_uf[linha["uf"]].append(linha)
    escolhidos = {}
    for uf, linhas in por_uf.items():
        ordenadas = sorted(
            linhas, key=lambda l: -totais.get((uf, l["municipio"]), 0)
        )
        escolhidos[uf] = {l["municipio"] for l in ordenadas[:QUANTIDADE_ROTULOS]}
    return escolhidos


PARTES_DISTANTES_GRAUS = 2.0
RAZAO_AREA_MINIMA = 0.30


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
        or p.area / maior.area >= RAZAO_AREA_MINIMA
        or p.centroid.distance(centro) < PARTES_DISTANTES_GRAUS
    ]
    if len(manter) == len(partes):
        return geom
    return shapely.union_all(manter) if len(manter) > 1 else manter[0]


def montar_geodataframe(linhas, geometrias):
    feats = []
    for linha in linhas:
        cod_ibge = linha["codigo_ibge"]
        feat = geometrias[cod_ibge]
        feat["properties"] = {
            "codigo": linha["codigo"],
            "codigo_ibge": cod_ibge,
            "uf": linha["uf"],
            "uf_nome": linha["uf_nome"],
            "municipio": linha["municipio"],
            "venceu": linha["venceu"],
            "partido": linha["partido"],
            "votos": int(linha["votos"] or 0),
            "pct": linha["pct"],
            "pct_seg": linha["pct_seg"],
            "segundo": linha["segundo"],
        }
        feats.append(feat)
    gdf = gpd.GeoDataFrame.from_features(feats).set_crs("EPSG:4674")
    gdf["geometry"] = gdf.geometry.make_valid()
    gdf["geometry"] = gdf.geometry.map(descartar_ilhas_distantes)
    gdf["cor"] = gdf["venceu"].map(CORES).fillna(COR_EMPATE)
    return gdf


def figsize_para(lim, lado=14.0, minimo=7.0):
    largura = (lim[2] - lim[0]) or 1e-9
    altura = (lim[3] - lim[1]) or 1e-9
    proporcao = largura / altura
    if proporcao >= 1:
        return (lado, max(minimo, lado / proporcao))
    return (max(minimo, lado * proporcao), lado)


def ajustar_texto(texto, largura_polgadas, fonte, fator=0.58, piso=9.0, separador=" — "):
    disponivel = max(1.0, largura_polgadas - 0.5)
    while fonte > piso and len(texto) * fonte * fator / 72.0 > disponivel:
        fonte -= 0.5
    if len(texto) * fonte * fator / 72.0 > disponivel and separador in texto:
        partes = texto.split(separador)
        if len(partes) == 2:
            texto = partes[0] + "\n" + separador.strip() + partes[1]
    return texto, fonte


def desenhar_inset(ax, gdf, pos, largura, altura, titulo):
    extensao = gdf.union_all().bounds
    largura_dados = extensao[2] - extensao[0]
    altura_dados = extensao[3] - extensao[1]
    margem = 0.06
    mini = ax.inset_axes([pos[0], pos[1], largura, altura])
    gdf.plot(ax=mini, color=gdf["cor"], edgecolor=BORDA, linewidth=0.5)
    mini.set_xlim(extensao[0] - largura_dados * margem, extensao[2] + largura_dados * margem)
    mini.set_ylim(extensao[1] - altura_dados * margem, extensao[3] + altura_dados * margem)
    mini.set_aspect("equal")
    mini.set_xticks([])
    mini.set_yticks([])
    for borda in mini.spines.values():
        borda.set_edgecolor("#555555")
        borda.set_linewidth(0.8)
    mini.set_facecolor(FUNDO)
    mini.text(
        0.5, 1.02, titulo, transform=mini.transAxes, fontsize=7,
        ha="center", va="bottom", color="#333333",
    )
    ax.indicate_inset_zoom(mini, edgecolor="#555555", alpha=0.7, linewidth=0.8)


def desenhar(gdf, slug, titulo, subtitulo, rodape, etiquetas, saida,
             nomes_inset=(), figsize=None, legenda=None, titulo_legenda=None,
             pos_inset=None):
    if any(nome in gdf["municipio"].to_list() for nome in nomes_inset):
        gdf_inset = gdf[gdf["municipio"].isin(nomes_inset)].copy()
        gdf = gdf[~gdf["municipio"].isin(nomes_inset)].copy()
    else:
        gdf_inset = None

    lim = gdf.total_bounds
    if figsize is None:
        figsize = figsize_para(lim)

    titulo, fonte_titulo = ajustar_texto(titulo, figsize[0], 19)
    subtitulo, fonte_subtitulo = ajustar_texto(subtitulo, figsize[0], 11, piso=8.0)

    fig, ax = plt.subplots(figsize=figsize, dpi=DPI)
    fig.patch.set_facecolor(FUNDO)
    ax.set_facecolor(FUNDO_EIXOS)

    gdf.plot(ax=ax, color=gdf["cor"], edgecolor=BORDA, linewidth=LARGURA_BORDA)
    ax.set_xlim(lim[0] - RAIO_ROTULO, lim[2] + RAIO_ROTULO)
    ax.set_ylim(lim[1] - RAIO_ROTULO, lim[3] + RAIO_ROTULO)
    ax.set_aspect("equal")
    ax.axis("off")

    ax.text(
        lim[0] - 0.10 * (lim[2] - lim[0]) / figsize[0],
        lim[3] + 0.55 * (lim[3] - lim[1]) / figsize[1],
        titulo,
        fontsize=fonte_titulo,
        fontweight="bold",
        va="bottom",
    )
    ax.text(
        lim[0] - 0.10 * (lim[2] - lim[0]) / figsize[0],
        lim[3] + 0.28 * (lim[3] - lim[1]) / figsize[1],
        subtitulo,
        fontsize=fonte_subtitulo,
        color="#444444",
        va="bottom",
    )

    contagem = gdf["venceu"].value_counts().to_dict()
    n_bolso = int(contagem.get("FLAVIO BOLSONARO", 0))
    n_lula = int(contagem.get("LULA", 0))
    n_outros = int(len(gdf) - n_bolso - n_lula)
    total = len(gdf)

    if legenda is None:
        rotulos_legenda = [
            (f"FLAVIO BOLSONARO — PL   ({n_bolso} municípios, "
             f"{br(100 * n_bolso / total, 1)}%)", CORES["FLAVIO BOLSONARO"]),
            (f"LULA — PT   ({n_lula} municípios, "
             f"{br(100 * n_lula / total, 1)}%)", CORES["LULA"]),
        ]
        if n_outros:
            rotulos_legenda.append(
                (f"Empate / outro   ({n_outros} municípios)", COR_EMPATE)
            )
        titulo_caixa = "Vencedor no município"
    else:
        rotulos_legenda = []
        for item in legenda:
            if len(item) == 3:
                faixa, cor, n = item
                rotulos_legenda.append((f"{faixa}   ({n} municípios)", cor))
            else:
                rotulos_legenda.append((item[0], item[1]))
        titulo_caixa = (
            "Margem de vitória no município" if titulo_legenda is None
            else titulo_legenda
        )

    alvos = [
        Patch(facecolor=cor, edgecolor="#555555", linewidth=0.5, label=rotulo)
        for rotulo, cor in rotulos_legenda
    ]
    ax.legend(
        handles=alvos,
        loc="lower left",
        bbox_to_anchor=(0.0, -0.02),
        frameon=True,
        framealpha=0.96,
        edgecolor="#cccccc",
        fontsize=11,
        title=titulo_caixa,
        title_fontsize=11,
    )

    ax.text(
        lim[2] + 0.55 * (lim[2] - lim[0]) / figsize[0],
        lim[1] - 0.30 * (lim[3] - lim[1]) / figsize[1],
        rodape,
        fontsize=9.5,
        color="#333333",
        ha="right",
        va="bottom",
    )

    for _, linha in gdf.iterrows():
        if linha["municipio"] not in etiquetas:
            continue
        centro = linha["geometry"].representative_point()
        ax.text(
            centro.x,
            centro.y,
            linha["municipio"].title(),
            fontsize=6.4,
            ha="center",
            va="center",
            color="#101010",
            path_effects=[pe.withStroke(linewidth=2.4, foreground="#ffffff")],
        )

    if gdf_inset is not None and len(gdf_inset):
        if pos_inset is None:
            pos_inset = (0.02, 0.52, 0.24, 0.24)
        desenhar_inset(
            ax, gdf_inset, pos_inset[:2], pos_inset[2], pos_inset[3],
            nomes_inset[0].title(),
        )

    fig.subplots_adjust(left=0.03, right=0.97, top=0.95, bottom=0.05)
    destino = os.path.join(saida, f"mapa_vencedor_presidencial_{slug}.png")
    plt.savefig(destino, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  {os.path.basename(destino)}")


def distribuir_votos(chaves, caminho_bruto):
    por_cand = defaultdict(int)
    total = 0
    alvo = set(chaves)
    with open(caminho_bruto, encoding="utf-8") as fh:
        for linha in csv.DictReader(fh):
            chave = (linha["uf"], linha["municipio"])
            if chave not in alvo:
                continue
            votos = int(linha["votos"] or 0)
            total += votos
            por_cand[linha["nome_urna"]] += votos
    base = total or 1
    return {
        "bolsonaro": br(100 * por_cand.get("FLAVIO BOLSONARO", 0) / base),
        "lula": br(100 * por_cand.get("LULA", 0) / base),
        "total": total,
    }


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)

    regiao = sys.argv[1].strip().lower()
    ufs = [u.strip().lower() for u in sys.argv[2].split(",") if u.strip()]
    desconhecidas = [u for u in ufs if u not in UFS]
    if desconhecidas:
        raise SystemExit(f"UF desconhecida: {desconhecidas}")

    dir_dados = os.path.join(RAIZ, "tse_2026_resultados", f"dados_{regiao}")
    saida = os.path.join(RAIZ, "tse_2026_resultados", f"mapa_{regiao}")
    os.makedirs(saida, exist_ok=True)

    csv_vencedor = os.path.join(dir_dados, f"vencedor_presidente_{regiao}.csv")
    csv_bruto = os.path.join(dir_dados, f"municipios_{regiao}_2026.csv")
    if not os.path.exists(csv_vencedor):
        raise SystemExit(f"Rode antes: python tse_regiao_dados.py {regiao} {sys.argv[2]}")

    with open(csv_vencedor, encoding="utf-8") as fh:
        venc = list(csv.DictReader(fh))
    totais = totais_por_municipio(csv_bruto)
    print(f"CSV do TSE: {len(venc)} municipios")

    linhas_por_uf = defaultdict(list)
    for linha in venc:
        linhas_por_uf[linha["uf"]].append(linha)
    ordem = [uf for uf in ufs if uf in linhas_por_uf]
    print("  " + " · ".join(
        f"{UFS[uf]} {len(linhas_por_uf[uf])}" for uf in ordem
    ))

    unicos = sorted({linha["codigo_ibge"] for linha in venc})
    print(f"Malhas IBGE a garantir: {len(unicos)}")
    geometrias = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        for i, (cod, feat) in enumerate(
            zip(unicos, pool.map(lambda c: carregar_malha(c, saida), unicos)), start=1
        ):
            geometrias[cod] = feat
            if i % 250 == 0 or i == len(unicos):
                print(f"  malhas {i}/{len(unicos)}")

    gdfs = {}
    for uf in ordem:
        gdf = montar_geodataframe(linhas_por_uf[uf], geometrias)
        gdf.to_file(
            os.path.join(saida, f"mapa_vencedor_presidencial_{uf}.geojson"),
            driver="GeoJSON",
        )
        gdfs[uf] = gdf
    print(f"GeoJSON por UF gravados: {len(gdfs)}")

    gdf_regiao = montar_geodataframe(venc, geometrias)
    gdf_regiao.to_file(
        os.path.join(saida, f"mapa_vencedor_presidencial_{regiao}.geojson"),
        driver="GeoJSON",
    )
    print(f"GeoJSON {regiao}: {len(gdf_regiao)} features")

    etiquetas = rotulos_por_uf(venc, totais)

    for uf in ordem:
        nome = UFS[uf]
        chaves = {(uf, l["municipio"]) for l in linhas_por_uf[uf]}
        share = distribuir_votos(chaves, csv_bruto)
        desenhar(
            gdfs[uf],
            uf,
            f"{nome} por município — eleição presidencial, 1º turno (04/10/2026)",
            f"{len(gdfs[uf])} municípios · resultado apurado pelo TSE "
            f"(eleição 6257, cargo 1)",
            f"Votos somados em {nome}: {share['total']:,}".replace(",", ".")
            + f"\nBolsonaro {share['bolsonaro']}  ·  Lula {share['lula']}",
            etiquetas[uf],
            saida,
            nomes_inset=INSETS.get(uf, ()),
        )

    share_regiao = distribuir_votos(
        {(l["uf"], l["municipio"]) for l in venc}, csv_bruto
    )
    rotulo = regiao.capitalize()
    desenhar(
        gdf_regiao,
        regiao,
        f"{rotulo} por município — eleição presidencial, 1º turno (04/10/2026)",
        f"{len(gdf_regiao)} municípios em {len(ordem)} estados · resultado apurado "
        f"pelo TSE (eleição 6257, cargo 1)",
        f"Votos somados no {rotulo}: {share_regiao['total']:,}".replace(",", ".")
        + f"\nBolsonaro {share_regiao['bolsonaro']}  ·  Lula {share_regiao['lula']}",
        set(),
        saida,
        nomes_inset=INSETS.get(regiao, ()),
    )


if __name__ == "__main__":
    main()