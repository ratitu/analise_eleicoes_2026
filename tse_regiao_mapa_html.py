"""Mapa interativo (HTML) dos municipios de uma regiao pelo vencedor da eleicao
presidencial de 2026.

Uso:
    python tse_regiao_mapa_html.py <regiao> <uf1,uf2,...>

Exemplo:
    python tse_regiao_mapa_html.py sudeste mg,rj,es,sp

Azul = FLAVIO BOLSONARO (PL)
Vermelho = LULA (PT)
Cinza = empate

Mesmos parametros do HTML de Sao Paulo (tse_mapa_sp_html.py): Leaflet, popup e
tooltip por municipio com o percentual, legenda com a contagem e rodape com o
total de votos. Gera um HTML por UF e um HTML unico da regiao.
"""

import csv
import json
import os
import sys
from collections import defaultdict

import folium
from folium import elements
from shapely.geometry import mapping, shape

RAIZ = os.path.dirname(os.path.abspath(__file__))

FASES_TOLERANCIA = (0.0009, 0.0015, 0.0025, 0.004, 0.008, 0.015)
ALVO_BYTES = 900_000
ALVO_BYTES_REGIAO = 2_500_000

CORES = {"FLAVIO BOLSONARO": "#1f5fbf", "LULA": "#d92b2b"}
COR_EMPATE = "#b9b9b9"
COR_LIMITE = "#ffe066"
PESO_LIMITE = 3.0

UFS = {
    "ac": "Acre", "al": "Alagoas", "ap": "Amapá", "am": "Amazonas",
    "ba": "Bahia", "ce": "Ceará", "df": "Distrito Federal", "es": "Espírito Santo",
    "go": "Goiás", "ma": "Maranhão", "mt": "Mato Grosso", "ms": "Mato Grosso do Sul",
    "mg": "Minas Gerais", "pa": "Pará", "pb": "Paraíba", "pr": "Paraná",
    "pe": "Pernambuco", "pi": "Piauí", "rj": "Rio de Janeiro", "rn": "Rio Grande do Norte",
    "rs": "Rio Grande do Sul", "ro": "Rondônia", "rr": "Roraima", "sc": "Santa Catarina",
    "sp": "São Paulo", "se": "Sergipe", "to": "Tocantins",
}

CENTRO_EXCLUIR = {"pe": ["FERNANDO DE NORONHA"]}


def br(valor, casas=2):
    return f"{valor:,.{casas}f}".replace(".", "X").replace(",", ".").replace("X", ",")


def simplify(feat, tol):
    geom = shape(feat["geometry"]).simplify(tol, preserve_topology=True)
    return {"type": "Feature", "properties": feat["properties"], "geometry": mapping(geom)}


def decidir_tolerancia(feats, alvo_bytes):
    compacto = feats
    tol = FASES_TOLERANCIA[-1]
    for candidata in FASES_TOLERANCIA:
        compacto = [simplify(feat, candidata) for feat in feats]
        tamanho = len(json.dumps(compacto, separators=(",", ":")).encode("utf-8"))
        print(f"  tolerancia {candidata}: {tamanho:,} bytes")
        if tamanho <= alvo_bytes:
            tol = candidata
            break
    return compacto, tol


def carregar(mapa_dir, chave, alvo_bytes):
    caminho = os.path.join(mapa_dir, f"mapa_vencedor_presidencial_{chave}.geojson")
    feats = json.load(open(caminho, encoding="utf-8"))["features"]
    print(f"  GeoJSON de entrada com {len(feats)} municipios")
    feats, tol = decidir_tolerancia(feats, alvo_bytes)
    print(f"  tolerancia adotada: {tol}")
    return feats


def popup_html(p):
    venceu = p.get("venceu", "")
    partido = p.get("partido", "")
    pct = p.get("pct", "")
    segundo = p.get("segundo", "")
    pct_seg = p.get("pct_seg", "")
    uf = p.get("uf", "")
    codigo = p.get("codigo", "")
    cor = CORES.get(venceu, COR_EMPATE)
    municipio = p.get("municipio", "").title()
    if not venceu:
        return f"<b>{municipio}</b><br>Sem resultado"
    segunda_linha = ""
    if segundo:
        segunda_linha = (
            "<br><span style='color:#666'>2o lugar:</span> "
            f"{segundo.title()} ({pct_seg}%)"
        )
    return (
        f"<div style='line-height:1.5'>"
        f"<b>{municipio}</b> <span style='color:#888'>/ {uf.upper()}</span>"
        f"<br><span style='display:inline-block;width:10px;height:10px;"
        f"background:{cor};border:1px solid #333'></span> "
        f"{venceu.title()} ({partido}) <b>{pct}%</b>"
        f"{segunda_linha}"
        f"<br><span style='color:#999;font-size:11px'>código TSE {codigo}</span>"
        f"</div>"
    )


def estilo(feature, usar_cor_prop=False):
    if usar_cor_prop:
        return {
            "fillColor": feature["properties"].get(
                "cor", CORES.get(feature["properties"].get("venceu"), COR_EMPATE)
            ),
            "color": "#ffffff",
            "weight": 0.6,
            "fillOpacity": 0.85,
        }
    return {
        "fillColor": CORES.get(feature["properties"].get("venceu"), COR_EMPATE),
        "color": "#ffffff",
        "weight": 0.6,
        "fillOpacity": 0.85,
    }


def linha_swatch(rotulo, cor):
    return (
        "<div>"
        f"<span style='display:inline-block;width:12px;height:12px;"
        f"background:{cor};border:1px solid #333;vertical-align:middle'></span>"
        f" {rotulo}</div>"
    )


def linha_analise(rotulo, detalhe):
    partes = []
    if isinstance(detalhe, str):
        partes.append(detalhe)
    else:
        for parte in detalhe:
            if isinstance(parte, str):
                partes.append(parte)
            else:
                texto, codigo = parte
                partes.append(
                    "<a class='destaque-link' href='#' "
                    f"data-codigo='{codigo}' "
                    "style='color:#0b4f9c;text-decoration:underline;"
                    "cursor:pointer' "
                    f"title='Ir para {texto}'>{texto}</a>"
                )
    return (
        "<div style='margin-bottom:4px'>"
        f"<span style='color:#666;font-size:11px'>{rotulo}</span><br>"
        f"<b>{''.join(partes)}</b></div>"
    )


def script_destaques(nome_mapa, nome_camada):
    return (
        "<script>"
        "function iniciarDestaques(){"
        f"var camadaVar=(typeof {nome_camada}!=='undefined')?'{nome_camada}':"
        "Object.keys(window).filter(k=>k.startsWith('geo_json_')&&"
        "!k.endsWith('_styler')&&!k.endsWith('_highlighter')&&"
        "!k.endsWith('_onEachFeature')&&!k.endsWith('_add'))[0];"
        f"var mapaVar=(typeof {nome_mapa}!=='undefined')?'{nome_mapa}':"
        "Object.keys(window).filter(k=>k.startsWith('map_'))[0];"
        "if(!mapaVar||!window[mapaVar]||!camadaVar||!window[camadaVar]){"
        "setTimeout(iniciarDestaques,100);return;}"
        f"var m=window[mapaVar],c=window[camadaVar],i={{}};"
        "c.eachLayer(function(l){var k=l.feature&&l.feature.properties"
        "&&l.feature.properties.codigo_ibge;"
        "if(k!==undefined&&k!==null){i[String(k)]=l;}});"
        "if(!m.getPane('paneDestaque')){"
        "var pane=m.createPane('paneDestaque');"
        "pane.style.zIndex=650;pane.style.pointerEvents='none';}"
        "var hl=null,camadaHl=null,estiloBase=null;"
        "function limpar(){"
        "if(hl){if(m.hasLayer(hl)){m.removeLayer(hl);}hl=null;}"
        "if(camadaHl&&estiloBase){camadaHl.setStyle(estiloBase);}"
        "camadaHl=null;estiloBase=null;}"
        "function marcar(l){"
        "var b=l.getBounds().getCenter();"
        "hl=L.circleMarker([b.lat,b.lng],{pane:'paneDestaque',radius:10,"
        "color:'#111111',weight:3,opacity:1,fillColor:'#ffd60a',"
        "fillOpacity:1}).addTo(m);"
        "estiloBase={fillColor:l.options.fillColor,color:l.options.color,"
        "weight:l.options.weight,opacity:l.options.opacity,"
        "dashArray:l.options.dashArray,fillOpacity:l.options.fillOpacity};"
        "camadaHl=l;"
        "l.setStyle({color:'#111111',weight:3,opacity:1,dashArray:'6,3',"
        "fillOpacity:0.95});"
        "l.bringToFront();}"
        "var links=document.querySelectorAll('a.destaque-link');"
        "for(var p=0;p<links.length;p++){links[p].addEventListener("
        "'click',function(e){e.preventDefault();"
        "var l=i[this.getAttribute('data-codigo')];if(!l){return;}"
        "if(camadaHl===l){limpar();return;}"
        "limpar();marcar(l);"
        "m.flyToBounds(l.getBounds(),{padding:[48,48],maxZoom:10,"
        "duration:0.7});"
        "m.once('moveend',function(){if(camadaHl===l&&l.openPopup){l.openPopup();}});"
        "});}"
        "}"
        "iniciarDestaques();"
        "</script>"
    )


def script_colapsaveis():
    return (
        "<script>(function(){"
        "var cabs=document.querySelectorAll('.colapsavel-cabecalho');"
        "for(var p=0;p<cabs.length;p++){"
        "cabs[p].addEventListener('click',function(){"
        "var corpo=document.getElementById("
        "this.getAttribute('data-alvo'));if(!corpo){return;}"
        "var aberto=corpo.style.display!=='none';"
        "corpo.style.display=aberto?'none':'';"
        "var seta=this.querySelector('.colapsavel-seta');"
        "if(seta){seta.textContent=aberto?'\\u25B6':'\\u25BC';}"
        "});}"
        "})();</script>"
    )


def painel_analises(analises):
    linhas = [
        "<div class='colapsavel-cabecalho' data-alvo='corpo-destaques' "
        "style='font-weight:bold;font-size:13px;margin-bottom:6px;"
        "cursor:pointer;user-select:none;display:flex;"
        "justify-content:space-between;align-items:center;gap:12px'>"
        "<span>Destaques</span>"
        "<span class='colapsavel-seta' style='font-size:10px'>&#9660;</span>"
        "</div>"
        "<div id='corpo-destaques'>"
    ]
    for rotulo, detalhe in analises:
        linhas.append(linha_analise(rotulo, detalhe))
    linhas.append("</div>")
    return (
        "<div id='painel-destaques' style=\"position:fixed;top:12px;right:12px;z-index:9999;"
        "background:#ffffff;border:1px solid #bbb;border-radius:4px;"
        "padding:10px 14px;font-family:Helvetica,Arial,sans-serif;"
        "font-size:12px;box-shadow:0 1px 6px rgba(0,0,0,.3);line-height:1.6\">"
        + "".join(linhas)
        + "</div>"
    )


def montar(rotulo, feats, por_cand, total, excluir_centro, destino, zoom,
           campos_extras=(), usar_cor_prop=False, analises=None, legenda=None,
           tiles="CartoDB positron", limites=None):
    base = [f for f in feats if f["properties"].get("municipio") not in excluir_centro]
    if not base:
        base = feats
    centro_lat = sum(shape(f["geometry"]).centroid.y for f in base) / len(base)
    centro_lon = sum(shape(f["geometry"]).centroid.x for f in base) / len(base)

    mapa = folium.Map(
        location=[centro_lat, centro_lon],
        zoom_start=zoom,
        tiles=tiles,
        control_scale=True,
        prefer_canvas=True,
    )

    camada = folium.GeoJson(
        data={"type": "FeatureCollection", "features": feats},
        name="Vencedor por municipio",
        style_function=lambda f: estilo(f, usar_cor_prop),
        highlight_function=lambda _: {
            "fillColor": "#ffdd00",
            "color": "#333333",
            "weight": 1.6,
            "fillOpacity": 0.95,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["municipio", "venceu", "partido", "pct"]
            + [c for c, _ in campos_extras],
            aliases=["Municipio:", "Vencedor:", "Partido:", "%:"]
            + [a for _, a in campos_extras],
            labels=True,
            sticky=True,
            style=(
                "background-color:#ffffff;border:1px solid #999;"
                "font-size:12px;padding:4px 8px;border-radius:3px"
            ),
        ),
        popup=folium.GeoJsonPopup(
            fields=["municipio", "uf", "venceu", "partido", "pct"]
            + [c for c, _ in campos_extras],
            aliases=["Municipio", "UF", "Vencedor", "Partido", "%"]
            + [a for _, a in campos_extras],
            labels=True,
            localize=True,
            sticky=False,
            max_width=320,
        ),
        zoom_on_click=True,
    )
    camada.add_to(mapa)
    if limites is not None:
        folha = folium.GeoJson(
            data=limites,
            name="Limites dos estados",
            style_function=lambda _: {
                "color": COR_LIMITE,
                "weight": PESO_LIMITE,
                "opacity": 0.95,
            },
            overlay=True,
            control=True,
            show=True,
            smooth_factor=0.6,
            interactive=False,
        )
        folha.add_to(mapa)
        folium.LayerControl(collapsed=True, position="bottomright").add_to(mapa)

    contagem = defaultdict(int)
    for f in feats:
        venceu = f["properties"].get("venceu")
        contagem[venceu if venceu in CORES else "EMPATE"] += 1

    linhas = [
        "<div class='colapsavel-cabecalho' data-alvo='corpo-legenda' "
        "style='font-weight:bold;font-size:14px;margin-bottom:4px;"
        "cursor:pointer;user-select:none;display:flex;"
        "justify-content:space-between;align-items:center;gap:12px'>"
        f"<span>Presidencial 2026 · {rotulo} · 1º turno</span>"
        "<span class='colapsavel-seta' style='font-size:10px'>&#9660;</span>"
        "</div>"
        "<div id='corpo-legenda'>"
    ]
    if legenda is None:
        linhas.append(linha_swatch(
            f"FLAVIO BOLSONARO (PL) — {contagem['FLAVIO BOLSONARO']} municipios",
            CORES["FLAVIO BOLSONARO"],
        ))
        linhas.append(linha_swatch(
            f"LULA (PT) — {contagem['LULA']} municipios",
            CORES["LULA"],
        ))
        if contagem["EMPATE"]:
            linhas.append(linha_swatch(
                f"Empate / outro — {contagem['EMPATE']} municipio",
                COR_EMPATE,
            ))
    else:
        for item in legenda:
            if len(item) == 3:
                faixa, cor, n = item
                linhas.append(linha_swatch(f"{faixa}   ({n} municipios)", cor))
            else:
                linhas.append(linha_swatch(item[0], item[1]))
    linhas.append(
        "<div style='color:#666;font-size:11px;margin-top:5px;"
        "border-top:1px solid #ddd;padding-top:5px'>"
        "Passe o mouse para ver os dados · clique para dar zoom</div>"
    )
    linhas.append("</div>")

    painel_legenda = (
        "<div id='painel-legenda' style=\"position:fixed;top:12px;left:56px;z-index:9999;"
        "background:#ffffff;border:1px solid #bbb;border-radius:4px;"
        "padding:10px 14px;font-family:Helvetica,Arial,sans-serif;"
        "font-size:13px;box-shadow:0 1px 6px rgba(0,0,0,.3);line-height:1.7\">"
        + "".join(linhas)
        + "</div></div>"
    )
    mapa.get_root().html.add_child(elements.Element(painel_legenda))

    if analises:
        mapa.get_root().html.add_child(
            elements.Element(painel_analises(analises))
        )
        mapa.get_root().html.add_child(
            elements.Element(script_destaques(mapa.get_name(), camada.get_name()))
        )

    base_total = total or 1
    pct_bolso = 100 * por_cand.get("FLAVIO BOLSONARO", 0) / base_total
    pct_lula = 100 * por_cand.get("LULA", 0) / base_total
    rodape = (
        "<div style='position:fixed;bottom:18px;left:56px;z-index:9999;"
        "background:#fff;border:1px solid #bbb;border-radius:4px;padding:8px 12px;"
        "font-family:Helvetica,Arial,sans-serif;font-size:12px;color:#444;"
        "box-shadow:0 1px 6px rgba(0,0,0,.3)'>"
        f"{total:,} votos presidenciais · ".replace(",", ".")
        + f"Bolsonaro {br(pct_bolso)} · Lula {br(pct_lula)} · "
        f"Fonte: TSE (eleicao 6257)</div>"
    )
    mapa.get_root().html.add_child(elements.Element(rodape))
    mapa.get_root().html.add_child(elements.Element(script_colapsaveis()))

    mapa.save(destino)
    print(
        f"  {os.path.basename(destino)}: {os.path.getsize(destino):,} bytes, "
        f"Bolsonaro {br(pct_bolso)} · Lula {br(pct_lula)}"
    )


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)

    regiao = sys.argv[1].strip().lower()
    ufs = [u.strip().lower() for u in sys.argv[2].split(",") if u.strip()]
    desconhecidas = [u for u in ufs if u not in UFS]
    if desconhecidas:
        raise SystemExit(f"UF desconhecida: {desconhecidas}")

    mapa_dir = os.path.join(RAIZ, "tse_2026_resultados", f"mapa_{regiao}")
    csv_bruto = os.path.join(
        RAIZ, "tse_2026_resultados", f"dados_{regiao}",
        f"municipios_{regiao}_2026.csv",
    )
    if not os.path.exists(csv_bruto):
        raise SystemExit(f"Rode antes: python tse_regiao_dados.py {regiao} {sys.argv[2]}")

    acumulado = defaultdict(int)
    total_regiao = 0
    with open(csv_bruto, encoding="utf-8") as fh:
        for linha in csv.DictReader(fh):
            votos = int(linha["votos"] or 0)
            total_regiao += votos
            acumulado[(linha["uf"], linha["nome_urna"])] += votos
    print(f"Votos presidenciais no {regiao}: {total_regiao:,}".replace(",", "."))

    for uf in ufs + [regiao]:
        chave = regiao if uf == regiao and uf not in UFS else uf
        rotulo = UFS[uf] if uf in UFS else regiao.capitalize()
        alvo_bytes = ALVO_BYTES_REGIAO if chave == regiao else ALVO_BYTES
        print(f"\n{rotulo}:")
        feats = carregar(mapa_dir, chave, alvo_bytes)
        if chave == regiao:
            por_cand = defaultdict(int)
            for (_, nome), votos in acumulado.items():
                por_cand[nome] += votos
            total = total_regiao
        else:
            por_cand = defaultdict(int)
            total = 0
            for (u, nome), votos in acumulado.items():
                if u == uf:
                    por_cand[nome] += votos
                    total += votos
        montar(
            rotulo,
            feats,
            por_cand,
            total,
            CENTRO_EXCLUIR.get(uf, []),
            os.path.join(mapa_dir, f"mapa_vencedor_presidencial_{chave}.html"),
            7 if chave == regiao else 8,
        )


if __name__ == "__main__":
    main()