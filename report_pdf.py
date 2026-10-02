"""
Geração do relatório em PDF — Pirajá · Entero
Usa reportlab (layout) + matplotlib (gráficos estáticos), ambas bibliotecas puras em Python,
sem dependências de sistema — rodam sem problemas no Streamlit Community Cloud.
"""
import io
from datetime import datetime
from pathlib import Path

import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether, HRFlowable,
)

# ---------------------------------------------------------------- paleta
# Identidade visual Pirajá — "Mata, barro e papel"
INK = colors.HexColor("#1B2421")          # tinta
INK_SOFT = colors.HexColor("#4E5B55")
INK_FAINT = colors.HexColor("#7A857F")
TEAL = colors.HexColor("#328567")         # verde-folha
TEAL_DARK = colors.HexColor("#11483D")    # verde-mata
TEAL_TINT = colors.HexColor("#E3EEE8")
BRICK = colors.HexColor("#9C4A2F")        # cobre
BRICK_TINT = colors.HexColor("#F3E4DB")
SAGE = colors.HexColor("#A9C3B8")
LINE = colors.HexColor("#DCD6C8")
BG = colors.HexColor("#F4F1EA")           # papel

MPL_TEAL = "#328567"
MPL_TEAL_DARK = "#11483D"
MPL_BRICK = "#9C4A2F"
MPL_SAGE = "#A9C3B8"
MPL_LINE = "#DCD6C8"
MPL_CATEGORIA = {"Patogênico": MPL_BRICK, "Comensal": MPL_TEAL, "Não classificado": MPL_SAGE}

# ---------------------------------------------------------------- fontes
# Fraunces (títulos e números) e Instrument Sans (texto), ambas sob licença
# SIL OFL, embutidas a partir de brand/fonts. Se os arquivos não estiverem
# presentes, o relatório cai para Times/Helvetica sem quebrar.
_FONT_DIR = Path(__file__).parent / "brand" / "fonts"
FONT_TITLE = "Times-Bold"
FONT_BODY = "Helvetica"
FONT_BODY_BOLD = "Helvetica-Bold"
_MPL_FAMILY = "sans-serif"
try:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont("Fraunces-SemiBold", str(_FONT_DIR / "Fraunces-SemiBold.ttf")))
    pdfmetrics.registerFont(TTFont("InstrumentSans", str(_FONT_DIR / "InstrumentSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("InstrumentSans-SemiBold", str(_FONT_DIR / "InstrumentSans-SemiBold.ttf")))
    pdfmetrics.registerFontFamily(
        "InstrumentSans", normal="InstrumentSans", bold="InstrumentSans-SemiBold",
        italic="InstrumentSans", boldItalic="InstrumentSans-SemiBold",
    )
    FONT_TITLE = "Fraunces-SemiBold"
    FONT_BODY = "InstrumentSans"
    FONT_BODY_BOLD = "InstrumentSans-SemiBold"
except Exception:  # noqa: BLE001
    pass
try:
    for _f in ("InstrumentSans-Regular.ttf", "InstrumentSans-SemiBold.ttf"):
        fm.fontManager.addfont(str(_FONT_DIR / _f))
    _MPL_FAMILY = "Instrument Sans"
except Exception:  # noqa: BLE001
    pass

plt.rcParams.update({
    "font.family": _MPL_FAMILY,
    "axes.edgecolor": MPL_LINE,
    "axes.labelcolor": "#4E5B55",
    "text.color": "#1B2421",
    "xtick.color": "#4E5B55",
    "ytick.color": "#4E5B55",
    "axes.grid": True,
    "grid.color": MPL_LINE,
    "grid.linewidth": 0.6,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})


def _fig_to_image(fig, width_mm=160):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    w = width_mm * mm
    from PIL import Image as PILImage
    pil = PILImage.open(buf)
    aspect = pil.height / pil.width
    buf.seek(0)
    return Image(buf, width=w, height=w * aspect)


def _chart_especies(especies_df):
    if especies_df.empty:
        return None
    df = especies_df.sort_values("prevalencia")
    colors_map = MPL_CATEGORIA
    bar_colors = [colors_map.get(c, MPL_SAGE) for c in df["categoria"]]
    fig, ax = plt.subplots(figsize=(6.2, max(1.6, 0.4 * len(df))))
    ax.barh(df["especie"], df["prevalencia"], color=bar_colors)
    ax.set_xlabel("Prevalência (%)")
    for i, v in enumerate(df["prevalencia"]):
        ax.text(v + 0.5, i, f"{v}%", va="center", fontsize=8)
    fig.tight_layout()
    return _fig_to_image(fig)


def _chart_todos_parasitos(todos_df):
    """Gráfico unificado de prevalência por espécie (fecal + lâmina), com
    hachura indicando o domínio da amostra (fezes vs. lâmina) e cor indicando a
    categoria (patogênico/comensal)."""
    if todos_df.empty:
        return None
    df = todos_df.sort_values("prevalencia")
    colors_map = MPL_CATEGORIA

    def _hatch_for(dominio):
        if dominio == "Fecal":
            return ""
        if dominio == "Fecal + Lâmina":
            return "xx"
        return "///"  # qualquer variante de "Lâmina (...)"

    bar_colors = [colors_map.get(c, MPL_SAGE) for c in df["categoria"]]
    hatches = [_hatch_for(d) for d in df["dominio"]]
    fig, ax = plt.subplots(figsize=(6.2, max(1.6, 0.42 * len(df))))
    bars = ax.barh(df["especie"], df["prevalencia"], color=bar_colors)
    for bar, h in zip(bars, hatches):
        bar.set_hatch(h)
        bar.set_edgecolor("white")
    ax.set_xlabel("Prevalência (%)")
    for i, (v, met) in enumerate(zip(df["prevalencia"], df["metodos"])):
        ax.text(v + 0.5, i, f"{v}% · {met}", va="center", fontsize=7)
    fig.tight_layout()
    return _fig_to_image(fig)


def _chart_poli(neg, mono, poli):
    fig, ax = plt.subplots(figsize=(4.2, 4.2))
    vals = [neg, mono, poli]
    labels = ["Negativo", "Monoparasitismo", "Poliparasitismo"]
    cols = [MPL_SAGE, MPL_TEAL, MPL_BRICK]
    if sum(vals) == 0:
        plt.close(fig)
        return None
    ax.pie(vals, labels=labels, autopct=lambda p: f"{p:.0f}%" if p > 0 else "", colors=cols,
           wedgeprops={"linewidth": 1, "edgecolor": "white"}, textprops={"fontsize": 8})
    fig.tight_layout()
    return _fig_to_image(fig, width_mm=90)


def _chart_metodos(metodos_df):
    if metodos_df.empty:
        return None
    fig, ax = plt.subplots(figsize=(6.2, 3))
    ax.bar(metodos_df["metodo"], metodos_df["prevalencia"], color=MPL_TEAL)
    ax.set_ylabel("Prevalência (%)")
    # eixo fixo em 0-105%: evita que o rótulo de texto (v + 0.5) fique fora da
    # área visível quando TODAS as prevalências são 0% (domínio all-negative),
    # o que antes inflava desproporcionalmente a imagem via bbox_inches="tight"
    ax.set_ylim(0, 105)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right", fontsize=7.5)
    for i, v in enumerate(metodos_df["prevalencia"]):
        ax.text(i, v + 2, f"{v}%", ha="center", fontsize=8)
    fig.tight_layout()
    return _fig_to_image(fig)


def _chart_ncoletas(efeito_df):
    if efeito_df.empty:
        return None
    fig, ax = plt.subplots(figsize=(6.2, 3))
    labels = [f"{int(r.n_potes_entregues)} pote(s)\nn={int(r.n_pacientes)}" for r in efeito_df.itertuples()]
    ax.bar(labels, efeito_df["prevalencia"], color=MPL_TEAL_DARK)
    ax.set_ylabel("Prevalência (%)")
    # mesmo racional do _chart_metodos: eixo fixo evita estouro do bbox quando
    # todos os subgrupos têm 0% de prevalência.
    ax.set_ylim(0, 105)
    for i, v in enumerate(efeito_df["prevalencia"]):
        ax.text(i, v + 2, f"{v}%", ha="center", fontsize=8)
    fig.tight_layout()
    return _fig_to_image(fig)


def _chart_cumulativa(cum_df):
    if cum_df.empty:
        return None
    fig, ax = plt.subplots(figsize=(6.2, 3))
    ax.plot(cum_df["k"], cum_df["prevalencia_cumulativa"], marker="o", color=MPL_TEAL_DARK)
    ax.set_xlabel("Nº de potes considerados (cumulativo)")
    ax.set_ylabel("Prevalência cumulativa (%)")
    ax.set_xticks(cum_df["k"])
    # eixo fixo em 0-105%, mesmo racional das outras funções _chart_*: evita que
    # o rótulo de texto acima do ponto estoure o bbox quando a prevalência
    # cumulativa é 0% (ou quando há um único ponto, k=1).
    ax.set_ylim(0, 105)
    for x, v in zip(cum_df["k"], cum_df["prevalencia_cumulativa"]):
        ax.text(x, v + 3, f"{v}%", ha="center", fontsize=8)
    fig.tight_layout()
    return _fig_to_image(fig)


def _styles():
    ss = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("lp_title", parent=ss["Title"], fontName=FONT_TITLE,
                                 fontSize=20, textColor=TEAL_DARK, alignment=TA_LEFT, spaceAfter=2),
        "eyebrow": ParagraphStyle("lp_eyebrow", parent=ss["Normal"], fontName=FONT_BODY_BOLD,
                                   fontSize=8.5, textColor=BRICK, spaceAfter=10, tracking=0.5),
        "h2": ParagraphStyle("lp_h2", parent=ss["Heading2"], fontName=FONT_TITLE,
                              fontSize=13.5, textColor=TEAL_DARK, spaceBefore=16, spaceAfter=6),
        "body": ParagraphStyle("lp_body", parent=ss["Normal"], fontName=FONT_BODY,
                                fontSize=9.5, textColor=INK_SOFT, leading=13.5),
        "note": ParagraphStyle("lp_note", parent=ss["Normal"], fontName=FONT_BODY,
                                fontSize=9, textColor=INK_SOFT, leading=13, backColor=BRICK_TINT,
                                borderPadding=8, leftIndent=4),
        "small": ParagraphStyle("lp_small", parent=ss["Normal"], fontName=FONT_BODY,
                                 fontSize=8, textColor=INK_FAINT),
    }
    return styles


def _prev_txt(prev, n):
    """'—' quando não há paciente conclusivo no denominador (0,0% daria a
    entender que houve exame e deu negativo)."""
    return f"{prev:.1f}%" if n else "—"


def _base_txt(pos, n, tem_metodo, dominio):
    if not tem_metodo:
        return f"Não avaliado: nenhum método de {dominio} nesta planilha"
    if not n:
        return "Não avaliado: nenhum resultado conclusivo"
    return f"{pos} de {n} pacientes (conclusivas)"


def _stat_table(metrics):
    # Coluna do meio: prevalência de lâmina calculada sobre TODOS os pacientes com
    # resultado conclusivo de lâmina (lamina_conclusivo) — não mais restrita ao
    # subgrupo que só entregou lâmina (ver analysis_engine.py, alteração v5 -> v6,
    # item 12). O subgrupo "só lâmina" continua disponível em
    # metrics['lamina_only_conclusivo'] / ['lamina_only_inconclusivo'] e é citado
    # à parte, na nota de atenção logo abaixo desta tabela.
    dominios = {m[3] for m in metrics.get("metodos_ativos", [])}
    n_f = len(metrics["fecal_conclusivo"])
    n_l = len(metrics["lamina_conclusivo"])
    n_c = len(metrics["combinada_base"])
    data = [
        ["PREVALÊNCIA — AMOSTRA FECAL", "PREVALÊNCIA — LÂMINA (TODOS)", "PREVALÊNCIA COMBINADA"],
        [_prev_txt(metrics['prev_fecal'], n_f), _prev_txt(metrics['prev_lamina'], n_l),
         _prev_txt(metrics['prev_combinada'], n_c)],
        [
            f"IC95% {_ic_texto(metrics['prev_fecal_ic95_inf'], metrics['prev_fecal_ic95_sup'])}",
            f"IC95% {_ic_texto(metrics['prev_lamina_ic95_inf'], metrics['prev_lamina_ic95_sup'])}",
            f"IC95% {_ic_texto(metrics['prev_combinada_ic95_inf'], metrics['prev_combinada_ic95_sup'])}",
        ],
        [
            _base_txt(int(metrics['fecal_conclusivo']['positivo_fecal'].sum()), n_f, "fecal" in dominios, "fezes"),
            _base_txt(int(metrics['lamina_conclusivo']['positivo_lamina'].sum()), n_l, "lamina" in dominios, "lâmina"),
            _base_txt(int(metrics['combinada_base']['positivo_algum_metodo'].sum()), n_c, True, ""),
        ],
    ]
    # linhas de IC e de base viram Paragraph para quebrar linha dentro da
    # célula (textos de "Não avaliado" não cabem numa linha só)
    ic_style = ParagraphStyle("lp_stat_ic", fontName=FONT_BODY, fontSize=8, leading=10, textColor=TEAL)
    base_style = ParagraphStyle("lp_stat_base", fontName=FONT_BODY, fontSize=8, leading=10,
                                textColor=INK_FAINT)
    data[2] = [Paragraph(txt if n else "", ic_style) for txt, n in zip(data[2], (n_f, n_l, n_c))]
    data[3] = [Paragraph(txt, base_style) for txt in data[3]]
    t = Table(data, colWidths=[56 * mm, 56 * mm, 56 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), FONT_BODY_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), INK_FAINT),
        ("FONTNAME", (0, 1), (-1, 1), FONT_TITLE),
        ("FONTSIZE", (0, 1), (-1, 1), 20),
        ("TEXTCOLOR", (0, 1), (-1, 1), TEAL_DARK),
        ("FONTNAME", (0, 2), (-1, 2), FONT_BODY),
        ("FONTSIZE", (0, 2), (-1, 2), 8),
        ("TEXTCOLOR", (0, 2), (-1, 2), TEAL),
        ("FONTNAME", (0, 3), (-1, 3), FONT_BODY),
        ("FONTSIZE", (0, 3), (-1, 3), 8),
        ("TEXTCOLOR", (0, 3), (-1, 3), INK_FAINT),
        ("BOX", (0, 0), (0, -1), 0.7, LINE),
        ("BOX", (1, 0), (1, -1), 0.7, LINE),
        ("BOX", (2, 0), (2, -1), 0.7, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _ic_texto(inf, sup):
    """Formata um par (limite_inferior, limite_superior) de IC95% como texto curto
    para caber em tabela do PDF. Retorna travessão quando não calculável (n=0)."""
    if inf is None or sup is None or pd.isna(inf) or pd.isna(sup):
        return "—"
    return f"{inf:.1f}–{sup:.1f}%"


def _with_ic_column(df, prev_col="prevalencia", inf_col="ic95_inf", sup_col="ic95_sup", label="ic95"):
    """Devolve cópia do DataFrame com uma coluna de texto 'IC 95%' combinando os
    limites de Wilson, no lugar das duas colunas numéricas ic95_inf/ic95_sup —
    mantém a tabela do PDF compacta o bastante para caber na largura da página."""
    out = df.copy()
    if inf_col in out.columns and sup_col in out.columns:
        out[label] = [
            _ic_texto(i, s) for i, s in zip(out[inf_col], out[sup_col])
        ]
        out = out.drop(columns=[inf_col, sup_col])
    return out


def _df_table(df, col_labels=None, col_widths=None, max_rows=None, font_size=8, h_padding=6):
    styles = _styles()
    cell_style = ParagraphStyle("lp_cell", parent=styles["body"], fontSize=font_size,
                                leading=font_size * 1.3, textColor=INK)
    header_style = ParagraphStyle("lp_cell_header", parent=styles["body"], fontSize=font_size,
                                   leading=font_size * 1.25,
                                   fontName=FONT_BODY_BOLD, textColor=INK_FAINT)
    if df.empty:
        return Paragraph("Sem dados.", styles["body"])
    if max_rows:
        df = df.head(max_rows)
    headers = col_labels or list(df.columns)
    header_row = [Paragraph(str(h), header_style) for h in headers]
    body_rows = [[Paragraph(str(v), cell_style) for v in row] for row in df.astype(str).values.tolist()]
    data = [header_row] + body_rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.9, SAGE),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), h_padding),
        ("RIGHTPADDING", (0, 0), (-1, -1), h_padding),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


# ---------------------------------------------------------------- v8
def _resumo_config(metrics):
    """Texto curto com a configuração usada na análise (ou None)."""
    cfg = metrics.get("config")
    if cfg is None:
        return None
    fezes = [n for _, n, _, d in metrics.get("metodos_ativos", []) if d == "fecal"]
    lamina = [n for _, n, _, d in metrics.get("metodos_ativos", []) if d == "lamina"]
    pat = sorted(e for e, c in cfg.categorias.items() if c == "Patogênico")
    com = sorted(e for e, c in cfg.categorias.items() if c == "Comensal")
    partes = [
        f"<b>Métodos de fezes:</b> {', '.join(fezes) or '—'}",
        f"<b>Métodos de lâmina:</b> {', '.join(lamina) or '—'}",
        f"<b>Amostras por paciente:</b> até P{cfg.n_amostras}" if cfg.n_amostras else "<b>Amostras por paciente:</b> todas",
        f"<b>Patogênicos:</b> {', '.join(pat) or '—'}",
        f"<b>Comensais:</b> {', '.join(com) or '—'}",
    ]
    if cfg.excluidos:
        partes.append(f"<b>Excluídos da análise:</b> {', '.join(sorted(cfg.excluidos))}")
    return " &middot; ".join(partes)


def _chart_especies_titulo(especies_df, titulo):
    if especies_df.empty:
        return None
    df = especies_df.sort_values("prevalencia")
    colors_map = MPL_CATEGORIA
    bar_colors = [colors_map.get(c, MPL_SAGE) for c in df["categoria"]]
    fig, ax = plt.subplots(figsize=(4.2, max(1.8, 0.42 * len(df) + 0.6)))
    ax.barh(df["especie"], df["prevalencia"], color=bar_colors)
    ax.set_title(titulo, fontsize=9, loc="left", color="#11483D")
    ax.set_xlabel("Prevalência (%)", fontsize=8)
    ax.tick_params(labelsize=7)
    vmax = float(df["prevalencia"].max())
    ax.set_xlim(0, max(10.0, min(115.0, vmax * 1.3)))
    for i, v in enumerate(df["prevalencia"]):
        ax.text(v + 0.5, i, f"{v}%", va="center", fontsize=7)
    fig.tight_layout()
    return _fig_to_image(fig, width_mm=84)


def _secao_dominio(story, styles, titulo, esp_df, n_base, n_pos, prev, ic, n_pat, prev_pat, ic_pat, tem_metodo):
    story.append(Paragraph(titulo, styles["h2"]))
    if not tem_metodo:
        story.append(Paragraph("Nenhum método deste tipo de amostra foi incluído na análise.", styles["body"]))
        return
    if not n_base:
        story.append(Paragraph("Nenhum resultado conclusivo neste tipo de amostra.", styles["body"]))
        return
    story.append(Paragraph(
        f"<b>Todos os parasitos:</b> {prev:.1f}% ({n_pos} de {n_base}; IC95% {_ic_texto(*ic)}) &middot; "
        f"<b>Somente patogênicos:</b> {prev_pat:.1f}% ({n_pat} de {n_base}; IC95% {_ic_texto(*ic_pat)}). "
        "Base: pacientes com resultado conclusivo neste tipo de amostra.",
        styles["body"],
    ))
    story.append(Spacer(1, 2 * mm))
    img_all = _chart_especies_titulo(esp_df, "Todos os parasitos")
    pat_df = esp_df[esp_df["categoria"] == "Patogênico"] if not esp_df.empty else esp_df
    img_pat = _chart_especies_titulo(pat_df, "Somente patogênicos")
    cells = [img_all or Paragraph("Nenhum parasito detectado.", styles["small"]),
             img_pat or Paragraph("Nenhum parasito patogênico detectado.", styles["small"])]
    t = Table([cells], colWidths=[87 * mm, 87 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(t)
    if not esp_df.empty:
        story.append(Spacer(1, 2 * mm))
        tab = _with_ic_column(esp_df).rename(columns={
            "especie": "Espécie", "n": "N", "prevalencia": "Prevalência %", "categoria": "Categoria", "ic95": "IC 95%"})
        story.append(_df_table(tab, col_widths=[52 * mm, 16 * mm, 24 * mm, 26 * mm, 26 * mm]))


def _secoes_por_dominio(story, styles, metrics):
    dominios = {m[3] for m in metrics.get("metodos_ativos", [])}
    lam_nomes = [n for _, n, _, d in metrics.get("metodos_ativos", []) if d == "lamina"]
    fc, lc = metrics["fecal_conclusivo"], metrics["lamina_conclusivo"]
    _secao_dominio(
        story, styles, "Parasitos em amostras de fezes — todos x somente patogênicos",
        metrics["especies_resumo"], len(fc), int(fc["positivo_fecal"].sum()) if len(fc) else 0,
        metrics["prev_fecal"], (metrics["prev_fecal_ic95_inf"], metrics["prev_fecal_ic95_sup"]),
        metrics["n_fecal_patogenico"], metrics["prev_fecal_patogenico"],
        (metrics["prev_fecal_patogenico_ic95_inf"], metrics["prev_fecal_patogenico_ic95_sup"]),
        "fecal" in dominios,
    )
    _secao_dominio(
        story, styles, f"Parasitos na lâmina ({' / '.join(lam_nomes) or 'Graham'}) — todos x somente patogênicos",
        metrics["especies_lamina_resumo"], len(lc), int(lc["positivo_lamina"].sum()) if len(lc) else 0,
        metrics["prev_lamina"], (metrics["prev_lamina_ic95_inf"], metrics["prev_lamina_ic95_sup"]),
        metrics["n_lamina_patogenico"], metrics["prev_lamina_patogenico"],
        (metrics["prev_lamina_patogenico_ic95_inf"], metrics["prev_lamina_patogenico_ic95_sup"]),
        "lamina" in dominios,
    )


def build_pdf_report(metrics: dict, logo_path: str | None = None) -> bytes:
    styles = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=18 * mm, bottomMargin=16 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title="Relatório de Análise Epidemiológica — Pirajá",
    )
    story = []

    # métodos efetivamente presentes nesta planilha — usado para montar tabelas/
    # pivots dinamicamente, em vez de assumir sempre os quatro métodos originais.
    metodos_ativos_nomes = metrics.get("metodos_ativos_nomes") or (
        list(metrics["metodos_resumo"]["metodo"]) if not metrics["metodos_resumo"].empty else []
    )

    # ---- cabeçalho: assinatura Pirajá · Entero + filete verde-mata ----
    meta_style = ParagraphStyle("lp_meta", parent=styles["small"], alignment=TA_RIGHT, leading=10.5)
    meta_block = [
        Paragraph("Relatório de análise epidemiológica", meta_style),
        Paragraph(f"Gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}", meta_style),
    ]
    logo_cell = ""
    if logo_path:
        try:
            # proporção da assinatura horizontal com módulo (1688 x 648 px)
            logo_cell = Image(logo_path, width=44 * mm, height=44 * mm * 648 / 1688)
        except Exception:  # noqa: BLE001
            logo_cell = ""
    if logo_cell == "":
        logo_cell = Paragraph("Pirajá", styles["title"])
    t = Table([[logo_cell, meta_block]], colWidths=[90 * mm, 84 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(t)
    story.append(Spacer(1, 3 * mm))
    story.append(HRFlowable(width="100%", thickness=1.4, color=TEAL_DARK))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Relatório de análise epidemiológica", styles["title"]))
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph(
        f"{metrics['total']} pacientes cadastrados &middot; {len(metrics['fecal'])} com amostra fecal "
        f"entregue &middot; {len(metrics['apenas_lamina'])} só com lâmina &middot; métodos "
        f"analisados: {', '.join(metodos_ativos_nomes) if metodos_ativos_nomes else '—'}.",
        styles["body"],
    ))
    cfg_txt = _resumo_config(metrics)
    if cfg_txt:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("<b>Configuração da análise</b> &middot; " + cfg_txt, styles["small"]))
    story.append(Spacer(1, 4 * mm))

    # ---- resumo executivo ----
    story.append(_stat_table(metrics))
    story.append(Spacer(1, 3 * mm))

    # "Amostras inconclusivas": agora soma TODOS os pacientes com lâmina
    # inconclusiva (lamina_inconclusivo, base completa), não mais só o subgrupo
    # que entregou exclusivamente lâmina — consistente com prev_lamina acima,
    # que também passou a usar a base completa.
    n_inconclusivas = len(metrics["fecal_inconclusivo"]) + len(metrics["lamina_inconclusivo"])
    if n_inconclusivas > 0:
        note_inc = (
            f"<b>Amostras inconclusivas:</b> {len(metrics['fecal_inconclusivo'])} criança(s) com "
            "pote de fezes entregue tiveram todos os métodos fecais marcados como \"Amostra "
            "insuficiente\" (ou sem resultado registrado)"
            + (f"; {len(metrics['lamina_inconclusivo'])} paciente(s) com lâmina entregue na mesma "
               "situação" if len(metrics['lamina_inconclusivo']) else "")
            + ". Esses pacientes foram excluídos dos denominadores de prevalência — não contam "
              "como negativas."
        )
        story.append(Paragraph(note_inc, styles["note"]))
        story.append(Spacer(1, 2 * mm))

    if len(metrics["apenas_lamina"]) > 0:
        note = (
            f"<b>Atenção:</b> {len(metrics['apenas_lamina'])} paciente(s) só entregaram a lâmina, nunca "
            "o pote de fezes — para eles, apenas o(s) método(s) de lâmina pôde(puderam) ser "
            "pesquisado(s). Os resultados desse subgrupo já estão incluídos na prevalência de lâmina "
            "do resumo acima (que soma todos os pacientes com resultado conclusivo de lâmina, tenham "
            f"entregado só lâmina ou fezes e lâmina); isoladamente, a prevalência só neste subgrupo é "
            f"de {metrics['prev_lamina_only']:.1f}% ({int(metrics['lamina_only_conclusivo']['positivo_lamina'].sum())} "
            f"de {len(metrics['lamina_only_conclusivo'])} pacientes conclusivos)."
        )
        story.append(Paragraph(note, styles["note"]))

    # ---- v8: fezes x lâmina, todos x somente patogênicos ----
    _secoes_por_dominio(story, styles, metrics)

    # ---- profundidade de amostragem ----
    story.append(Paragraph("Pacientes por profundidade de amostragem", styles["h2"]))
    cat_df = metrics["cat_counts"].rename("n_pacientes").to_frame()
    cat_df["%"] = (100 * cat_df["n_pacientes"] / metrics["total"]).round(1)
    cat_df = cat_df.reset_index().rename(columns={"index": "categoria_amostragem", "categoria_amostragem": "Categoria"})
    cat_df.columns = ["Categoria", "Nº crianças", "%"]
    story.append(_df_table(cat_df, col_widths=[80 * mm, 35 * mm, 25 * mm]))

    # ---- prevalência de todos os parasitos (fecal + lâmina, unificado) ----
    story.append(Paragraph("Prevalência de todos os parasitos", styles["h2"]))
    story.append(Paragraph(
        "Espécies fecais e achados de lâmina, reunidos num só gráfico. As bases de cálculo diferem "
        "por domínio (ver coluna \"Base N\" na tabela abaixo). Quando a mesma espécie foi encontrada "
        "em métodos de domínios diferentes (ex.: Enterobius vermicularis, tipicamente por um método "
        "de lâmina, mas ocasionalmente também visível num método fecal), ela aparece numa única "
        "linha \"Fecal + Lâmina\", com denominador e numerador calculados por criança — quem foi "
        "detectado em mais de um método conta uma vez só, não duas.",
        styles["small"],
    ))
    story.append(Spacer(1, 1.5 * mm))
    todos_img = _chart_todos_parasitos(metrics["todos_parasitos_resumo"])
    if todos_img:
        story.append(todos_img)
        story.append(Spacer(1, 2 * mm))
    todos_table = _with_ic_column(metrics["todos_parasitos_resumo"]).rename(columns={
        "especie": "Espécie", "categoria": "Categoria", "dominio": "Amostra", "n": "N",
        "prevalencia": "Prevalência %", "base_n": "Base N", "metodos": "Método(s)", "ic95": "IC 95%",
    })
    story.append(_df_table(todos_table, col_widths=[32 * mm, 18 * mm, 20 * mm, 10 * mm, 18 * mm, 14 * mm, 28 * mm, 20 * mm]))

    # ---- prevalência por método e espécie ----
    story.append(Paragraph("Prevalência por método diagnóstico e espécie", styles["h2"]))
    story.append(Paragraph(
        "Cada valor é a prevalência (%) daquela espécie especificamente pelo método indicado; "
        "denominador = pacientes com resultado conclusivo naquele método. Uma mesma espécie pode "
        "aparecer em mais de um método fecal. Colunas mostram só os métodos presentes nesta "
        "planilha.",
        styles["small"],
    ))
    story.append(Spacer(1, 1.5 * mm))
    if not metrics["metodo_especie_resumo"].empty and metodos_ativos_nomes:
        pivot = metrics["metodo_especie_resumo"].pivot_table(
            index="especie", columns="metodo", values="prevalencia", aggfunc="first",
        ).reindex(columns=metodos_ativos_nomes)
        pivot_df = pivot.reset_index().rename(columns={"especie": "Espécie"})
        pivot_df = pivot_df.fillna("—")
        # cabeçalho com quebra de linha em hífen e antes de parênteses, para
        # nomes longos ("Baermann-Picanço", "Ritchie (formol-éter)") não serem
        # cortados no meio da palavra em colunas estreitas
        pivot_labels = ["Espécie"] + [
            str(c).replace("-", "-<br/>").replace(" (", "<br/>(") for c in pivot_df.columns[1:]
        ]
        # largura útil da página A4 com margens de 18 mm = 174 mm. Antes cada
        # coluna de método tinha no mínimo 18 mm, e com 6+ métodos a tabela
        # passava da margem direita. Agora as colunas dividem o espaço que
        # sobra (até 25 mm cada) e a fonte diminui quando há muitos métodos.
        n_metodo_cols = max(len(metodos_ativos_nomes), 1)
        largura_util = 174
        col_especie = 44 if n_metodo_cols > 5 else 50
        col_metodo = min(25, (largura_util - col_especie) / n_metodo_cols)
        col_w = [col_especie * mm] + [col_metodo * mm] * n_metodo_cols
        story.append(_df_table(pivot_df, col_labels=pivot_labels, col_widths=col_w,
                               font_size=7 if n_metodo_cols > 5 else 8,
                               h_padding=2 if n_metodo_cols > 5 else 6))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            "Intervalos de confiança de 95% (Wilson) correspondentes a cada célula acima:",
            styles["small"],
        ))
        story.append(Spacer(1, 1 * mm))
        me_table = _with_ic_column(metrics["metodo_especie_resumo"]).rename(columns={
            "metodo": "Método", "especie": "Espécie", "n": "N",
            "prevalencia": "Prevalência %", "categoria": "Categoria", "ic95": "IC 95%",
        })
        story.append(_df_table(me_table, col_widths=[25 * mm, 40 * mm, 12 * mm, 22 * mm, 25 * mm, 26 * mm]))
    else:
        story.append(Paragraph("Sem dados suficientes para este cruzamento.", styles["body"]))

    # ---- prevalência por espécie ----
    story.append(Paragraph("Prevalência por espécie — métodos fecais (base: fezes com resultado conclusivo)", styles["h2"]))
    story.append(Paragraph(
        "Cada espécie encontrada por algum método fecal presente nesta planilha, especificamente — "
        "inclusive Enterobius vermicularis, se algum caso tiver sido identificado incidentalmente "
        "num método fecal (achado válido, não erro de digitação). A prevalência combinada dessa "
        "espécie com métodos de lâmina, sem contar o mesmo paciente duas vezes, está no gráfico "
        "unificado acima.",
        styles["small"],
    ))
    story.append(Spacer(1, 1.5 * mm))
    esp_img = _chart_especies(metrics["especies_resumo"])
    if esp_img:
        story.append(esp_img)
        story.append(Spacer(1, 2 * mm))
    esp_table = _with_ic_column(metrics["especies_resumo"]).rename(
        columns={"especie": "Espécie", "n": "N", "prevalencia": "Prevalência %", "categoria": "Categoria", "ic95": "IC 95%"}
    )
    story.append(_df_table(esp_table, col_widths=[52 * mm, 16 * mm, 24 * mm, 24 * mm, 24 * mm]))

    # ---- poliparasitismo ----
    story.append(Paragraph("Mono x poliparasitismo (base: espécies de origem fecal)", styles["h2"]))
    poli_img = _chart_poli(metrics["neg"], metrics["mono"], metrics["poli"])
    if poli_img:
        story.append(poli_img)
        story.append(Spacer(1, 2 * mm))
    if not metrics["combos_resumo"].empty:
        story.append(Paragraph("Combinações mais frequentes:", styles["body"]))
        combo_table = metrics["combos_resumo"].rename(columns={"combinacao": "Combinação", "n": "N"})
        story.append(_df_table(combo_table, col_widths=[110 * mm, 20 * mm]))

    # ---- comparação de métodos ----
    story.append(Paragraph("Comparação entre métodos diagnósticos", styles["h2"]))
    story.append(Paragraph(
        "Denominador = pacientes com resultado conclusivo naquele método específico (exclui "
        "\"Amostra insuficiente\" e \"Não realizado\"). Lista os métodos efetivamente presentes "
        "nesta planilha.",
        styles["small"],
    ))
    story.append(Spacer(1, 1.5 * mm))
    met_img = _chart_metodos(metrics["metodos_resumo"])
    if met_img:
        story.append(met_img)
        story.append(Spacer(1, 2 * mm))
    met_table = _with_ic_column(metrics["metodos_resumo"]).rename(columns={
        "metodo": "Método", "amostra_biologica": "Amostra", "n_pacientes_testaveis": "Testáveis",
        "n_pacientes_positivas": "Positivas", "n_pacientes_inconclusivas": "Inconclusivas",
        "prevalencia": "Prevalência %", "ic95": "IC 95%",
    })
    story.append(_df_table(met_table, col_widths=[24 * mm, 20 * mm, 16 * mm, 16 * mm, 18 * mm, 20 * mm, 22 * mm]))

    story.append(Spacer(1, 3 * mm))
    subsection_style = ParagraphStyle(
        "lp_h3_inline", parent=styles["h2"], fontSize=11.5, spaceBefore=6, spaceAfter=4,
    )
    story.append(Paragraph("HPJ x Willis — teste de McNemar", subsection_style))
    mc = metrics["mcnemar_hpj_willis"]
    if mc["n_pareado"] == 0 or mc["tabela"] is None:
        story.append(Paragraph(
            "Sem pacientes com resultado conclusivo em HPJ e Willis simultaneamente (ou um dos dois "
            "métodos não está presente nesta planilha) — teste não calculado.",
            styles["body"],
        ))
    else:
        tb = mc["tabela"]
        story.append(Paragraph(
            "Compara os dois métodos aplicados à mesma amostra de fezes da mesma criança (dados "
            "pareados), usando só os pacientes em que os dois métodos discordaram entre si.",
            styles["small"],
        ))
        story.append(Spacer(1, 1.5 * mm))
        mc_table_data = pd.DataFrame(
            [["HPJ +", tb["pp"], tb["pn"]], ["HPJ −", tb["np"], tb["nn"]]],
            columns=["", "Willis +", "Willis −"],
        )
        story.append(_df_table(mc_table_data, col_widths=[30 * mm, 30 * mm, 30 * mm]))
        story.append(Spacer(1, 2 * mm))
        metodo_label = {
            "exato": "teste exato (< 25 discordâncias)",
            "chi2_corrigido": "qui-quadrado com correção de continuidade",
            "sem_discordancia": "sem discordâncias — nada a testar",
        }.get(mc["metodo"], mc["metodo"])
        story.append(Paragraph(
            f"n pareado = {mc['n_pareado']} &middot; {tb['pn'] + tb['np']} discordância(s) "
            f"({tb['pn']} HPJ+/Willis−, {tb['np']} HPJ−/Willis+) &middot; {metodo_label} "
            f"&middot; <b>p-valor = {mc['p_valor']:.4f}</b>.",
            styles["body"],
        ))

    # ---- efeito n coletas ----
    story.append(Paragraph("Efeito do número de potes de fezes entregues", styles["h2"]))
    story.append(Paragraph(
        "Baseado apenas em positividade fecal. Compara subgrupos diferentes de crianças — pode "
        "ter viés de seleção; ver curva cumulativa abaixo para uma leitura sem esse viés.",
        styles["small"],
    ))
    story.append(Spacer(1, 1.5 * mm))
    nc_img = _chart_ncoletas(metrics["efeito_n_coletas"])
    if nc_img:
        story.append(nc_img)

    ca = metrics["cochran_armitage_efeito_coletas"]
    if ca["p_valor"] is not None:
        story.append(Spacer(1, 1.5 * mm))
        story.append(Paragraph(
            f"Teste de tendência de Cochran-Armitage: Z = {ca['estatistica_z']:.3f}, "
            f"p-valor = {ca['p_valor']:.4f} ({ca['n_grupos']} grupos). {ca['aviso']}",
            styles["small"],
        ))

    # ---- curva cumulativa ----
    if not metrics["fecal_cumulativa"].empty:
        story.append(Paragraph("Ganho marginal por amostra — curva cumulativa", styles["h2"]))
        n_grupo = int(metrics["fecal_cumulativa"]["n_pacientes"].iloc[0])
        story.append(Paragraph(
            f"Mesmo grupo de {n_grupo} paciente(s) que entregou o número máximo de potes "
            "observado no estudo, medida repetida (1ª, 1ª+2ª ... coletas). Sem viés de comparar "
            "subgrupos diferentes de crianças.",
            styles["small"],
        ))
        story.append(Spacer(1, 1.5 * mm))
        cum_img = _chart_cumulativa(metrics["fecal_cumulativa"])
        if cum_img:
            story.append(cum_img)

    # ---- base por criança ----
    story.append(Paragraph("Base por paciente", styles["h2"]))
    story.append(Paragraph(
        "Tabela completa disponível no arquivo Excel exportado junto com este PDF; abaixo, uma "
        "amostra das primeiras linhas.",
        styles["body"],
    ))
    story.append(Spacer(1, 2 * mm))
    child_cols = ["id_paciente", "nome_paciente", "categoria_amostragem", "especies_str"]
    child_df = metrics["por_paciente"][child_cols].sort_values("id_paciente").rename(columns={
        "id_paciente": "ID", "nome_paciente": "Nome", "categoria_amostragem": "Amostragem", "especies_str": "Espécies",
    })
    story.append(_df_table(child_df, col_widths=[22 * mm, 42 * mm, 42 * mm, 54 * mm], max_rows=30))
    if len(child_df) > 30:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            f"… e mais {len(child_df) - 30} pacientes. Veja a lista completa no Excel exportado.",
            styles["small"],
        ))

    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", thickness=0.8, color=LINE))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "Nota metodológica: a prevalência é calculada por paciente, não por exame — uma criança conta "
        "como positiva se qualquer uma de suas coletas (P1, P2, ... Pn) revelou o parasita. O pote de "
        "fezes alimenta os métodos de domínio fecal; a lâmina alimenta exclusivamente os métodos de "
        "domínio lâmina/swab. Pacientes cujos únicos resultados foram \"Amostra insuficiente\" são "
        "reportadas à parte como inconclusivas e não entram nos denominadores de prevalência. Uma "
        "coluna de método marcada como \"Não realizado\" numa coleta específica é excluída inteiramente "
        "do denominador daquele método nessa coleta — não conta como positiva, negativa nem "
        "inconclusiva. Esta planilha trouxe os seguintes métodos: "
        f"{', '.join(metodos_ativos_nomes) if metodos_ativos_nomes else '—'}.",
        styles["small"],
    ))

    doc.build(story)
    return buf.getvalue()
