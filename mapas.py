"""
Mapas de prevalência por território (moradia do paciente) — Pirajá.

  * Município: malha municipal do IBGE (MMD 2025), guardada em versão
    simplificada por UF em geo/malha_municipal_2025/<UF>.geojson.gz.
  * Bairro: Malha de Bairros do Censo 2022 do IBGE, guardada simplificada por
    UF em geo/malha_bairros_2022/<UF>.geojson.gz (só existe para os municípios
    com divisão oficial em bairros). Alternativa: arquivo de limites enviado
    por quem usa (GeoJSON ou shapefile .zip), por exemplo o da prefeitura.

Dois produtos: uma figura no padrão cartográfico (matplotlib — rosa dos ventos,
escala, grade de coordenadas, mapa de localização, legenda em classes, fonte)
para artigo/PDF, e uma versão interativa (plotly, só SVG — não depende de
servidor de mapas externo).
"""
from __future__ import annotations

import gzip
import io
import json
import math
import tempfile
import unicodedata
import zipfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch, Rectangle

GEO_DIR = Path(__file__).parent / "geo"
FONT_DIR = Path(__file__).parent / "brand" / "fonts"
CRS = "EPSG:4674"  # SIRGAS 2000

TINTA, TINTA_SUAVE, MATA, COBRE = "#1B2421", "#4E5B55", "#11483D", "#9C4A2F"
LINHA, SEM_DADO, FUNDO, BORDA = "#DCD6C8", "#ECE8DF", "#F7FAFB", "#B9B3A6"
# sequencial de uma matiz (barro/cobre), claro -> escuro
RAMPA = ["#F3E4DB", "#E2B49A", "#C97E5C", "#9C4A2F", "#5E2A19"]
FONTE_MALHA = "Base cartográfica: IBGE, Malha Municipal Digital (2025)"
SRC_TXT = "Sistema de referência: SIRGAS 2000 (EPSG:4674)"

try:
    for _f in ("InstrumentSans-Regular.ttf", "InstrumentSans-SemiBold.ttf"):
        fm.fontManager.addfont(str(FONT_DIR / _f))
    _FAMILIA = [fm.FontProperties(fname=str(FONT_DIR / "InstrumentSans-Regular.ttf")).get_name(), "DejaVu Sans"]
except Exception:  # noqa: BLE001
    _FAMILIA = ["DejaVu Sans"]


def _gpd():
    import geopandas as gpd  # import tardio: só carrega se o mapa for pedido
    return gpd


def chave(x) -> str:
    t = "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x)
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return " ".join(t.lower().replace("-", " ").split())


# ----------------------------------------------------------------------------
# bases cartográficas
# ----------------------------------------------------------------------------
@lru_cache(maxsize=32)
def municipios_uf(uf: str):
    gpd = _gpd()
    p = GEO_DIR / "malha_municipal_2025" / f"{uf.upper()}.geojson.gz"
    if not p.exists():
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        g = gpd.GeoDataFrame.from_features(json.load(f)["features"], crs=CRS)
    g["_k"] = g["nome"].map(chave)
    return g


@lru_cache(maxsize=1)
def contorno_ufs():
    gpd = _gpd()
    with gzip.open(GEO_DIR / "ufs_2025.geojson.gz", "rt", encoding="utf-8") as f:
        return gpd.GeoDataFrame.from_features(json.load(f)["features"], crs=CRS)


FONTE_BAIRROS_IBGE = "IBGE, Malha de Bairros (Censo 2022)"


@lru_cache(maxsize=32)
def bairros_uf(uf: str):
    """Divisões intramunicipais da UF: Malha de Bairros do Censo 2022 (IBGE) +
    malhas complementares de municípios que o IBGE não cobre (pasta
    geo/malha_bairros_extra — ex.: distritos de São Paulo, Regiões
    Administrativas do DF). Cada polígono traz a sua 'fonte'. None se não houver."""
    gpd = _gpd()
    partes = []
    for pasta, fonte in (("malha_bairros_2022", FONTE_BAIRROS_IBGE), ("malha_bairros_extra", None)):
        p = GEO_DIR / pasta / f"{uf.upper()}.geojson.gz"
        if p.exists():
            with gzip.open(p, "rt", encoding="utf-8") as f:
                g = gpd.GeoDataFrame.from_features(json.load(f)["features"], crs=CRS)
            if fonte:
                g["fonte"] = fonte
            partes.append(g)
    if not partes:
        return None
    g = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs=CRS)
    # se um município tiver malha complementar, ela substitui a do IBGE para ele
    extra_mun = set(g.loc[g["fonte"] != FONTE_BAIRROS_IBGE, "cd_mun"].astype(str))
    g = g[~((g["fonte"] == FONTE_BAIRROS_IBGE) & g["cd_mun"].astype(str).isin(extra_mun))]
    g["_k"] = g["nome"].map(chave)
    g["_km"] = g["municipio"].map(chave)
    return g.reset_index(drop=True)


def _codigo_municipio(nome, uf):
    """(cd_mun, uf) pelo nome do município (+UF, se houver); None se ambíguo/ausente."""
    k = chave(nome)
    achados = []
    for u in ([uf] if uf else todas_ufs()):
        g = municipios_uf(u)
        if g is not None:
            achados += [(r.cd_mun, r.uf) for r in g[g["_k"] == k].itertuples()]
    return achados[0] if len(achados) == 1 else None


# Cidades em que a divisão intramunicipal oficial não se chama "bairro"
TERMO_DIVISAO = {"São Paulo/SP": "distrito", "Brasília/DF": "região administrativa"}

# Nomes populares -> nome oficial da divisão (por código de município IBGE)
APELIDOS = {
    "5300108": {  # Brasília/DF — Regiões Administrativas
        "estrutural": "scia", "cidade estrutural": "scia", "vila estrutural": "scia",
        "sol nascente": "sol nascente/por do sol", "por do sol": "sol nascente/por do sol",
        "sudoeste": "sudoeste/octogonal", "octogonal": "sudoeste/octogonal",
        "brasilia": "plano piloto", "asa sul": "plano piloto", "asa norte": "plano piloto",
        "nucleo bandeirantes": "nucleo bandeirante", "itapoa": "itapoa",
    },
}


def casar_bairros_ibge(tab: pd.DataFrame):
    """Junta prevalência por bairro com a Malha de Bairros 2022 do IBGE, pelo
    município (+UF) e pelo nome do bairro (sem acento/maiúsculas; se não houver
    nome idêntico, aceita o mais parecido do mesmo município, com aviso).
    Devolve (gdf_com_dados, gdf_sem_dados, ufs, avisos)."""
    import difflib
    gpd = _gpd()
    avisos, partes, munis_ok, ufs = [], [], set(), set()
    sem_malha, nao_achados, aproximados = set(), [], []
    for _, r in tab.iterrows():
        uf = str(r.get("uf") or "").strip().upper()
        cod = _codigo_municipio(r["municipio"], uf)
        if cod is None:
            nao_achados.append(f"{r['bairro']} ({r['municipio']})")
            continue
        cd_mun, uf = cod
        b = bairros_uf(uf)
        bm = None if b is None else b[b["cd_mun"].astype(str) == str(cd_mun)]
        if bm is None or bm.empty:
            sem_malha.add(f"{r['municipio']}/{uf}")
            continue
        munis_ok.add(str(cd_mun))
        ufs.add(uf)
        k = chave(r["bairro"])
        k = APELIDOS.get(str(cd_mun), {}).get(k, k)
        hit = bm[bm["_k"] == k]
        if hit.empty:  # nome composto na malha ("A/B"): aceita qualquer uma das partes
            hit = bm[bm["_k"].map(lambda x: k in [p.strip() for p in x.split("/")])]
        if hit.empty:
            parecido = difflib.get_close_matches(k, list(bm["_k"]), n=1, cutoff=0.82)
            if not parecido:
                nao_achados.append(f"{r['bairro']} ({r['municipio']})")
                continue
            hit = bm[bm["_k"] == parecido[0]]
            aproximados.append(f"{r['bairro']} → {hit['nome'].iloc[0]}")
        linha = hit.iloc[[0]].copy()
        linha["nome"] = r["bairro"]
        for c in tab.columns:
            if c not in ("bairro", "municipio", "uf"):
                linha[c] = r[c]
        partes.append(linha)
    if sem_malha:
        avisos.append("Municípios sem divisão em bairros nas malhas disponíveis (IBGE, Censo 2022, e complementares): "
                      + ", ".join(sorted(sem_malha)) + ". Use o mapa por município ou envie os limites da prefeitura.")
    if aproximados:
        avisos.append("Bairros associados pelo nome mais parecido na malha de bairros — confira: "
                      + "; ".join(aproximados))
    if nao_achados:
        avisos.append("Bairros não encontrados nas malhas de bairros (ficaram fora do mapa): " + ", ".join(nao_achados))
    if not partes:
        return None, None, ufs, avisos
    com = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs=CRS)
    # se dois nomes da planilha caíram no mesmo bairro do IBGE, soma
    if com["cd_bairro"].duplicated().any():
        dups = com.loc[com["cd_bairro"].duplicated(keep=False), "nome"]
        avisos.append("Nomes diferentes da planilha caíram no mesmo bairro do IBGE e foram somados: "
                      + ", ".join(sorted(set(dups))))
        geo = com.drop_duplicates("cd_bairro").set_index("cd_bairro")["geometry"]
        agg = com.groupby("cd_bairro").agg(
            nome=("nome", " / ".join), fonte=("fonte", "first"),
            n_pacientes=("n_pacientes", "sum"), n_positivos=("n_positivos", "sum"),
            n_positivos_patogenico=("n_positivos_patogenico", "sum"))
        agg["prevalencia"] = (100 * agg.n_positivos / agg.n_pacientes).round(1)
        agg["prevalencia_patogenico"] = (100 * agg.n_positivos_patogenico / agg.n_pacientes).round(1)
        ic = [_wilson(k, n) for k, n in zip(agg.n_positivos, agg.n_pacientes)]
        agg["ic95_inf"], agg["ic95_sup"] = [a for a, _ in ic], [b for _, b in ic]
        com = gpd.GeoDataFrame(agg.join(geo).reset_index(), geometry="geometry", crs=CRS)
    todos = pd.concat([bairros_uf(u) for u in ufs], ignore_index=True)
    sem = todos[todos["cd_mun"].astype(str).isin(munis_ok) & ~todos["cd_bairro"].isin(com["cd_bairro"])]
    return com, gpd.GeoDataFrame(sem, crs=CRS), ufs, avisos


def _wilson(k, n, z=1.96):
    if not n:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(100 * max(0.0, c - h), 1), round(100 * min(1.0, c + h), 1))


def todas_ufs() -> list[str]:
    return sorted(p.name.split(".")[0] for p in (GEO_DIR / "malha_municipal_2025").glob("*.geojson.gz"))


def casar_municipios(tab: pd.DataFrame):
    """Junta a tabela de prevalência por município (colunas municipio, uf, ...)
    com a malha. Sem UF, procura o nome em todo o Brasil e só aceita se o nome
    for único. Devolve (gdf_com_dados, ufs_usadas, avisos)."""
    gpd = _gpd()
    avisos, partes, ufs = [], [], set()
    for _, r in tab.iterrows():
        k = chave(r["municipio"])
        uf = str(r.get("uf") or "").strip().upper()
        cand = []
        for u in ([uf] if uf else todas_ufs()):
            g = municipios_uf(u)
            if g is not None:
                cand.append(g[g["_k"] == k])
        cand = [c for c in cand if not c.empty]
        achados = pd.concat(cand) if cand else None
        if achados is None or achados.empty:
            avisos.append(f"Município não encontrado na malha do IBGE: {r['municipio']}" + (f"/{uf}" if uf else ""))
            continue
        if len(achados) > 1:
            avisos.append(f"'{r['municipio']}' existe em mais de um estado — preencha a coluna uf")
            continue
        linha = achados.iloc[[0]].copy()
        for c in tab.columns:
            if c not in ("municipio", "uf"):
                linha[c] = r[c]
        partes.append(linha)
        ufs.add(linha["uf"].iloc[0])
    if not partes:
        return None, ufs, avisos
    out = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs=CRS)
    return out, ufs, avisos


# ----------------------------------------------------------------------------
# limites de bairros enviados por quem usa
# ----------------------------------------------------------------------------
def ler_limites(arquivo_bytes: bytes, nome_arquivo: str):
    """Lê GeoJSON (.geojson/.json) ou shapefile compactado (.zip). Converte para
    SIRGAS 2000. Devolve (gdf, colunas_de_texto)."""
    gpd = _gpd()
    nome = nome_arquivo.lower()
    if nome.endswith(".zip"):
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(io.BytesIO(arquivo_bytes)) as z:
                z.extractall(tmp)
            shp = next(iter(sorted(Path(tmp).rglob("*.shp"))), None)
            if shp is None:
                raise ValueError("O .zip não tem um arquivo .shp.")
            g = gpd.read_file(shp)
    else:
        g = gpd.read_file(io.BytesIO(arquivo_bytes))
    if g.crs is None:
        g = g.set_crs(CRS)
    g = g.to_crs(CRS)
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    g = g[g.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    cols = [c for c in g.columns if c != "geometry" and not pd.api.types.is_numeric_dtype(g[c])]
    return g.reset_index(drop=True), cols


def coluna_nome_provavel(cols: list[str]) -> str | None:
    pref = ["nm_bairro", "bairro", "nome_bairro", "nome", "nm_bai", "name", "nm"]
    k = {c.lower(): c for c in cols}
    for p in pref:
        if p in k:
            return k[p]
    for c in cols:
        if "bairro" in c.lower() or "nome" in c.lower():
            return c
    return cols[0] if cols else None


def casar_bairros(tab: pd.DataFrame, limites, col_nome: str):
    """Junta prevalência por bairro com os limites enviados, pelo nome do bairro
    (sem diferenciar acento/maiúsculas). Devolve (gdf_com_dados, gdf_todos, avisos)."""
    gpd = _gpd()
    lim = limites.copy()
    lim["_k"] = lim[col_nome].map(chave)
    lim = lim.dissolve("_k", as_index=False, aggfunc="first")
    t = tab.copy()
    t["_k"] = t["bairro"].map(chave)
    # o mesmo nome de bairro em municípios diferentes não dá para separar só pelo
    # arquivo de limites: soma-se e avisa
    avisos = []
    dup = t["_k"].duplicated(keep=False)
    if dup.any():
        avisos.append("Bairros com o mesmo nome em municípios diferentes foram somados no mapa: "
                      + ", ".join(sorted(set(t.loc[dup, "bairro"]))))
        t = t.groupby("_k", as_index=False).agg(
            bairro=("bairro", "first"), n_pacientes=("n_pacientes", "sum"), n_positivos=("n_positivos", "sum"),
            n_positivos_patogenico=("n_positivos_patogenico", "sum"))
        t["prevalencia"] = (100 * t.n_positivos / t.n_pacientes).round(1)
        t["prevalencia_patogenico"] = (100 * t.n_positivos_patogenico / t.n_pacientes).round(1)
    m = lim.merge(t.drop(columns=[c for c in ("municipio", "uf") if c in t.columns]), on="_k", how="left")
    faltando = sorted(set(t["_k"]) - set(lim["_k"]))
    if faltando:
        nomes = t.set_index("_k").loc[faltando, "bairro"]
        avisos.append("Bairros da planilha que não estão no arquivo de limites: " + ", ".join(map(str, nomes)))
    # nome exibido: a grafia da planilha; se o bairro não tem dados, a do arquivo
    m["nome"] = m["bairro"].where(m["bairro"].notna(), m[col_nome].astype(str).str.title())
    com = gpd.GeoDataFrame(m[m["prevalencia"].notna()], crs=CRS)
    return (com if not com.empty else None), gpd.GeoDataFrame(m, crs=CRS), avisos


# ----------------------------------------------------------------------------
# classes
# ----------------------------------------------------------------------------
def classes(valores, modo: str = "auto"):
    """Limites das 5 classes. 'fixas': <10, 10–20, 20–40, 40–60, ≥60.
    'auto': 5 intervalos iguais de 5 em 5 pontos percentuais (no mínimo 5),
    começando no múltiplo de 5 abaixo do menor valor. Áreas com valores muito
    próximos ficam na mesma cor — não se exagera diferença pequena."""
    if modo == "fixas":
        return [0, 10, 20, 40, 60, 100.0001]
    v = [x for x in valores if pd.notna(x)]
    if not v:
        return [0, 20, 40, 60, 80, 100.0001]
    lo = 5 * math.floor(min(v) / 5)
    hi = 5 * math.ceil(max(v) / 5)
    if hi <= lo:
        hi = lo + 5
    if len(v) < 3:  # uma ou duas áreas: faixas automáticas não fazem sentido
        return [0, 10, 20, 40, 60, 100.0001]
    passo = max(5, 5 * math.ceil((hi - lo) / 25))
    if lo + 4 * passo >= 100:  # a última faixa não pode começar em 100% ou mais
        lo = max(0, 100 - 5 * passo)
    lims = [lo + i * passo for i in range(6)]
    lims[-1] = max(lims[-1], max(v)) + 0.0001
    return lims


def rotulos(lims):
    def f(x):
        return f"{x:g}".replace(".", ",")
    out = []
    for i in range(5):
        a, b = lims[i], lims[i + 1]
        if i == 0 and a == 0:
            out.append(f"< {f(b)}%")
        elif i == 4:
            out.append(f"≥ {f(a)}%")
        else:
            out.append(f"{f(a)}–{f(round(b, 1))}%")
    return out


def cor_de(v, lims):
    for i in range(5):
        if v < lims[i + 1]:
            return RAMPA[i]
    return RAMPA[-1]


# ----------------------------------------------------------------------------
# figura estática (padrão cartográfico)
# ----------------------------------------------------------------------------
def _br(v, d=1):
    return f"{v:.{d}f}".replace(".", ",")


def _aspecto(ax, lat):
    ax.set_aspect(1 / math.cos(math.radians(lat)))


def _grade(ax):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    larg = max(x1 - x0, y1 - y0)
    passo = min([0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5], key=lambda p: abs(larg / p - 5))
    casas = 2 if passo < 0.1 else (1 if passo < 1 else 0)
    ax.set_xticks(np.arange(math.ceil(x0 / passo) * passo, x1, passo))
    ax.set_yticks(np.arange(math.ceil(y0 / passo) * passo, y1, passo))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(
        lambda v, _: f"{abs(v):.{casas}f}°{'O' if v < 0 else 'L'}".replace(".", ",")))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(
        lambda v, _: f"{abs(v):.{casas}f}°{'S' if v < 0 else 'N'}".replace(".", ",")))
    ax.tick_params(labelsize=6.5, colors=TINTA_SUAVE, length=3, direction="in", top=True, right=True,
                   labeltop=True, labelright=True)
    plt.setp(ax.get_yticklabels(), rotation=90, va="center")
    ax.grid(True, color=LINHA, linewidth=0.4, linestyle=(0, (3, 3)))
    ax.set_axisbelow(False)
    ax.set_xlabel("")
    ax.set_ylabel("")
    for s in ax.spines.values():
        s.set_color(TINTA)
        s.set_linewidth(0.8)


def _norte(ax, x=0.93, y=0.86, tam=0.07):
    ax.annotate("", xy=(x, y + tam), xytext=(x, y), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>,head_width=0.45,head_length=0.9", color=TINTA, lw=1.4))
    ax.text(x, y + tam + 0.012, "N", transform=ax.transAxes, ha="center", va="bottom",
            fontsize=11, color=TINTA)


def _escala(ax, lat, x=0.05, y=0.05):
    km_por_grau = 111.32 * math.cos(math.radians(lat))
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    alvo = (x1 - x0) * km_por_grau / 4
    passo = min([0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200, 250, 500], key=lambda v: abs(v - alvo))
    seg = passo / 2 / km_por_grau
    bx, by, h = x0 + x * (x1 - x0), y0 + y * (y1 - y0), (y1 - y0) * 0.012
    for i in range(2):
        ax.add_patch(Rectangle((bx + i * seg, by), seg, h, facecolor=TINTA if i == 0 else "white",
                               edgecolor=TINTA, lw=0.7, zorder=10))
    for i, v in enumerate([0, passo / 2, passo]):
        ax.text(bx + i * seg, by + h * 1.8, f"{v:g}".replace(".", ","), ha="center", va="bottom",
                fontsize=6.5, color=TINTA, zorder=10,
                path_effects=[pe.withStroke(linewidth=2, foreground="white")])
    ax.text(bx + 2 * seg + seg * 0.15, by + h / 2, "km", va="center", fontsize=6.5, color=TINTA, zorder=10,
            path_effects=[pe.withStroke(linewidth=2, foreground="white")])


def _inset(fig, rect, ufs_destaque, ext):
    ax = fig.add_axes(rect)
    u = contorno_ufs()
    u.plot(ax=ax, color=SEM_DADO, edgecolor="white", linewidth=0.3)
    u[u["sigla"].isin(ufs_destaque)].plot(ax=ax, color=MATA, edgecolor="white", linewidth=0.3)
    minx, miny, maxx, maxy = ext
    pad = 0.6
    ax.add_patch(Rectangle((minx - pad, miny - pad), maxx - minx + 2 * pad, maxy - miny + 2 * pad,
                           fill=False, edgecolor=COBRE, lw=1.2))
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel("")
    ax.set_ylabel("")
    for s in ax.spines.values():
        s.set_color(TINTA)
        s.set_linewidth(0.6)
    ax.set_facecolor("white")
    ax.text(0.04, 0.96, "Localização", transform=ax.transAxes, fontsize=6.2, color=TINTA_SUAVE, va="top")
    _aspecto(ax, -15)


REGIOES = {
    "Norte": ["AC", "AM", "AP", "PA", "RO", "RR", "TO"],
    "Nordeste": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
    "Centro-Oeste": ["DF", "GO", "MS", "MT"],
    "Sudeste": ["ES", "MG", "RJ", "SP"],
    "Sul": ["PR", "RS", "SC"],
}
REGIAO_DA_UF = {u: r for r, us in REGIOES.items() for u in us}
NOME_UF = {"AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia", "CE": "Ceará",
           "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MG": "Minas Gerais",
           "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco",
           "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RO": "Rondônia",
           "RR": "Roraima", "RS": "Rio Grande do Sul", "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo",
           "TO": "Tocantins"}
RECORTES = ("brasil", "regiao", "estado", "municipio")


def _tam(n, nmax):
    return 40 + 520 * (n / max(nmax, 1))


def _ext_pad(bounds, frac=0.06, minimo=0.01):
    minx, miny, maxx, maxy = bounds
    pad = max(maxx - minx, maxy - miny) * frac + minimo
    return (minx - pad, miny - pad, maxx + pad, maxy + pad)


def figura_bytes(fig, formato="png", dpi=300) -> bytes:
    buf = io.BytesIO()
    kw = {"pil_kwargs": {"compression": "tiff_lzw"}} if formato == "tiff" else {}
    fig.savefig(buf, format=formato, dpi=dpi, facecolor="white", **kw)
    return buf.getvalue()


def _aneis(geom):
    from shapely.geometry import MultiPolygon
    if geom is None or geom.is_empty:
        return [], []
    polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    xs, ys = [], []
    for p in polys:
        if p.geom_type != "Polygon":
            continue
        x, y = p.exterior.xy
        xs += list(x) + [None]
        ys += list(y) + [None]
    return xs, ys


# ----------------------------------------------------------------------------
# figura estática (padrão cartográfico)
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# etiquetas sem sobreposição
# ----------------------------------------------------------------------------
def _sobrepoe(a, b, folga=1.5):
    return not (a[2] + folga <= b[0] or b[2] + folga <= a[0] or a[3] + folga <= b[1] or b[3] + folga <= a[1])


def _linha_cruza(p0, p1, caixa, passos=24):
    for k in range(1, passos):
        t = k / passos
        x, y = p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t
        if caixa[0] <= x <= caixa[2] and caixa[1] <= y <= caixa[3]:
            return True
    return False


def _segs_cruzam(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (o(a, b, c) * o(a, b, d) < 0) and (o(c, d, a) * o(c, d, b) < 0)


def _borda_caixa(p, caixa, gap=1.5):
    """Ponto da borda da caixa na direção de p (a linha de chamada para antes do texto)."""
    cx, cy = (caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2
    dx, dy = p[0] - cx, p[1] - cy
    hw, hh = (caixa[2] - caixa[0]) / 2 + gap, (caixa[3] - caixa[1]) / 2 + gap
    if dx == 0 and dy == 0:
        return cx, cy
    t = min(hw / abs(dx) if dx else 1e9, hh / abs(dy) if dy else 1e9)
    return cx + dx * t, cy + dy * t


def _posicionar_rotulos(fig, ax, itens, raio_px=None, pontos=False, fonte=5.6):
    """Coloca as etiquetas sem sobreposição, em três níveis:
    1) dentro da área (ou ao lado do círculo), deslocando um pouco se preciso;
    2) fora, num espaço livre próximo, com linha de chamada (para fora do aglomerado);
    3) se nada couber, um número na área e o nome numa lista ao lado do mapa.
    itens: lista de dict(nome, valor, x, y, geom, prioridade). Devolve cópias com
    'modo' ('dentro' | 'chamada' | 'numero'), 'texto', 'lx', 'ly' (dados), 'linha' e 'num'."""
    from shapely.geometry import Point
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    T = ax.transData
    inv = T.inverted()
    axb = ax.get_window_extent(rend)
    lim = (axb.x0 + 3, axb.y0 + 3, axb.x1 - 3, axb.y1 - 3)
    W, H = axb.width, axb.height
    # obstáculos fixos: seta do norte (alto à direita) e barra de escala (baixo à esquerda)
    fixos = [(axb.x0 + 0.885 * W, axb.y0 + 0.83 * H, axb.x1, axb.y1),
             (axb.x0, axb.y0, axb.x0 + 0.36 * W, axb.y0 + 0.13 * H)]
    caixas = []      # etiquetas já colocadas
    linhas = []      # linhas de chamada já desenhadas
    anc = {i: tuple(T.transform((it["x"], it["y"]))) for i, it in enumerate(itens)}
    raio = raio_px or {i: 4.0 for i in anc}
    obst_anc = {i: (x - raio[i], y - raio[i], x + raio[i], y + raio[i]) for i, (x, y) in anc.items()}
    cx0 = sum(x for x, _ in anc.values()) / max(len(anc), 1)
    cy0 = sum(y for _, y in anc.values()) / max(len(anc), 1)

    def medida(txt):
        t = ax.text(0, 0, txt, fontsize=fonte, linespacing=1.1, ha="center", va="center")
        bb = t.get_window_extent(rend)
        t.remove()
        return bb.width + 3, bb.height + 2

    def livre(caixa, i, linha_de=None):
        if caixa[0] < lim[0] or caixa[1] < lim[1] or caixa[2] > lim[2] or caixa[3] > lim[3]:
            return False
        if any(_sobrepoe(caixa, o) for o in fixos + caixas):
            return False
        # não cobre o ponto/círculo de outra área (no modo áreas, nem o próprio fica de fora: a
        # etiqueta centrada nele é o caso normal, então i == -1 libera só esse)
        if any(_sobrepoe(caixa, o, 0.5) for j, o in obst_anc.items() if j != i):
            return False
        if any(_linha_cruza(a, b, caixa) for a, b in linhas):
            return False
        if linha_de is not None:
            p1 = _borda_caixa(linha_de, caixa)
            if any(_linha_cruza(linha_de, p1, o) for o in caixas):
                return False
            if any(_segs_cruzam(linha_de, p1, a, b) for a, b in linhas):
                return False
            if any(_linha_cruza(linha_de, p1, o) for j, o in obst_anc.items() if j != i):
                return False
        return True

    ordem = sorted(range(len(itens)), key=lambda i: -itens[i]["prioridade"])
    res = [dict(it) for it in itens]
    numerados = []
    for i in ordem:
        it = res[i]
        ax_, ay_ = anc[i]
        txt = f"{it['nome']} ({_br(it['valor'])}%)" if pontos else f"{it['nome']}\n{_br(it['valor'])}%"
        w, h = medida(txt)
        it["texto"] = txt
        feito = False
        # 1) dentro da área / ao lado do círculo
        if pontos:
            r = raio[i]
            cands = [(ax_ + r + 3 + w / 2, ay_), (ax_ - r - 3 - w / 2, ay_),
                     (ax_, ay_ + r + 2 + h / 2), (ax_, ay_ - r - 2 - h / 2)]
        else:
            cands = [(ax_, ay_)] + [(ax_ + dx * w, ay_ + dy * h) for dx, dy in
                                    [(0, .55), (0, -.55), (.3, 0), (-.3, 0), (.3, .5), (-.3, .5), (.3, -.5), (-.3, -.5)]]
        for ccx, ccy in cands:
            caixa = (ccx - w / 2, ccy - h / 2, ccx + w / 2, ccy + h / 2)
            if not pontos and (ccx, ccy) != (ax_, ay_):
                gx, gy = inv.transform((ccx, ccy))
                if it.get("geom") is None or not it["geom"].contains(Point(gx, gy)):
                    continue
            if livre(caixa, i if pontos else i):
                it.update(modo="dentro", caixa=caixa)
                feito = True
                break
        # 2) fora, com linha de chamada, preferindo a direção "para fora" do aglomerado
        if not feito:
            ox, oy = ax_ - cx0, ay_ - cy0
            ang_fora = math.atan2(oy, ox) if (abs(ox) + abs(oy)) > 1 else math.pi / 2
            base = max(h * 1.1, 12) + raio[i]
            d_max = 0.2 * max(W, H) + raio[i]   # linha de chamada longa demais confunde: vira número
            angs = sorted((k * math.pi / 8 for k in range(16)),
                          key=lambda a: abs(math.atan2(math.sin(a - ang_fora), math.cos(a - ang_fora))))
            for mult in (1.0, 1.6, 2.3, 3.2, 4.3, 5.6, 7.2):
                if base * mult > d_max:
                    break
                for a in angs:
                    d = base * mult
                    ccx = ax_ + math.cos(a) * (d + w / 2 * abs(math.cos(a)))
                    ccy = ay_ + math.sin(a) * (d + h / 2 * abs(math.sin(a)))
                    caixa = (ccx - w / 2, ccy - h / 2, ccx + w / 2, ccy + h / 2)
                    if livre(caixa, i, linha_de=(ax_, ay_)):
                        it.update(modo="chamada", caixa=caixa)
                        feito = True
                        break
                if feito:
                    break
        if feito:
            caixas.append(it["caixa"])
            c = it["caixa"]
            if it["modo"] == "chamada":
                p1 = _borda_caixa((ax_, ay_), c)
                linhas.append(((ax_, ay_), p1))
                it["linha"] = (tuple(inv.transform((ax_, ay_))), tuple(inv.transform(p1)))
            it["lx"], it["ly"] = inv.transform(((c[0] + c[2]) / 2, (c[1] + c[3]) / 2))
        else:
            it["modo"] = "numero"
            numerados.append(i)
    # 3) numeração em ordem de leitura (de cima para baixo, da esquerda para a direita); o
    #    número também procura lugar livre (se não couber sobre a área, sai com linha curta)
    lado = fonte * fig.dpi / 72 * 1.25 + 2
    for n, i in enumerate(sorted(numerados, key=lambda i: (-round(anc[i][1] / 20), anc[i][0])), 1):
        it = res[i]
        it["num"] = n
        ax_, ay_ = anc[i]
        ox, oy = ax_ - cx0, ay_ - cy0
        ang_fora = math.atan2(oy, ox) if (abs(ox) + abs(oy)) > 1 else math.pi / 2
        angs = sorted((k * math.pi / 8 for k in range(16)),
                      key=lambda a: abs(math.atan2(math.sin(a - ang_fora), math.cos(a - ang_fora))))
        achado = None
        for d in (0, 1.3, 2.0, 2.8, 3.8, 5.0):
            for a in ([0] if d == 0 else angs):
                ccx = ax_ + math.cos(a) * (d * lado + (raio[i] if d else 0))
                ccy = ay_ + math.sin(a) * (d * lado + (raio[i] if d else 0))
                caixa = (ccx - lado / 2, ccy - lado / 2, ccx + lado / 2, ccy + lado / 2)
                if livre(caixa, i, linha_de=None if d == 0 else (ax_, ay_)):
                    achado = (caixa, d)
                    break
            if achado:
                break
        if achado is None:
            achado = ((ax_ - lado / 2, ay_ - lado / 2, ax_ + lado / 2, ay_ + lado / 2), 0)
        c, d = achado
        caixas.append(c)
        ncx, ncy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
        it["nx"], it["ny"] = inv.transform((ncx, ncy))
        if d:
            p1 = _borda_caixa((ax_, ay_), c, gap=0.5)
            linhas.append(((ax_, ay_), p1))
            it["linha"] = (tuple(inv.transform((ax_, ay_))), tuple(inv.transform(p1)))
    # 4) no modo círculos a lateral está ocupada pelas legendas: a lista de numerados vai
    #    para um canto livre dentro do mapa (alto à esquerda ou baixo à direita)
    info = {"lista_ax": None}
    if numerados and pontos:
        linhas_txt = sum(1 for _ in numerados) + 1
        larg = max(medida(f"{res[i]['nome']} ({_br(res[i]['valor'])}%)")[0] for i in numerados) + 14
        alt = linhas_txt * fonte * fig.dpi / 72 * 1.45 + 8
        cantos = {"sup_esq": (axb.x0 + 6, axb.y1 - 6 - alt, axb.x0 + 6 + larg, axb.y1 - 6),
                  "inf_dir": (axb.x1 - 6 - larg, axb.y0 + 6, axb.x1 - 6, axb.y0 + 6 + alt),
                  "inf_esq": (axb.x0 + 6, axb.y0 + 0.14 * H, axb.x0 + 6 + larg, axb.y0 + 0.14 * H + alt)}

        def custo(c):
            return (sum(_sobrepoe(c, o, 0) for o in caixas) * 3
                    + sum(_sobrepoe(c, o, 0) for o in obst_anc.values()))
        nome_c, c = min(cantos.items(), key=lambda kv: custo(kv[1]))
        info["lista_ax"] = ((c[0] - axb.x0) / W, (c[3] - axb.y0) / H)
    return res, info


def _desenhar_rotulos(ax, fig, res, info=None, fonte=5.6, topo=0.335):
    halo = [pe.withStroke(linewidth=2.2, foreground="white")]
    lista = []
    for it in res:
        if it["modo"] in ("dentro", "chamada"):
            if it["modo"] == "chamada":
                (x0, y0), (x1, y1) = it["linha"]
                ax.plot([x0, x1], [y0, y1], color=TINTA, lw=0.45, zorder=6, solid_capstyle="round")
                ax.plot([x0], [y0], "o", ms=1.9, color=TINTA, zorder=7)
            ax.text(it["lx"], it["ly"], it["texto"], ha="center", va="center", fontsize=fonte, zorder=8,
                    linespacing=1.1, color=TINTA, path_effects=halo)
        elif it.get("num"):
            if it.get("linha"):
                (x0, y0), (x1, y1) = it["linha"]
                ax.plot([x0, x1], [y0, y1], color=TINTA, lw=0.45, zorder=6, solid_capstyle="round")
                ax.plot([x0], [y0], "o", ms=1.9, color=TINTA, zorder=7)
            ax.text(it.get("nx", it["x"]), it.get("ny", it["y"]), str(it["num"]), ha="center", va="center", fontsize=fonte - 0.6, zorder=8,
                    color=TINTA, bbox=dict(boxstyle="circle,pad=0.2", facecolor="white", edgecolor=TINTA, lw=0.45))
            lista.append((it["num"], f"{it['num']}  {it['nome']} ({_br(it['valor'])}%)"))
    if lista and info and info.get("lista_ax"):
        lista.sort()
        x, y = info["lista_ax"]
        ax.text(x, y, "Áreas numeradas\n" + "\n".join(t for _, t in lista), transform=ax.transAxes,
                ha="left", va="top", fontsize=fonte, color=TINTA, linespacing=1.35, zorder=9,
                bbox=dict(boxstyle="round,pad=0.5", facecolor="white", edgecolor=LINHA, lw=0.6, alpha=0.95))
    elif lista:
        lista.sort()
        linhas = [t for _, t in lista]
        ncol = 1 if len(linhas) <= 12 else 2
        por = math.ceil(len(linhas) / ncol)
        fig.text(0.765, topo, "Áreas numeradas", ha="left", va="top", fontsize=6.4, color=TINTA)
        for c in range(ncol):
            fig.text(0.765 + c * 0.115, topo - 0.025, "\n".join(linhas[c * por:(c + 1) * por]), ha="left", va="top",
                     fontsize=5.6 if ncol == 1 else 4.9, color=TINTA, linespacing=1.35)


def figura_estatica(cena: dict):
    """cena: dict montado por preparar_mapa (áreas, camadas de fundo, extensão,
    classes, estilo, títulos)."""
    areas, valor_col, lims = cena["areas"], cena["valor_col"], cena["lims"]
    ext, pontos, rotulos_on = cena["ext"], cena["pontos"], cena["rotulos"]
    with plt.rc_context({"font.family": _FAMILIA, "font.size": 8.5}):
        cmap = ListedColormap(RAMPA)
        norm = BoundaryNorm(lims, cmap.N)
        fig = plt.figure(figsize=(7.6, 6.0), dpi=150, facecolor="white")
        ax = fig.add_axes([0.075, 0.085, 0.66, 0.83])
        ax.set_facecolor(FUNDO)
        lw_fundo = 0.25 if cena["recorte"] in ("brasil", "regiao") else 0.6
        for camada in cena["fundo"]:
            camada.plot(ax=ax, color="white", edgecolor=BORDA, linewidth=lw_fundo)
        if cena.get("ufs_contorno") is not None:
            cena["ufs_contorno"].boundary.plot(ax=ax, color="#8F8A80", linewidth=0.6)
        sem = cena.get("sem_dados")
        if sem is not None and not sem.empty:
            sem.plot(ax=ax, color=SEM_DADO, edgecolor="white", linewidth=0.5)
        if pontos:
            pts = areas.geometry.representative_point()
            nmax = areas["n_pacientes"].max()
            ax.scatter(pts.x, pts.y, s=[_tam(n, nmax) for n in areas["n_pacientes"]],
                       c=areas[valor_col], cmap=cmap, norm=norm, edgecolor=TINTA, linewidth=0.6, zorder=5)
        else:
            # áreas pequenas demais para a escala ganham um contorno fino escuro, para não sumirem
            borda = TINTA if cena["recorte"] in ("brasil", "regiao") else "white"
            areas.plot(ax=ax, column=valor_col, cmap=cmap, norm=norm, edgecolor=borda,
                       linewidth=0.35 if borda == TINTA else 0.9, zorder=4)
        ax.set_xlim(ext[0], ext[2])
        ax.set_ylim(ext[1], ext[3])
        lat_c = (ext[1] + ext[3]) / 2
        _aspecto(ax, lat_c)
        _grade(ax)
        _norte(ax)
        _escala(ax, lat_c)
        h = [Patch(facecolor=c, edgecolor=TINTA_SUAVE, lw=0.4, label=r) for c, r in zip(RAMPA, rotulos(lims))]
        if sem is not None and not sem.empty:
            h.append(Patch(facecolor=SEM_DADO, edgecolor=TINTA_SUAVE, lw=0.4, label=f"{cena['rotulo_area']} sem dados"))
        leg = ax.legend(handles=h, title="Prevalência", loc="upper left", bbox_to_anchor=(1.06, 0.62),
                        fontsize=6.8, title_fontsize=7.2, frameon=True, framealpha=0.95, edgecolor=LINHA,
                        borderpad=0.7, labelspacing=0.45, handlelength=1.4)
        leg._legend_box.align = "left"
        if pontos:
            from matplotlib.lines import Line2D
            nmax = areas["n_pacientes"].max()
            refs = sorted({max(1, int(round(nmax * f))) for f in (0.25, 0.5, 1.0)})
            ax.add_artist(leg)
            hs = [Line2D([], [], marker="o", ls="", markerfacecolor="white", markeredgecolor=TINTA,
                         markersize=math.sqrt(_tam(v, nmax)), label=str(v)) for v in refs]
            ax.legend(handles=hs, title="Pacientes (n)", loc="upper left", bbox_to_anchor=(1.06, 0.25),
                      fontsize=6.8, title_fontsize=7.2, frameon=True, framealpha=0.95, edgecolor=LINHA,
                      borderpad=0.9, labelspacing=1.3, handletextpad=1.2)
        if cena["recorte"] != "brasil":
            _inset(fig, [0.765, 0.60, 0.2, 0.3], set(cena["ufs_destaque"]), ext)
        cena["rotulos_pos"] = None
        if rotulos_on and len(areas):
            pts = areas.geometry.representative_point()
            itens = [dict(nome=nm, valor=v, x=p.x, y=p.y, geom=g, prioridade=(n if pontos else g.area))
                     for nm, v, p, g, n in zip(areas["nome"], areas[valor_col], pts, areas.geometry,
                                               areas["n_pacientes"])]
            raio = None
            if pontos:
                nmax = areas["n_pacientes"].max()
                esc = fig.dpi / 72
                raio = {i: math.sqrt(_tam(n, nmax)) / 2 * esc for i, n in enumerate(areas["n_pacientes"])}
            res, info = _posicionar_rotulos(fig, ax, itens, raio, pontos=pontos)
            _desenhar_rotulos(ax, fig, res, info)
            cena["rotulos_pos"] = res
        fig.suptitle(cena["titulo"], x=0.075, ha="left", y=0.985, fontsize=10.5, color=MATA)
        rod = f"{SRC_TXT} · {FONTE_MALHA}" + (f" · {cena['nota']}" if cena.get("nota") else "")
        fig.text(0.5, 0.012, rod, ha="center", va="bottom", fontsize=6.0, color=TINTA_SUAVE)
    return fig


# ----------------------------------------------------------------------------
# versão interativa (plotly, SVG puro)
# ----------------------------------------------------------------------------
def _camada_unica(fig, gdf, cor, borda, larg):
    """Desenha muitos polígonos numa só trace (rápido mesmo com milhares)."""
    import plotly.graph_objects as go
    xs, ys = [], []
    for g in gdf.geometry:
        x, y = _aneis(g)
        xs += x
        ys += y
    if xs:
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", fill="toself", fillcolor=cor,
                                 line=dict(color=borda, width=larg), hoverinfo="skip", showlegend=False))


def _rotulos_interativos(fig, pos, pontos):
    """Etiquetas do mapa interativo nas mesmas posições calculadas para a figura estática
    (sem sobreposição): texto, linhas de chamada e números com a lista no canto."""
    import plotly.graph_objects as go
    lx, ly = [], []
    dots_x, dots_y = [], []
    lista = []
    for it in pos:
        if it.get("linha"):
            (x0, y0), (x1, y1) = it["linha"]
            lx += [x0, x1, None]
            ly += [y0, y1, None]
            dots_x.append(x0)
            dots_y.append(y0)
    if lx:
        fig.add_trace(go.Scatter(x=lx, y=ly, mode="lines", line=dict(color=TINTA, width=0.8),
                                 hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(x=dots_x, y=dots_y, mode="markers", marker=dict(size=4, color=TINTA),
                                 hoverinfo="skip", showlegend=False))
    for it in pos:
        if it["modo"] in ("dentro", "chamada"):
            txt = it["texto"].replace("\n", "<br>")
            fig.add_annotation(x=it["lx"], y=it["ly"], text=txt, showarrow=False, font=dict(size=9, color=TINTA),
                               bgcolor="rgba(255,255,255,.6)", borderpad=0)
        elif it.get("num"):
            fig.add_annotation(x=it.get("nx", it["x"]), y=it.get("ny", it["y"]), text=f"<b>{it['num']}</b>",
                               showarrow=False, font=dict(size=9, color=TINTA), bgcolor="white",
                               bordercolor=TINTA, borderwidth=0.8, borderpad=2)
            lista.append((it["num"], f"{it['num']}  {it['nome']} ({_br(it['valor'])}%)"))
    if lista:
        lista.sort()
        fig.add_annotation(x=0.01, y=0.99, xref="paper", yref="paper", xanchor="left", yanchor="top", align="left",
                           showarrow=False, text="<b>Áreas numeradas</b><br>" + "<br>".join(t for _, t in lista),
                           font=dict(size=10, color=TINTA), bgcolor="rgba(255,255,255,.92)", bordercolor=LINHA,
                           borderwidth=1, borderpad=6)


def figura_interativa(cena: dict, altura=620):
    import plotly.graph_objects as go
    areas, valor_col, lims = cena["areas"], cena["valor_col"], cena["lims"]
    ext, pontos, rotulos_on, rot_area = cena["ext"], cena["pontos"], cena["rotulos"], cena["rotulo_area"]
    fig = go.Figure()
    for camada in cena["fundo"]:
        _camada_unica(fig, camada, "#FFFFFF", BORDA, 0.5 if cena["recorte"] in ("brasil", "regiao") else 0.8)
    if cena.get("ufs_contorno") is not None:
        for g in cena["ufs_contorno"].geometry:
            x, y = _aneis(g)
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color="#8F8A80", width=1),
                                     hoverinfo="skip", showlegend=False))
    sem = cena.get("sem_dados")
    pos = cena.get("rotulos_pos") if rotulos_on else None
    if sem is not None and not sem.empty:
        _camada_unica(fig, sem, SEM_DADO, "white", 0.8)

    def _ic(r):
        if valor_col == "prevalencia" and pd.notna(r.get("ic95_inf")) and pd.notna(r.get("ic95_sup")):
            return f" (IC 95% {_br(r['ic95_inf'])}–{_br(r['ic95_sup'])}%)"
        return ""

    def _hover(r):
        return (f"<b>{r['nome']}</b><br>{rot_area}<br>Pacientes: {int(r['n_pacientes'])}"
                f"<br>Prevalência: <b>{_br(r[valor_col])}%</b>{_ic(r)}<extra></extra>")

    if pontos:
        pts = areas.geometry.representative_point()
        nmax = areas["n_pacientes"].max()
        fig.add_trace(go.Scatter(
            x=pts.x, y=pts.y, mode="markers+text" if (rotulos_on and not pos) else "markers", showlegend=False,
            text=[f"{n} ({_br(v)}%)" for n, v in zip(areas["nome"], areas[valor_col])], textposition="middle right",
            textfont=dict(size=10, color=TINTA),
            marker=dict(size=[math.sqrt(_tam(n, nmax)) * 1.35 for n in areas["n_pacientes"]],
                        color=[cor_de(v, lims) for v in areas[valor_col]], line=dict(color=TINTA, width=0.8)),
            hovertemplate=[_hover(r) for _, r in areas.iterrows()]))
    else:
        borda = TINTA if cena["recorte"] in ("brasil", "regiao") else "white"
        for _, r in areas.iterrows():
            xs, ys = _aneis(r.geometry)
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", fill="toself", fillcolor=cor_de(r[valor_col], lims),
                                     line=dict(color=borda, width=0.6 if borda == TINTA else 1.3), hoveron="fills",
                                     showlegend=False, name="", hovertemplate=_hover(r)))
        # ponto invisível no centro de cada área: facilita o hover em áreas pequenas
        pts = areas.geometry.representative_point()
        fig.add_trace(go.Scatter(
            x=pts.x, y=pts.y, mode="markers+text" if (rotulos_on and not pos) else "markers", showlegend=False,
            marker=dict(size=10, color="rgba(0,0,0,0)"),
            text=[f"{n}<br>{_br(v)}%" for n, v in zip(areas["nome"], areas[valor_col])],
            textfont=dict(size=10, color=TINTA, shadow="1px 1px 2px white, -1px -1px 2px white, 1px -1px 2px white, -1px 1px 2px white"),
            hovertemplate=[_hover(r) for _, r in areas.iterrows()]))
    if pos:
        _rotulos_interativos(fig, pos, pontos)
    for c, r in zip(RAMPA, rotulos(lims)):
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=r,
                                 marker=dict(symbol="square", size=12, color=c, line=dict(color=TINTA_SUAVE, width=0.5))))
    lat_c = (ext[1] + ext[3]) / 2
    casas = ".0f" if (ext[2] - ext[0]) > 8 else ".2f"
    eixo = dict(showgrid=True, gridcolor="#E6E1D6", zeroline=False, ticks="inside", mirror=True, showline=True,
                linecolor=TINTA, tickformat=casas, ticksuffix="°", tickfont=dict(size=10, color=TINTA_SUAVE))
    fig.update_xaxes(range=[ext[0], ext[2]], **eixo)
    fig.update_yaxes(range=[ext[1], ext[3]], scaleanchor="x", scaleratio=1 / math.cos(math.radians(lat_c)), **eixo)
    fig.update_layout(
        height=altura, margin=dict(l=50, r=20, t=10, b=40), plot_bgcolor=FUNDO, paper_bgcolor="#FBF9F4",
        font=dict(family="Instrument Sans, sans-serif", color=TINTA), dragmode="pan",
        legend=dict(title=dict(text="<b>Prevalência</b>"), bgcolor="rgba(255,255,255,.92)", bordercolor=LINHA,
                    borderwidth=1, x=1.0, xanchor="right", y=0.02, yanchor="bottom"),
        hoverlabel=dict(bgcolor="white", bordercolor=BORDA),
    )
    fig.add_annotation(x=0.97, y=0.97, xref="paper", yref="paper", text="<b>N</b><br>↑", showarrow=False,
                       font=dict(size=16, color=TINTA))
    return fig


# ----------------------------------------------------------------------------
# opções de recorte a partir dos dados
# ----------------------------------------------------------------------------
def opcoes_recorte(metrics: dict, nivel: str) -> dict:
    """Regiões, UFs e municípios que têm pacientes (no nível pedido), em ordem
    de nº de pacientes. Devolve {'regiao': [...], 'estado': [...], 'municipio': [...]}."""
    tab = metrics.get("territorio_municipio" if nivel == "municipio" else "territorio_bairro")
    if tab is None or tab.empty:
        return {"regiao": [], "estado": [], "municipio": []}
    t = tab.assign(_uf=tab["uf"].astype(str).str.upper())
    t = t[t["_uf"].isin(NOME_UF)]
    por_uf = t.groupby("_uf")["n_pacientes"].sum().sort_values(ascending=False)
    por_reg = t.assign(_r=t["_uf"].map(REGIAO_DA_UF)).groupby("_r")["n_pacientes"].sum().sort_values(ascending=False)
    por_mun = t.assign(_m=t["municipio"].astype(str) + "/" + t["_uf"]).groupby("_m")["n_pacientes"].sum() \
        .sort_values(ascending=False)
    return {"regiao": list(por_reg.index), "estado": list(por_uf.index), "municipio": list(por_mun.index)}


def municipios_com_bairro(metrics: dict) -> list[str]:
    return opcoes_recorte(metrics, "bairro")["municipio"]


def _ufs_do_recorte(recorte, valor):
    if recorte == "regiao":
        return set(REGIOES.get(valor, []))
    if recorte == "estado":
        return {str(valor).upper()}
    if recorte == "municipio":
        return {str(valor).partition("/")[2].upper()}
    return set(NOME_UF)


# ----------------------------------------------------------------------------
# ponto de entrada usado pelo app
# ----------------------------------------------------------------------------
def preparar_mapa(metrics: dict, nivel: str, indicador: str, modo_classes: str = "auto",
                  limites=None, col_nome=None, mostrar_rotulos=None, municipio_foco: str | None = None,
                  recorte: str | None = None, recorte_valor: str | None = None, estilo: str = "areas"):
    """Monta o mapa. nivel: 'municipio' | 'bairro'. recorte: 'brasil' | 'regiao'
    | 'estado' | 'municipio' (recorte_valor = nome da região, sigla da UF ou
    'Município/UF'). estilo: 'areas' (áreas coloridas) | 'pontos' (círculos
    proporcionais). Devolve dict com 'ok', 'avisos', 'fig_estatica',
    'fig_interativa', 'titulo' — ou ok=False e 'erro'."""
    gpd = _gpd()
    valor_col = "prevalencia" if indicador == "todos" else "prevalencia_patogenico"
    qual = "enteroparasitos" if indicador == "todos" else "enteroparasitos patogênicos"
    avisos: list[str] = []
    if recorte is None:  # compatibilidade: mapa de bairros de uma cidade
        recorte, recorte_valor = ("municipio", municipio_foco) if municipio_foco else ("brasil", None)
    ufs_rec = _ufs_do_recorte(recorte, recorte_valor)

    tab_m = metrics.get("territorio_municipio")
    if tab_m is None or tab_m.empty:
        return {"ok": False, "erro": "Nenhum paciente com município preenchido — não há o que mapear."}

    # ---- unidades com dados (municípios ou bairros) dentro do recorte ----
    nota = ""
    if nivel == "municipio":
        t = tab_m[tab_m["uf"].astype(str).str.upper().isin(ufs_rec) | (recorte == "brasil")]
        if recorte == "municipio":
            nome_f = str(recorte_valor).partition("/")[0]
            t = t[t["municipio"].map(chave) == chave(nome_f)]
        if t.empty:
            return {"ok": False, "erro": "Nenhum paciente com município neste recorte."}
        areas, _, av = casar_municipios(t)
        avisos += av
        if areas is None:
            return {"ok": False, "erro": "Nenhum município do recorte foi encontrado na malha do IBGE.",
                    "avisos": avisos}
        sem, rot_area, unidade = None, "Município", "município"
    else:
        tab_b = metrics.get("territorio_bairro")
        if tab_b is None or tab_b.empty:
            return {"ok": False, "erro": "Nenhum paciente com bairro preenchido.", "avisos": avisos}
        tb = tab_b[tab_b["uf"].astype(str).str.upper().isin(ufs_rec) | (recorte == "brasil")]
        if recorte == "municipio":
            nome_f = str(recorte_valor).partition("/")[0]
            tb = tb[tb["municipio"].map(chave) == chave(nome_f)]
        if tb.empty:
            return {"ok": False, "erro": "Nenhum paciente com bairro neste recorte.", "avisos": avisos}
        if limites is None:
            areas, sem, _, av = casar_bairros_ibge(tb)
            avisos += av
            if areas is None:
                return {"ok": False, "erro": "Nenhum bairro do recorte foi encontrado nas malhas de bairros. "
                                             "Use o mapa por município ou envie os limites da prefeitura.",
                        "avisos": avisos}
            fontes = sorted(set(areas["fonte"].dropna())) if "fonte" in areas.columns else [FONTE_BAIRROS_IBGE]
            nota = "Limites intramunicipais: " + "; ".join(fontes)
        else:
            areas, todos, av = casar_bairros(tb, limites, col_nome)
            avisos += av
            if areas is None:
                return {"ok": False, "erro": "Nenhum bairro da planilha foi encontrado no arquivo de limites "
                                             "(confira a coluna com o nome do bairro).", "avisos": avisos}
            sem = todos[todos["prevalencia"].isna()]
            nota = "Limites intramunicipais: arquivo enviado pelo usuário"
        rot_area = "Bairro"
        unidade = TERMO_DIVISAO.get(recorte_valor, "bairro") if recorte == "municipio" else "bairro"

    # ---- extensão e camadas de fundo, conforme o recorte ----
    ufs_gdf = contorno_ufs()
    ufs_dados = set(areas["uf"].astype(str).str.upper()) if "uf" in areas.columns else set()
    fundo, ufs_contorno = [], None
    if recorte == "brasil":
        ext = _ext_pad(ufs_gdf.total_bounds, 0.03)
        fundo = [ufs_gdf]
        local = "Brasil"
    elif recorte == "regiao":
        reg = ufs_gdf[ufs_gdf["sigla"].isin(ufs_rec)]
        ext = _ext_pad(reg.total_bounds, 0.05)
        fundo = [ufs_gdf]
        ufs_contorno = reg
        local = f"Região {recorte_valor}"
    elif recorte == "estado":
        uf = next(iter(ufs_rec))
        mun_uf = municipios_uf(uf)
        ext = _ext_pad(mun_uf.total_bounds, 0.05)
        fundo = [ufs_gdf, mun_uf]
        ufs_contorno = ufs_gdf[ufs_gdf["sigla"] == uf]
        local = NOME_UF.get(uf, uf)
    else:  # municipio
        nome_f, _, uf = str(recorte_valor).partition("/")
        mun_uf = municipios_uf(uf)
        alvo = mun_uf[mun_uf["_k"] == chave(nome_f)] if mun_uf is not None else None
        base_b = alvo.total_bounds if alvo is not None and not alvo.empty else areas.total_bounds
        ext = _ext_pad(base_b, 0.08)
        fundo = [ufs_gdf] + ([mun_uf] if mun_uf is not None else [])
        local = str(recorte_valor)
    if sem is not None and not sem.empty:
        sem = sem.cx[ext[0]:ext[2], ext[1]:ext[3]]
    pontos = (estilo == "pontos")
    lims = classes(areas[valor_col], modo_classes)
    if mostrar_rotulos is None:
        mostrar_rotulos = len(areas) <= 15
    pequenos = int((areas["n_pacientes"] < 10).sum())
    if pequenos:
        avisos.append(f"{pequenos} área(s) com menos de 10 pacientes: prevalência pouco precisa — "
                      "interprete com cuidado (veja o IC 95% na tabela).")
    if not pontos and nivel == "municipio" and recorte in ("brasil", "regiao"):
        avisos.append("Em escala nacional/regional, municípios pequenos ficam quase invisíveis como áreas — "
                      "se for o caso, use 'Círculos proporcionais'.")
    titulo = f"Prevalência de {qual} por {unidade} de residência — {local}"
    cena = dict(areas=areas, valor_col=valor_col, lims=lims, ext=ext, pontos=pontos, rotulos=mostrar_rotulos,
                fundo=fundo, ufs_contorno=ufs_contorno, sem_dados=sem, rotulo_area=rot_area, recorte=recorte,
                ufs_destaque=ufs_dados or ufs_rec, titulo=titulo, nota=nota)
    return {"ok": True, "avisos": avisos, "fig_estatica": figura_estatica(cena),
            "fig_interativa": figura_interativa(cena), "titulo": titulo}
