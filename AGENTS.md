# AGENTS.md

Instructions for AI agents working in this repo. Omit anything here that an
agent would not get wrong without help.

## Environment

- **Python**: `/home/ratitu/miniconda3/envs/qgis_env/bin/python` (3.12,
  geopandas 1.0.1, matplotlib 3.10.9, folium 0.19.4, xyzservices).
  There is no venv activation step and no build step — invoke that interpreter
  directly. The system `python` is NOT the right one.
- **Not a git repository.** `git rev-parse` fails. Do not run git commands,
  do not ask for a commit SHA, do not attempt `git diff`-based review.
- **No tests, no linter, no type checker, no CI, no pre-commit.** Verification
  is numeric/manual: run the script, then parse the emitted GeoJSON/HTML/PNG
  and assert counts and invariants with a short Python snippet.

### Recreating the environment (another machine)

The interpreter path above assumes `qgis_env` already exists. To rebuild it,
these are the commands that actually created it (from
`envs/qgis_env/conda-meta/history`):

```bash
/home/ratitu/miniconda3/bin/conda create -n qgis_env python=3.12.4
/home/ratitu/miniconda3/bin/conda install -c conda-forge qgis
/home/ratitu/miniconda3/bin/python -m pip install geopandas folium xyzservices
```

QGIS pulls in gdal/pyproj/fiona/shapely/numpy. The pip line carries only the
three that conda-forge qgis does not provide. Versions currently resolved:
geopandas 1.0.1, matplotlib 3.10.9, folium 0.19.4, xyzservices 2025.10.0,
shapely 2.1.0, pyproj 3.7.2, fiona 1.10.1, numpy 2.4.4, pandas 2.3.3,
branca 0.8.2 (folium's peer dep), mapclassify 2.10.0.

The scripts only need geopandas/matplotlib/folium/xyzservices at runtime —
`branca` and `mapclassify` are installed but unused by this repo.

## Pipeline order (data -> map)

1. `tse_regiao_dados.py <regiao> <uf1,uf2,...>` — downloads TSE JWS per
   municipality, writes `tse_2026_resultados/dados_<regiao>/`.
2. `tse_regiao_mapa.py <regiao> <uf1,uf2,...>` — reads those CSVs, fetches
   IBGE malhas, writes per-UF + regional GeoJSONs into
   `tse_2026_resultados/mapa_<regiao>/`.
3. `tse_mapa_brasil.py` — joins the 5 regional GeoJSONs, applies the
   margin ramp, writes `tse_2026_resultados/mapa_brasil/` (PNG + GeoJSON + HTML).

`tse_mapa_brasil.py` is the main entrypoint. `tse_mapa_sp.py` is a separate,
self-contained Sao Paulo map (645 municipalities) with its own `desenhar()`.

## Caches — do not re-download

- TSE JWS responses are cached in `tse_2026_resultados/jws_mun/` (one file per
  municipality, ~5571 files). A file that exists and is non-empty is reused;
  the TSE is never re-queried. Delete the file to force a refetch.
- IBGE malha responses are cached in `tse_2026_resultados/mapa_<regiao>/malhas/`.
- The municipality config JWS is cached at
  `tse_2026_resultados/dados_mun/jws/mun-e006257-cm.jws`.

## Data traps (these will silently corrupt output)

- **pt-BR decimal commas.** `margem_pp`, `pct`, `pct_seg` in the CSVs and in
  the GeoJSON `properties` are strings like `"2,35"` / `"69,10"`, dtype object.
  `float("2,35")` raises and `astype(float)` on the column breaks. Always run
  them through `numero()` (or `.map(numero)`) before comparing or sorting.
- `pct_seg` is the runner-up's percentage; `margem_pp` is the winner's margin
  over the runner-up in percentage points. `margem_pp` is the only valid source
  for the color ramp — never use raw vote totals.
- **Region naming.** `tse_mapa_brasil.py` expects `centro_oeste` (with
  underscore). The `tse_regiao_dados.py` docstring example says `centrooeste`,
  which is wrong — that would create a `dados_centrooeste/` dir the Brasil
  script never reads. The Nordeste pipeline is also inconsistent:
  `tse_nordeste_dados.py` writes to `dados_mun_nordeste/`, not `dados_nordeste/`.
- `tse_regiao_dados.py` takes the region as a free-form string and does not
  validate it; a typo silently creates a new empty dir instead of erroring.
- **Only 5 CSV files are authoritative.** National totals come from
  `dados_<regiao>/municipios_<regiao>_2026.csv` for `nordeste, sudeste,
  centro_oeste, norte, sul` — exactly what `ler_votos_brutos()` iterates.
  Never `glob("dados_*/municipios_*.csv")`, and never touch `dados_mun/`: its
  `municipios_sp_2026.csv` mixes the 2022 slate into 2026 data (candidate `13`
  appears as both FERNANDO HADDAD and LULA; TARCÍSIO/VERA LÚCIA/CARLOS
  MACHADO are 2022-only), which inflates the total to 200.677.105 instead of
  118.960.495. `dados_nordeste/` and `dados_mun_nordeste/` are byte-identical
  duplicates, so globbing also double-counts the Northeast.

## Code rules

- **Never refactor the shared modules** `tse_regiao_mapa.py` and
  `tse_regiao_mapa_html.py`. To change their behavior, add an optional
  parameter with a default that preserves existing behavior, and pass it from
  the caller. State/regional maps must keep rendering unchanged.
- **`tse_regiao_dados.py` is out of scope** — the owner declared it off-limits.
- **Style**: Portuguese, without accents, in identifiers, messages, docstrings
  and UI labels (`municipio`, `venceu`, `Sao Paulo`, `Brasilia`). Match this.
- **No inline `#` comments** — a hook rejects them. Use a string literal or a
  comment on its own line only if unavoidable.
- **Never suppress type errors** (`as any`, `@ts-ignore`, `@ts-expect-error`)
  and never leave an empty `except:`.

## Tooling gotchas

- The `write` tool corrupts the indentation of the first line of a new nesting
  level. After creating or rewriting a Python file, always run
  `/home/ratitu/miniconda3/envs/qgis_env/bin/python -m py_compile <file>` and fix
  before running.
- A full `tse_mapa_brasil.py` run takes ~80-120s. The default shell timeout is
  120s and will kill a backgrounded (`nohup ... &`) process mid-run, leaving a
  0-byte HTML. Run it in the foreground with a timeout of 420000ms+.
- `look_at` / the multimodal-looker agent cannot read images in this model.
  Validate PNGs numerically (PIL + numpy pixel counts) and say so when a human
  visual check is advisable.
- Playwright needs
  `executable_path='/home/ratitu/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome'`
  and `args=['--no-sandbox', '--disable-gpu']`. The `chromium_headless_shell`
  build is not installed.

## Verified baseline (mapa_brasil)

5571 municipalities, 118.960.495 votes, Bolsonaro 47,04% / Lula 45,15%.
Winner counts: FLAVIO BOLSONARO 2906, LULA 2663, ties 2 (TRABIJU/SP,
CRIXAS DO TOCANTINS/TO). Margin bands (0-2 / 2-5 / 5-10 / 10-20 / 20+ pp):
PT 82/129/151/295/2006, PL 88/124/264/582/1848. The band counts must sum to
5571 and no municipality may be left uncolored — assert both after any change.

## Known dead end: Sao Paulo by electoral zone

A request for Sao Paulo maps **by zona eleitoral** (presidente cargo 1 +
governador cargo 3) was investigated and is **blocked on external data, not
on code**. Do not re-run this research. Verified across three independent
paths (a 17-minute librarian sweep plus direct endpoint probing):

- **Votes per zone — no public endpoint.** Every URL pattern under
  `resultados.tse.jus.br/oficial/ele2026/6257/dados/sp/` returns 404
  (`-z.jws`, `-z0001.jws`, `-z0020.jws`, `-z1`, `-z001`, `-z01`, `-z00001`,
  `-u`/`-d`/`-v` variants, `v001`/`v002`/`v003` prefixes). Zone config files
  (`config/zona-*.jws`, `config/mun-zona-*.jws`) also 404. The only config
  that exists is `config/mun-e006257-cm.jws`, which lists SP's 57 zone codes
  but carries no results.
- **Zone polygons — no public source.** TSE map-download pages return 403
  Access Denied. IBGE malhas have no electoral-zone level (municipio works;
  distritos/subdistritos/setores do not correspond to zones).
- **Governor cargo code — unknown.** `c0003` (and `c00003`, `c03`, `c3`,
  `c0006`, `c0007`) all 404. The municipality endpoint only ever returns
  `carg` with a single entry, `cd=1`.

If this task comes back, the viable fallback is a **municipal** Sao Paulo map
(`tse_mapa_sp.py`) with the margin ramp plus a list of the 57 zone codes —
not a per-zone choropleth. Do not fabricate zone-level numbers.
