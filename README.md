# Mapas da eleição presidencial de 2026 — TSE (Brasil)

Mapa coroplético interativo das eleições presidenciais de 2026 — eleição 6257,
cargo 1, 1º turno (04/10/2026) — colorido pela **margem de vitória** de cada município.

## Visualizar o mapa

Abra `index.html` no navegador (ou arraste o arquivo para o navegador).
Funciona totalmente offline — as libs Leaflet/Folium vêm de CDN e as 5.571
features (municípios) estão embutidas no HTML.

## Resultado Brasil (5.571 municípios, 118.960.495 votos)

| Candidato | Votos | % | Municípios vencidos |
| --- | ---: | ---: | ---: |
| Flávio Bolsonaro (PL) | 55.957.681 | 47,04% | 2.906 |
| Lula (PT) | 53.716.127 | 45,15% | 2.663 |
| *Empate* | — | — | 2 |

> Dois municípios terminaram empatados em cinza: **Trabiju/SP** e
> **Crixás do Tocantins/TO**.

## Como ler a cor

A intensidade da cor representa a **margem de vitória** — quantos pontos
percentuais o vencedor levou sobre o segundo colocado. **Não** é o total de
votos. São 5 faixas discretas em cada família de cor (uma rampa independente
por partido, nunca misturadas):

| Faixa (pp) | PT (Lula) | PL (Bolsonaro) |
| --- | ---: | ---: |
| 0 a 2 | `#f5d6d2` | `#cedff9` |
| 2 a 5 | `#fdada4` | `#9ec7ff` |
| 5 a 10 | `#fd8377` | `#6eaaff` |
| 10 a 20 | `#f2544c` | `#4083ec` |
| 20 ou mais | `#d92b2b` | `#1f5fbf` |

Mais claro = margem apertada. Mais escuro = vitória folgada. Empate = `#b9b9b9`.
A separação entre degraus vizinhos foi desenhada para ter contraste perceptível
(≥ 1,25:1) mesmo em município pequeno.

## Funcionalidades do HTML interativo

- **Legenda** com os 5 degraus de cada família e a contagem de municípios em cada faixa.
- **Painel "Destaques"** (painel lateral direito) com os destaques da eleição:
  - Cidade com mais votos para LULA (São Paulo/SP)
  - Cidade com mais votos para FLAVIO BOLSONARO (Rio de Janeiro/RJ)
  - Maior percentual de votos para LULA (Bonfim do PI)
  - Maior percentual de votos para FLAVIO BOLSONARO (Nova Pádua/RS)
  - Maior vantagem para LULA (80,13 pp)
  - Maior vantagem para FLAVIO BOLSONARO (79,64 pp)
  - Mais próximo de empate (São Joaquim de Bicas/MG, 0,01 pp)
  - Municípios empatados (2) (CRIXÁS DO TOCANTINS/TO · TRABIJU/SP · 0,00 pp cada)
- Nomes das cidades são **links clicáveis**: clique para voar até o município
  no mapa e destacá-lo.
- **Camada de satélite** (Esri World Imagery) por baixo.
- Tooltip/popup com município, vencedor, partido, percentual, margem e faixa.
- Painéis colapsáveis (legenda / destaques).

## Como foi gerado

1. Baixar os dados do TSE e consolidar o vencedor de cada município:
   `python tse_regiao_dados.py <regiao> <uf1,uf2,...>` (ex.: sudeste mg,rj,es,sp)

2. Gerar o mapa da região:
   `python tse_regiao_mapa.py <regiao> <uf1,uf2,...>`

3. Juntar as 5 regiões no mapa do Brasil (PNG + GeoJSON + HTML):
   `python tse_mapa_brasil.py`

Os passos 1 e 2 usam os scripts deste repositório; o passo 3 cria o `index.html`.
Os downloads do TSE ficam em cache (`tse_2026_resultados/jws_mun/`) e não são
refeitos.

## Dados e fontes

- **Fonte:** camada de dados do próprio [TSE](https://resultados.tse.jus.br/oficial/ele2026/6257/).
- **Geometrias:** malhas de município do [IBGE](https://servicodados.ibge.gov.br/).
- **Atualização:** os arquivos de cache (`tse_2026_resultados/jws_mun/` e
  `tse_2026_resultados/dados_*/`) já contêm os dados processados e não são
  refeitos automaticamente; delete os arquivos individuais para forçar refetch.

## Cavalo de batalha — não cometer esses erros

| Erro | Consequência |
| --- | --- |
| `float("2,35")` quebra → **sempre use `numero()` / `.map(numero)`** | Dados corrompidos |
| `glob("dados_*/municipios_*.csv")` → conta Nordeste duas vezes | Total inflado para 200.677.105 em vez de 118.960.495 |
| `tse_regiao_dados.py` é off-limits: só read, nunca modifique | Dados inconsistentes |
| Comentar `#` inline → **hook rejeita** | Quebra de formatação |
| Execução em background (`nohup … &`) com timeout 120s → **mata processo** deixando HTML de 0 bytes | Resultado inválido |

## Licença

Este trabalho usa dados abertos do TSE (domínio público). O código-fonte
(4 scripts Python) está disponível para fins de transparência e reprodutibilidade.
O HTML pode ser compartilhado livremente.