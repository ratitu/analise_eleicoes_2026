"""Baixa a votacao presidencial de 2026 (eleicao 6257, cargo 1) para todos os
municipios de uma regiao e consolida o vencedor de cada cidade.

Uso:
    python tse_regiao_dados.py <regiao> <uf1,uf2,...>

Exemplos:
    python tse_regiao_dados.py sudeste mg,rj,es,sp
    python tse_regiao_dados.py norte am,pa,to,ap,rr
    python tse_regiao_dados.py centrooeste ms,mt,go,df

Os arquivos vem da camada de dados do proprio resultados.tse.jus.br:
  https://resultados.tse.jus.br/oficial/ele2026/6257/dados/{uf}/{uf}{codTSE}-c0001-e006257-u.jws

Cada arquivo e um JWS: o payload e o segundo segmento, base64url. Os votos do
candidato estao em `vap`; `tvtn` e o total do partido e nao serve.

O cache de JWS e compartilhado em tse_2026_resultados/jws_mun/, de modo que SP
(ja baixado antes) e qualquer regiao ja processada nao sao baixados de novo.

Saidas em tse_2026_resultados/dados_<regiao>/:
  municipios_<regiao>_2026.csv      uma linha por candidato
  vencedor_presidente_<regiao>.csv  uma linha por municipio
"""

import base64
import csv
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

RAIZ = os.path.dirname(os.path.abspath(__file__))
BASE = "https://resultados.tse.jus.br/oficial"
ELEICAO = 6257
CARGO = 1

DIR_JWS = os.path.join(RAIZ, "tse_2026_resultados", "jws_mun")
JWS_MUN = os.path.join(RAIZ, "tse_2026_resultados", "dados_mun", "jws", "mun-e006257-cm.jws")

UFS = {
    "ac": "Acre", "al": "Alagoas", "ap": "Amapá", "am": "Amazonas",
    "ba": "Bahia", "ce": "Ceará", "df": "Distrito Federal", "es": "Espírito Santo",
    "go": "Goiás", "ma": "Maranhão", "mt": "Mato Grosso", "ms": "Mato Grosso do Sul",
    "mg": "Minas Gerais", "pa": "Pará", "pb": "Paraíba", "pr": "Paraná",
    "pe": "Pernambuco", "pi": "Piauí", "rj": "Rio de Janeiro", "rn": "Rio Grande do Norte",
    "rs": "Rio Grande do Sul", "ro": "Rondônia", "rr": "Roraima", "sc": "Santa Catarina",
    "sp": "São Paulo", "se": "Sergipe", "to": "Tocantins",
}

SIGLAS = {
    "22": "PL", "55": "PSD", "13": "PT", "27": "DC", "21": "PCB",
    "16": "PSTU", "70": "AVANTE", "30": "NOVO", "80": "UP",
    "35": "DEMOCRATA", "14": "MISSÃO", "29": "PCO",
}


def http(url, tentativas=4):
    ultimo = None
    for tentativa in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except Exception as erro:
            ultimo = erro
            time.sleep(0.6 * (tentativa + 1))
    raise ultimo


def decodificar_jws(bruto):
    partes = bruto.decode("utf-8").strip().split(".")
    segunda = partes[1]
    segunda += "=" * (-len(segunda) % 4)
    return json.loads(base64.urlsafe_b64decode(segunda))


def numero(valor):
    txt = str(valor).strip()
    if not txt:
        return None
    if "," in txt:
        txt = txt.replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return None


def br(valor, casas=2):
    return f"{valor:,.{casas}f}".replace(".", "X").replace(",", ".").replace("X", ",")


def carregar_municipios(ufs):
    if not os.path.exists(JWS_MUN):
        os.makedirs(os.path.dirname(JWS_MUN), exist_ok=True)
        with open(JWS_MUN, "wb") as fh:
            fh.write(http(f"{BASE}/ele2026/{ELEICAO}/config/mun-e{ELEICAO:06d}-cm.jws"))
    payload = decodificar_jws(open(JWS_MUN, "rb").read())
    achados = []
    for estado in payload["abr"]:
        cd = estado["cd"].lower()
        if cd not in ufs:
            continue
        for mun in estado["mu"]:
            achados.append(
                {
                    "uf": cd,
                    "uf_nome": UFS[cd],
                    "codigo": mun["cd"],
                    "codigo_ibge": mun["cdi"],
                    "municipio": mun["nm"],
                }
            )
    return achados


def url_dados(uf, codigo):
    return (
        f"{BASE}/ele2026/{ELEICAO}/dados/{uf}/{uf}{codigo}"
        f"-c{CARGO:04d}-e{ELEICAO:06d}-u.jws"
    )


def pegar(alvo):
    uf, codigo = alvo["uf"], alvo["codigo"]
    cache = os.path.join(DIR_JWS, f"{uf}{codigo}-c{CARGO:04d}-e{ELEICAO:06d}-u.jws")
    if os.path.exists(cache) and os.path.getsize(cache) > 0:
        bruto = open(cache, "rb").read()
    else:
        bruto = http(url_dados(uf, codigo))
        os.makedirs(DIR_JWS, exist_ok=True)
        with open(cache, "wb") as fh:
            fh.write(bruto)
    return alvo, decodificar_jws(bruto)


def candidatos_cargo(payload, cargo):
    for c in payload.get("carg", []):
        if int(c.get("cd", -1)) != cargo:
            continue
        achados = []
        for agrup in c.get("agr", []):
            listas = []
            if agrup.get("cand"):
                listas.append(agrup["cand"])
            for par in agrup.get("par", []) or []:
                if par.get("cand"):
                    listas.append(par["cand"])
            for lista in listas:
                for cand in lista:
                    achados.append((agrup, cand))
        return achados
    return []


def coletar(alvo, payload):
    linhas = []
    for agrup, cand in candidatos_cargo(payload, CARGO):
        votos = numero(cand.get("vap"))
        if votos is None:
            votos = numero(cand.get("vtn"))
        numero_cand = str(cand.get("n", "")).strip()
        linhas.append(
            {
                "uf": alvo["uf"],
                "uf_nome": alvo["uf_nome"],
                "municipio": alvo["municipio"],
                "codigo": alvo["codigo"],
                "codigo_ibge": alvo["codigo_ibge"],
                "eleicao": ELEICAO,
                "cargo": "Presidente",
                "numero": numero_cand,
                "partido": SIGLAS.get(numero_cand, agrup.get("com", "")),
                "nome_urna": cand.get("nmu", "") or cand.get("nm", ""),
                "nome_completo": cand.get("nm", ""),
                "votos": int(votos) if votos is not None else 0,
                "percentual": cand.get("pvap", "") or "",
                "situacao": cand.get("dvt", "") or "",
            }
        )
    return linhas


def consolidar(brutos):
    por_municipio = {}
    for alvo, payload in brutos:
        chave = (alvo["uf"], alvo["codigo"])
        por_municipio.setdefault(chave, []).extend(coletar(alvo, payload))

    saida = []
    for (uf, codigo), linhas in por_municipio.items():
        validas = [l for l in linhas if l["nome_urna"].strip()]
        validas.sort(key=lambda l: l["votos"], reverse=True)
        if not validas:
            continue
        primeiro = validas[0]
        segundo = validas[1] if len(validas) > 1 else None
        p1 = numero(primeiro["percentual"])
        p2 = numero(segundo["percentual"]) if segundo else None
        empate = bool(segundo and primeiro["votos"] == segundo["votos"])
        if empate:
            venceu = f"{primeiro['nome_urna']} x {segundo['nome_urna']}"
            partida = f"{primeiro['partido']} x {segundo['partido']}"
            obs = f"EMPATE {primeiro['votos']} a {segundo['votos']}"
        else:
            venceu = primeiro["nome_urna"]
            partida = primeiro["partido"]
            obs = ""
        saida.append(
            {
                "uf": uf,
                "uf_nome": primeiro["uf_nome"],
                "municipio": primeiro["municipio"],
                "codigo": codigo,
                "codigo_ibge": primeiro["codigo_ibge"],
                "venceu": venceu,
                "partido": partida,
                "votos": primeiro["votos"],
                "pct": primeiro["percentual"],
                "segundo": segundo["nome_urna"] if segundo else "",
                "partido_segundo": segundo["partido"] if segundo else "",
                "votos_seg": segundo["votos"] if segundo else 0,
                "pct_seg": segundo["percentual"] if segundo else "",
                "margem_pp": br(p1 - p2) if (p1 is not None and p2 is not None) else "",
                "observacao": obs,
            }
        )
    return saida


def escrever(caminho, linhas, colunas):
    with open(caminho, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=colunas)
        w.writeheader()
        w.writerows(linhas)
    print(f"  {os.path.basename(caminho)}: {len(linhas)} linhas, "
          f"{os.path.getsize(caminho):,} bytes")


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)

    regiao = sys.argv[1].strip().lower()
    ufs = [u.strip().lower() for u in sys.argv[2].split(",") if u.strip()]
    desconhecidas = [u for u in ufs if u not in UFS]
    if desconhecidas:
        raise SystemExit(f"UF desconhecida: {desconhecidas}")

    dir_saida = os.path.join(RAIZ, "tse_2026_resultados", f"dados_{regiao}")
    os.makedirs(dir_saida, exist_ok=True)
    print(f"Regiao {regiao}: {', '.join(ufs)}")

    alvos = carregar_municipios(ufs)
    contagem = defaultdict(int)
    for a in alvos:
        contagem[a["uf"]] += 1
    print(f"Municipios: {len(alvos)}  ·  "
          + " · ".join(f"{u.upper()} {contagem[u]}" for u in ufs if contagem[u]))

    brutos = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        for i, (alvo, payload) in enumerate(pool.map(pegar, alvos), start=1):
            brutos.append((alvo, payload))
            if i % 250 == 0 or i == len(alvos):
                print(f"  baixados {i}/{len(alvos)}")
    print(f"OK {len(brutos)}/{len(alvos)}")

    todas = []
    for alvo, payload in brutos:
        todas.extend(coletar(alvo, payload))
    escrever(
        os.path.join(dir_saida, f"municipios_{regiao}_2026.csv"),
        todas,
        ["uf", "uf_nome", "municipio", "codigo", "codigo_ibge", "eleicao", "cargo",
         "numero", "partido", "nome_urna", "nome_completo", "votos", "percentual",
         "situacao"],
    )

    vencedores = consolidar(brutos)
    escrever(
        os.path.join(dir_saida, f"vencedor_presidente_{regiao}.csv"),
        vencedores,
        ["uf", "uf_nome", "municipio", "codigo", "codigo_ibge", "venceu", "partido",
         "votos", "pct", "segundo", "partido_segundo", "votos_seg", "pct_seg",
         "margem_pp", "observacao"],
    )

    contagem_vencedor = defaultdict(int)
    for v in vencedores:
        contagem_vencedor[v["venceu"]] += 1
    print("\nVencedor por municipio:")
    for nome, qtd in sorted(contagem_vencedor.items(), key=lambda kv: -kv[1]):
        print(f"  {nome}: {qtd}")


if __name__ == "__main__":
    main()