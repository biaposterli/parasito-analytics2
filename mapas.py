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


@lru_cache(maxsize=32)
def bairros_uf(uf: str):
    """Malha de Bairros do Censo 2022 (IBGE) da UF, ou None se a UF não tiver."""
    gpd = _gpd()
    p = GEO_DIR / "malha_bairros_2022" / f"{uf.upper()}.geojson.gz"
    if not p.exists():
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        g = gpd.GeoDataFrame.from_features(json.load(f)["features"], crs=CRS)
    g["_k"] = g["nome"].map(chave)
    g["_km"] = g["municipio"].map(chave)
    return g


def _codigo_municipio(nome, uf):
    """(cd_mun, uf) pelo nome do município (+UF, se houver); None se ambíguo/ausente."""
    k = chave(nome)
    achados = []
    for u in ([uf] if uf else todas_ufs()):
        g = municipios_uf(u)
        if g is not None:
            achados += [(r.cd_mun, r.uf) for r in g[g["_k"] == k].itertuples()]
    return achados[0] if len(achados) == 1 else None


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
        hit = bm[bm["_k"] == k]
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
        avisos.append("Municípios sem divisão em bairros na malha do IBGE (Censo 2022): "
                      + ", ".join(sorted(sem_malha)) + ". Use o mapa por município ou envie os limites da prefeitura.")
    if aproximados:
        avisos.append("Bairros associados pelo nome mais parecido na malha do IBGE — confira: "
                      + "; ".join(aproximados))
    if nao_achados:
        avisos.append("Bairros não encontrados na malha do IBGE (ficaram fora do mapa): " + ", ".join(nao_achados))
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
            nome=("nome", " / ".join), n_pacientes=("n_pacientes", "sum"), n_positivos=("n_positivos", "sum"),
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
    passo = max(5, 5 * math.ceil((hi - lo) / 25))
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


LIMIAR_PONTOS_GRAUS = 4.0   # acima dessa extensão, municípios viram círculos proporcionais


def usar_pontos(areas) -> bool:
    """Áreas espalhadas por uma região grande (ex.: capitais de vários estados)
    ficariam minúsculas como polígonos — nesse caso desenha-se um círculo por
    área (cor = prevalência, tamanho = nº de pacientes) sobre os estados."""
    minx, miny, maxx, maxy = areas.total_bounds
    return max(maxx - minx, maxy - miny) > LIMIAR_PONTOS_GRAUS


def _tam(n, nmax):
    return 40 + 520 * (n / max(nmax, 1))


def figura_estatica(areas, valor_col, titulo, rotulo_area, lims, contexto=None, sem_dados=None,
                    ufs_destaque=(), mostrar_rotulos=True, nota=""):
    """areas: GeoDataFrame com 'nome' e a coluna de valor. contexto: polígonos de
    fundo (brancos). sem_dados: polígonos da mesma categoria sem dados (cinza)."""
    with plt.rc_context({"font.family": _FAMILIA, "font.size": 8.5}):
        cmap = ListedColormap(RAMPA)
        norm = BoundaryNorm(lims, cmap.N)
        fig = plt.figure(figsize=(7.6, 6.0), dpi=150, facecolor="white")
        ax = fig.add_axes([0.075, 0.085, 0.66, 0.83])
        ax.set_facecolor(FUNDO)
        pontos = usar_pontos(areas)
        minx, miny, maxx, maxy = areas.total_bounds
        pad = max(maxx - minx, maxy - miny) * (0.18 if pontos else 0.12) + (1.0 if pontos else 0.01)
        ext = (minx - pad, miny - pad, maxx + pad, maxy + pad)
        if pontos:
            contorno_ufs().plot(ax=ax, color="white", edgecolor=BORDA, linewidth=0.6)
            pts = areas.geometry.representative_point()
            nmax = areas["n_pacientes"].max()
            ax.scatter(pts.x, pts.y, s=[_tam(n, nmax) for n in areas["n_pacientes"]],
                       c=areas[valor_col], cmap=cmap, norm=norm, edgecolor=TINTA, linewidth=0.6, zorder=5)
            if mostrar_rotulos:
                for p, nome, v, n in zip(pts, areas["nome"], areas[valor_col], areas["n_pacientes"]):
                    r = math.sqrt(_tam(n, nmax)) / 2
                    ax.annotate(f"{nome} ({_br(v)}%)", (p.x, p.y), xytext=(r + 3, 0), textcoords="offset points",
                                va="center", fontsize=5.8, color=TINTA, zorder=6,
                                path_effects=[pe.withStroke(linewidth=2, foreground="white")])
        else:
            if contexto is not None and not contexto.empty:
                contexto.cx[ext[0]:ext[2], ext[1]:ext[3]].plot(ax=ax, color="white", edgecolor=BORDA, linewidth=0.6)
            if sem_dados is not None and not sem_dados.empty:
                sem_dados.plot(ax=ax, color=SEM_DADO, edgecolor="white", linewidth=0.6)
            areas.plot(ax=ax, column=valor_col, cmap=cmap, norm=norm, edgecolor="white", linewidth=0.9)
            if mostrar_rotulos:
                pts = areas.geometry.representative_point()
                for p, nome, v in zip(pts, areas["nome"], areas[valor_col]):
                    ax.text(p.x, p.y, f"{nome}\n{_br(v)}%", ha="center", va="center", fontsize=5.6, zorder=5,
                            linespacing=1.1, color=TINTA,
                            path_effects=[pe.withStroke(linewidth=2.2, foreground="white")])
        ax.set_xlim(ext[0], ext[2])
        ax.set_ylim(ext[1], ext[3])
        lat_c = (ext[1] + ext[3]) / 2
        _aspecto(ax, lat_c)
        _grade(ax)
        _norte(ax)
        _escala(ax, lat_c)
        h = [Patch(facecolor=c, edgecolor=TINTA_SUAVE, lw=0.4, label=r) for c, r in zip(RAMPA, rotulos(lims))]
        if sem_dados is not None and not sem_dados.empty:
            h.append(Patch(facecolor=SEM_DADO, edgecolor=TINTA_SUAVE, lw=0.4, label=f"{rotulo_area} sem dados"))
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
            leg2 = ax.legend(handles=hs, title="Pacientes (n)", loc="upper left", bbox_to_anchor=(1.06, 0.25),
                             fontsize=6.8, title_fontsize=7.2, frameon=True, framealpha=0.95, edgecolor=LINHA,
                             borderpad=0.9, labelspacing=1.3, handletextpad=1.2)
        if max(ext[2] - ext[0], ext[3] - ext[1]) < 15:
            _inset(fig, [0.765, 0.60, 0.2, 0.3], set(ufs_destaque), ext)
        fig.suptitle(titulo, x=0.075, ha="left", y=0.985, fontsize=10.5, color=MATA)
        rod = f"{SRC_TXT} · {FONTE_MALHA}" + (f" · {nota}" if nota else "")
        fig.text(0.5, 0.012, rod, ha="center", va="bottom", fontsize=6.0, color=TINTA_SUAVE)
    return fig


def figura_bytes(fig, formato="png", dpi=300) -> bytes:
    buf = io.BytesIO()
    kw = {"pil_kwargs": {"compression": "tiff_lzw"}} if formato == "tiff" else {}
    fig.savefig(buf, format=formato, dpi=dpi, facecolor="white", **kw)
    return buf.getvalue()


# ----------------------------------------------------------------------------
# versão interativa (plotly, SVG puro)
# ----------------------------------------------------------------------------
def _aneis(geom):
    from shapely.geometry import MultiPolygon
    polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    xs, ys = [], []
    for p in polys:
        x, y = p.exterior.xy
        xs += list(x) + [None]
        ys += list(y) + [None]
    return xs, ys


def figura_interativa(areas, valor_col, rotulo_area, lims, contexto=None, sem_dados=None,
                      mostrar_rotulos=True, altura=620):
    import plotly.graph_objects as go
    fig = go.Figure()
    pontos = usar_pontos(areas)
    minx, miny, maxx, maxy = areas.total_bounds
    pad = max(maxx - minx, maxy - miny) * (0.18 if pontos else 0.12) + (1.0 if pontos else 0.01)
    ext = (minx - pad, miny - pad, maxx + pad, maxy + pad)
    if pontos:
        contexto, sem_dados = contorno_ufs(), None
    if contexto is not None and not contexto.empty:
        for g in contexto.cx[ext[0]:ext[2], ext[1]:ext[3]].geometry:
            xs, ys = _aneis(g)
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", fill="toself", fillcolor="#FFFFFF",
                                     line=dict(color=BORDA, width=0.8), hoverinfo="skip", showlegend=False))
    if sem_dados is not None and not sem_dados.empty:
        for _, r in sem_dados.iterrows():
            xs, ys = _aneis(r.geometry)
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", fill="toself", fillcolor=SEM_DADO,
                                     line=dict(color="white", width=1), hoveron="fills", showlegend=False, name="",
                                     hovertemplate=f"<b>{r['nome']}</b><br>Sem dados<extra></extra>"))
    for _, r in (areas.iloc[0:0] if pontos else areas).iterrows():
        xs, ys = _aneis(r.geometry)
        ic = ""
        if pd.notna(r.get("ic95_inf")) and pd.notna(r.get("ic95_sup")) and valor_col == "prevalencia":
            ic = f" (IC 95% {_br(r['ic95_inf'])}–{_br(r['ic95_sup'])}%)"
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines", fill="toself", fillcolor=cor_de(r[valor_col], lims),
            line=dict(color="white", width=1.3), hoveron="fills", showlegend=False, name="",
            hovertemplate=(f"<b>{r['nome']}</b><br>{rotulo_area}<br>Pacientes: {int(r['n_pacientes'])}"
                           f"<br>Prevalência: <b>{_br(r[valor_col])}%</b>{ic}<extra></extra>")))
    if pontos:
        pts = areas.geometry.representative_point()
        nmax = areas["n_pacientes"].max()

        def _ic(r):
            if pd.notna(r.get("ic95_inf")) and pd.notna(r.get("ic95_sup")) and valor_col == "prevalencia":
                return f" (IC 95% {_br(r['ic95_inf'])}–{_br(r['ic95_sup'])}%)"
            return ""
        fig.add_trace(go.Scatter(
            x=pts.x, y=pts.y, mode="markers+text" if mostrar_rotulos else "markers", showlegend=False,
            text=[f"{n} ({_br(v)}%)" for n, v in zip(areas["nome"], areas[valor_col])], textposition="middle right",
            textfont=dict(size=10, color=TINTA),
            marker=dict(size=[math.sqrt(_tam(n, nmax)) * 1.35 for n in areas["n_pacientes"]],
                        color=[cor_de(v, lims) for v in areas[valor_col]], line=dict(color=TINTA, width=0.8)),
            hovertemplate=[f"<b>{r['nome']}</b><br>{rotulo_area}<br>Pacientes: {int(r['n_pacientes'])}"
                           f"<br>Prevalência: <b>{_br(r[valor_col])}%</b>{_ic(r)}<extra></extra>"
                           for _, r in areas.iterrows()],
        ))
    elif mostrar_rotulos:
        pts = areas.geometry.representative_point()
        fig.add_trace(go.Scatter(
            x=pts.x, y=pts.y, mode="text", hoverinfo="skip", showlegend=False,
            text=[f"{n}<br>{_br(v)}%" for n, v in zip(areas["nome"], areas[valor_col])],
            textfont=dict(size=10, color=TINTA, shadow="1px 1px 2px white, -1px -1px 2px white, 1px -1px 2px white, -1px 1px 2px white")))
    for c, r in zip(RAMPA, rotulos(lims)):
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=r,
                                 marker=dict(symbol="square", size=12, color=c, line=dict(color=TINTA_SUAVE, width=0.5))))
    lat_c = (ext[1] + ext[3]) / 2
    eixo = dict(showgrid=True, gridcolor="#E6E1D6", zeroline=False, ticks="inside", mirror=True, showline=True,
                linecolor=TINTA, tickformat=".2f", ticksuffix="°", tickfont=dict(size=10, color=TINTA_SUAVE))
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
# ponto de entrada usado pelo app
# ----------------------------------------------------------------------------
def municipios_com_bairro(metrics: dict) -> list[str]:
    """'Município/UF' que têm pacientes com bairro, do maior para o menor."""
    tb = metrics.get("territorio_bairro")
    if tb is None or tb.empty:
        return []
    g = tb.assign(_r=tb["municipio"].astype(str) + "/" + tb["uf"].astype(str).str.upper()) \
        .groupby("_r")["n_pacientes"].sum().sort_values(ascending=False)
    return [r.rstrip("/") for r in g.index]


def preparar_mapa(metrics: dict, nivel: str, indicador: str, modo_classes: str = "auto",
                  limites=None, col_nome=None, mostrar_rotulos=None, municipio_foco: str | None = None):
    """Monta tudo o que a tela/PDF precisam. Devolve dict com 'ok', 'avisos',
    'fig_estatica', 'fig_interativa', 'titulo' — ou ok=False e 'erro'."""
    valor_col = "prevalencia" if indicador == "todos" else "prevalencia_patogenico"
    qual = "enteroparasitos" if indicador == "todos" else "enteroparasitos patogênicos"
    avisos: list[str] = []
    tab_m = metrics.get("territorio_municipio")
    if tab_m is None or tab_m.empty:
        return {"ok": False, "erro": "Nenhum paciente com município preenchido — não há o que mapear."}
    mun_dados, ufs, av = casar_municipios(tab_m)
    avisos += av
    contexto = None
    if ufs:
        gpd = _gpd()
        contexto = gpd.GeoDataFrame(pd.concat([municipios_uf(u) for u in sorted(ufs)], ignore_index=True), crs=CRS)

    if nivel == "municipio":
        if mun_dados is None:
            return {"ok": False, "erro": "Nenhum município da planilha foi encontrado na malha do IBGE.",
                    "avisos": avisos}
        areas, sem, rot_area = mun_dados, None, "Município"
        titulo = f"Prevalência de {qual} por município de residência"
    else:
        tab_b = metrics.get("territorio_bairro")
        if tab_b is None or tab_b.empty:
            return {"ok": False, "erro": "Nenhum paciente com bairro preenchido.", "avisos": avisos}
        if municipio_foco:
            nome_f, _, uf_f = municipio_foco.partition("/")
            sel = tab_b["municipio"].map(chave) == chave(nome_f)
            if uf_f:
                sel &= tab_b["uf"].astype(str).str.upper() == uf_f.upper()
            tab_b = tab_b[sel]
            if tab_b.empty:
                return {"ok": False, "erro": f"Nenhum bairro com pacientes em {municipio_foco}.", "avisos": avisos}
            # mapa de bairros é de uma cidade: o contexto é só a UF dela
            if uf_f and municipios_uf(uf_f) is not None:
                contexto = municipios_uf(uf_f)
                ufs = {uf_f.upper()}
        if limites is None:
            # padrão: Malha de Bairros do Censo 2022 (IBGE)
            areas, sem, ufs_b, av = casar_bairros_ibge(tab_b)
            avisos += av
            if areas is None:
                return {"ok": False, "erro": "Nenhum bairro da planilha foi encontrado na malha de bairros do "
                                             "IBGE. Confira bairro/município/UF na planilha, use o mapa por "
                                             "município ou envie os limites da prefeitura.", "avisos": avisos}
            ufs = set(ufs) | set(ufs_b)
            fonte_bairros = "Bairros: IBGE, Malha de Bairros (Censo 2022)"
        else:
            areas, todos, av = casar_bairros(tab_b, limites, col_nome)
            avisos += av
            if areas is None:
                return {"ok": False, "erro": "Nenhum bairro da planilha foi encontrado no arquivo de limites "
                                             "(confira a coluna com o nome do bairro).", "avisos": avisos}
            sem = todos[todos["prevalencia"].isna()]
            fonte_bairros = "Bairros: arquivo de limites enviado pelo usuário"
        rot_area = "Bairro"
        munis = sorted(set(tab_b["municipio"].astype(str)) - {""})
        if municipio_foco:
            titulo = f"Prevalência de {qual} por bairro de residência — {municipio_foco}"
        else:
            titulo = f"Prevalência de {qual} por bairro de residência" + (f" — {', '.join(munis)}" if len(munis) <= 2 else "")
        if not ufs:
            ufs = {str(u).upper() for u in tab_b["uf"] if str(u).strip()}

    nota = fonte_bairros if nivel != "municipio" else ""
    lims = classes(areas[valor_col], modo_classes)
    if mostrar_rotulos is None:
        mostrar_rotulos = len(areas) <= 15
    pequenos = int((areas["n_pacientes"] < 10).sum())
    if pequenos:
        avisos.append(f"{pequenos} área(s) com menos de 10 pacientes: prevalência pouco precisa — "
                      "interprete com cuidado (veja o IC 95% na tabela).")
    fig_e = figura_estatica(areas, valor_col, titulo, rot_area, lims, contexto=contexto, sem_dados=sem,
                            ufs_destaque=ufs, mostrar_rotulos=mostrar_rotulos, nota=nota)
    fig_i = figura_interativa(areas, valor_col, rot_area, lims, contexto=contexto, sem_dados=sem,
                              mostrar_rotulos=mostrar_rotulos)
    return {"ok": True, "avisos": avisos, "fig_estatica": fig_e, "fig_interativa": fig_i, "titulo": titulo}
