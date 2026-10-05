"""
Pirajá · Entero
Plataforma de análise epidemiológica de exames parasitológicos —
módulo de parasitos intestinais (exames de fezes e lâmina/fita adesiva).

Rodar localmente:
    pip install -r requirements.txt
    streamlit run app.py
"""
import hashlib
import io
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analysis_engine import (
    CATEGORIAS_VALIDAS,
    CRITERIOS_PADRAO,
    TODAS,
    METHOD_CATALOG,
    PARASITE_MAP,
    PATOGENICOS,
    COMENSAIS,
    REQUIRED_COLUMNS,
    coletas_duplicadas,
    criterios_ativos,
    coletas_nao_reconhecidas,
    compute_metrics,
    norm_text,
    normalize_columns,
    validate_columns,
)
from analysis_config import (
    AMOSTRAS_VALIDAS,
    CONFIG_SHEETS,
    abas_config_modelo,
    atualizar_contagens,
    config_xlsx_bytes,
    construir_config,
    detectar_colunas_metodo,
    ler_config_da_planilha,
    montar_tabelas_iniciais,
    planilha_com_config_bytes,
)
from report_pdf import _agora, build_pdf_report
from estilo_planilha import estilizar_modelo, estilizar_relatorio
import mapas

APP_DIR = Path(__file__).parent

# ----------------------------------------------------------------
# Identidade visual Pirajá — paleta "Mata, barro e papel"
# ----------------------------------------------------------------
BRAND_DIR = APP_DIR / "brand"
LOGO_PDF_PATH = BRAND_DIR / "piraja-entero-cor.png"        # cabeçalho do PDF
FAVICON_PATH = BRAND_DIR / "piraja-favicon.png"             # ícone da aba do navegador
LOGO_SIDEBAR_SVG = BRAND_DIR / "piraja-entero-negativo.svg" # sidebar (fundo verde-mata)

MATA = "#11483D"          # verde-mata — principal
FOLHA = "#328567"         # verde-folha — secundária
COBRE = "#9C4A2F"         # cobre — acento do módulo Entero
COBRE_CLARO = "#D08A6A"   # cobre claro — acento sobre fundo escuro
PAPEL = "#F4F1EA"         # papel — fundos
TINTA = "#1B2421"         # tinta — texto corrido

BG = PAPEL
SURFACE = "#FBF9F4"
INK = TINTA
INK_SOFT = "#4E5B55"
INK_FAINT = "#7A857F"
TEAL = FOLHA
TEAL_DARK = MATA
TEAL_TINT = "#E3EEE8"
BRICK = COBRE
BRICK_TINT = "#F3E4DB"
SAGE = "#A9C3B8"          # neutro esverdeado (categorias sem classificação)
LINE = "#DCD6C8"
MATA_DOT = "#1F6150"      # pontos do padrão "Campo" sobre verde-mata


def _svg_data_uri(path):
    import base64
    try:
        return "data:image/svg+xml;base64," + base64.b64encode(Path(path).read_bytes()).decode()
    except OSError:
        return ""


LOGO_SIDEBAR_URI = _svg_data_uri(LOGO_SIDEBAR_SVG)

st.set_page_config(
    page_title="Pirajá · Painel de análise epidemiológica",
    page_icon=str(FAVICON_PATH) if FAVICON_PATH.exists() else "🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------------------------------------------
# CSS de marca
# ----------------------------------------------------------------
st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Instrument+Sans:wght@400;500;600;700&display=swap');

    html, body, [class*="css"]  {{
        font-family: 'Instrument Sans', sans-serif;
        color: {INK};
    }}
    .stApp {{
        background-color: {BG};
    }}
    h1, h2, h3 {{
        font-family: 'Fraunces', serif !important;
        color: {TEAL_DARK} !important;
    }}
    /* ----- reforço de contraste: TODO texto renderizado pelo Streamlit -----
       O Streamlit pode aplicar automaticamente um tema escuro conforme a
       preferência do sistema operacional/navegador do usuário. Nesse caso a
       cor de texto herdada da regra genérica acima (html, body, [class*="css"])
       pode ser sobrescrita por um texto claro, enquanto os fundos abaixo
       continuam claros (fixados manualmente) — resultando em texto invisível.

       Por isso as regras abaixo miram diretamente os contêineres que o
       Streamlit usa para QUALQUER texto (st.write, st.markdown, st.caption). */
    [data-testid="stMarkdownContainer"],
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] span,
    [data-testid="stMarkdownContainer"] small,
    [data-testid="stMarkdownContainer"] strong,
    [data-testid="stMarkdownContainer"] em,
    [data-testid="stMarkdownContainer"] u,
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p,
    [data-testid="stCaptionContainer"] small,
    [data-testid="stText"] {{
        color: {INK_SOFT} !important;
    }}
    [data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"], [data-testid="stText"],
    [data-testid="stWidgetLabel"], [data-testid="stFileUploader"], [data-testid="stDataFrame"],
    [data-testid="stAlert"], [data-testid="stExpander"] summary {{
        font-family: 'Instrument Sans', sans-serif;
    }}
    [data-testid="stMarkdownContainer"] h1,
    [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3,
    [data-testid="stMarkdownContainer"] h4 {{
        color: {TEAL_DARK} !important;
    }}
    /* elementos de marca com cor própria (sobrescrevem a regra genérica acima
       por especificidade/ordem — mantidos explicitamente) */
    .pj-card p, .pj-note {{
        color: {INK_SOFT} !important;
    }}
    .pj-topbar .name, .pj-section-title, .pj-section-subtitle,
    .pj-step .step-title {{
        color: {TEAL_DARK} !important;
    }}
    .pj-section-caption, .pj-topbar .sub, .pj-card .kicker {{
        color: {INK_FAINT} !important;
    }}
    /* ----- eyebrow / section labels ----- */
    .pj-eyebrow {{
        font-family: 'Instrument Sans', sans-serif;
        font-weight: 600;
        font-size: 12px;
        letter-spacing: .14em;
        text-transform: uppercase;
        color: {BRICK} !important;
    }}

    /* ----- top brand bar ----- */
    .pj-topbar {{
        display:flex; align-items:baseline; justify-content:space-between; gap:14px;
        padding: 4px 0 16px 0;
        border-bottom: 1px solid {LINE};
        margin-bottom: 22px;
    }}
    .pj-topbar .name {{
        font-family:'Fraunces', serif; font-weight:600; font-size: 22px; color:{TEAL_DARK};
        line-height:1.15;
    }}
    .pj-topbar .sub {{
        font-family:'Instrument Sans', sans-serif; font-weight:600; font-size:11.5px;
        letter-spacing:.14em; color:{INK_FAINT}; text-transform:uppercase;
    }}

    /* ----- hero (verde-mata + padrão "Campo") ----- */
    .pj-hero {{
        position: relative; overflow: hidden;
        background: {MATA};
        border-radius: 14px;
        padding: 36px 40px;
        margin-bottom: 22px;
    }}
    .pj-hero::before {{
        content: ""; position: absolute; inset: 0; pointer-events: none;
        background-image: radial-gradient(circle, {MATA_DOT} 3.2px, transparent 3.8px);
        background-size: 26px 26px;
        background-position: 13px 13px;
        -webkit-mask-image: linear-gradient(to left, #000 15%, transparent 70%);
                mask-image: linear-gradient(to left, #000 15%, transparent 70%);
    }}
    .pj-hero .pj-hero-cluster {{
        position: absolute; right: 34px; top: 26px; width: 120px; height: 90px; pointer-events: none;
    }}
    .pj-hero > *:not(.pj-hero-cluster) {{ position: relative; }}
    [data-testid="stMarkdownContainer"] .pj-hero .pj-eyebrow {{ color: {COBRE_CLARO} !important; }}
    [data-testid="stMarkdownContainer"] .pj-hero h2 * {{ color: {PAPEL} !important; }}
    [data-testid="stMarkdownContainer"] .pj-hero h2 {{
        color: {PAPEL} !important;
        margin: 6px 0 12px 0 !important;
        font-size: 32px !important; font-weight: 500 !important; line-height: 1.15 !important;
        max-width: 760px;
    }}
    [data-testid="stMarkdownContainer"] .pj-hero p {{
        color: rgba(244, 241, 234, .82) !important;
        font-size: 15.5px; max-width: 720px; margin-bottom: 0; line-height: 1.6;
    }}

    /* ----- generic section card ----- */
    .pj-card {{
        background: {SURFACE};
        border: 1px solid {LINE};
        border-radius: 14px;
        padding: 18px 20px;
        height: 100%;
    }}
    .pj-card .kicker {{
        font-family:'Instrument Sans', sans-serif; font-weight:600; font-size: 11.5px; letter-spacing:.12em;
        text-transform:uppercase; color:{INK_FAINT} !important; margin-bottom: 10px; display:block;
    }}

    /* ----- step header (numbered badge + title) ----- */
    .pj-step {{
        display:flex; align-items:center; gap:12px; margin: 6px 0 2px 0;
    }}
    .pj-step .badge {{
        flex: 0 0 auto;
        width: 34px; height: 34px; border-radius: 50%;
        background: {TEAL_DARK}; color: {PAPEL} !important;
        font-family:'Fraunces', serif; font-weight:600; font-size: 16px;
        display:flex; align-items:center; justify-content:center;
    }}
    .pj-step .step-title {{
        font-family:'Fraunces', serif; font-weight:600; color:{TEAL_DARK}; font-size: 22px;
    }}
    /* Cartão de cada passo: cada passo é um st.container(key="pj-step-N"), que
       o Streamlit marca com a classe st-key-pj-step-N; o estilo mira essa classe
       (uma <div> aberta e fechada em st.markdown separados não envolveria nada). */
    div[class*="st-key-pj-step"] {{
        background:{SURFACE}; border:1px solid {LINE}; border-radius:14px;
        padding: 22px 24px 24px 24px; margin-bottom: 18px;
    }}

    /* ----- metrics ----- */
    div[data-testid="stMetric"] {{
        background: {SURFACE};
        border: 1px solid {LINE};
        padding: 16px 18px;
        border-radius: 12px;
    }}
    div[data-testid="stMetric"] label {{
        font-family: 'Instrument Sans', sans-serif !important;
        font-weight: 600;
        text-transform: uppercase;
        font-size: 11px !important;
        letter-spacing: .1em;
        color: {INK_FAINT} !important;
    }}
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{
        font-family: 'Fraunces', serif !important;
        font-weight: 600;
        color: {TEAL_DARK} !important;
    }}

    /* ----- buttons -----
       Reforço extra aqui: o texto do botão passa por [data-testid="stMarkdownContainer"]
       internamente (mesmo elemento usado pelo texto solto da página), então sem uma
       regra MAIS específica que essa, ele herdaria a cor escura das regras genéricas
       acima e ficaria quase invisível sobre o fundo verde-escuro do botão. As regras
       abaixo miram o texto e o ícone do botão diretamente, com prioridade máxima. */
    .stDownloadButton button, .stButton button, .stFormSubmitButton button {{
        background-color: {TEAL_DARK};
        color: {PAPEL} !important;
        border: 1px solid {TEAL_DARK};
        font-family: 'Instrument Sans', sans-serif;
        font-weight: 600;
        border-radius: 8px;
        font-size: 13.5px;
    }}
    .stFormSubmitButton button p, .stFormSubmitButton button span,
    .stDownloadButton button p, .stButton button p,
    .stDownloadButton button span, .stButton button span,
    .stDownloadButton button div, .stButton button div,
    .stDownloadButton button [data-testid="stMarkdownContainer"],
    .stDownloadButton button [data-testid="stMarkdownContainer"] p,
    .stButton button [data-testid="stMarkdownContainer"],
    .stButton button [data-testid="stMarkdownContainer"] p {{
        color: {PAPEL} !important;
    }}
    .stDownloadButton button svg, .stButton button svg {{
        fill: {PAPEL} !important;
        color: {PAPEL} !important;
    }}
    .stDownloadButton button:hover, .stButton button:hover, .stFormSubmitButton button:hover {{
        background-color: {TEAL};
        border-color: {TEAL};
        color: {PAPEL} !important;
    }}
    .stFormSubmitButton button:hover p, .stFormSubmitButton button:hover span,
    .stDownloadButton button:hover p, .stButton button:hover p,
    .stDownloadButton button:hover span, .stButton button:hover span,
    .stDownloadButton button:hover [data-testid="stMarkdownContainer"] p,
    .stButton button:hover [data-testid="stMarkdownContainer"] p {{
        color: {PAPEL} !important;
    }}

    /* ----- tags ----- */
    .pj-tag {{
        display:inline-block; font-family:'Instrument Sans', sans-serif; font-weight:500; font-size:12.5px;
        padding:3px 11px; margin:2px; border-radius:999px; border:1px solid;
    }}

    /* ----- notes ----- */
    .pj-note {{
        background: {BRICK_TINT}; border-left: 3px solid {BRICK};
        padding: 12px 16px; font-size: 14px; color: {INK_SOFT} !important; border-radius: 6px;
    }}

    /* ----- section title inside report ----- */
    .pj-section-title {{
        font-family:'Fraunces', serif; font-weight:600; color:{TEAL_DARK};
        font-size: 20px; margin: 2px 0 2px 0;
    }}
    .pj-section-subtitle {{
        font-family:'Fraunces', serif; font-weight:600; color:{TEAL_DARK};
        font-size: 16px; margin: 2px 0 2px 0;
    }}
    .pj-section-caption {{
        color:{INK_FAINT} !important; font-size: 12.5px; margin-bottom: 10px;
    }}

    /* ----- tabs (sectorized report) ----- */
    .stTabs [data-baseweb="tab-list"], .stTabs [role="tablist"] {{
        gap: 4px;
        border-bottom: 1px solid {LINE};
    }}
    .stTabs [data-baseweb="tab"], .stTabs [role="tab"] {{
        font-family: 'Instrument Sans', sans-serif;
        font-weight: 600;
        font-size: 14px;
        color: {INK_FAINT} !important;
        padding: 10px 14px;
    }}
    .stTabs [role="tab"] p {{ font-family: 'Instrument Sans', sans-serif; font-weight: 600; }}
    .stTabs [aria-selected="true"] {{
        color: {TEAL_DARK} !important;
        border-bottom: 2px solid {BRICK} !important;
    }}
    .stTabs [data-baseweb="tab-highlight"] {{ background-color: {BRICK} !important; }}

    hr {{ border-color: {LINE}; }}

    /* ----- sidebar (verde-mata, assinatura em negativo) ----- */
    section[data-testid="stSidebar"] {{
        background-color: {MATA};
        border-right: none;
    }}
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] li,
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span,
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] em,
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{
        color: rgba(244, 241, 234, .78) !important;
    }}
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] strong,
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] strong {{
        color: {PAPEL} !important;
    }}
    section[data-testid="stSidebar"] .pj-eyebrow {{ color: {COBRE_CLARO} !important; }}
    section[data-testid="stSidebar"] hr {{ border-color: rgba(244, 241, 234, .16) !important; }}
    section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] *,
    section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] button * {{
        color: {PAPEL} !important; fill: {PAPEL} !important;
    }}
    section[data-testid="stSidebar"] .stDownloadButton button {{
        background-color: {PAPEL}; border-color: {PAPEL};
    }}
    section[data-testid="stSidebar"] .stDownloadButton button p,
    section[data-testid="stSidebar"] .stDownloadButton button span,
    section[data-testid="stSidebar"] .stDownloadButton button div,
    section[data-testid="stSidebar"] .stDownloadButton button [data-testid="stMarkdownContainer"] p {{
        color: {MATA} !important;
    }}
    section[data-testid="stSidebar"] .stDownloadButton button:hover {{
        background-color: {COBRE_CLARO}; border-color: {COBRE_CLARO};
    }}
    section[data-testid="stSidebar"] .stDownloadButton button:hover p {{
        color: {TINTA} !important;
    }}
    .pj-sidebar-brand {{ padding: 2px 0 6px 0; }}
    .pj-sidebar-brand img {{ width: 172px; height: auto; display: block; }}
    </style>
    """,
    unsafe_allow_html=True,
)

CHART_COLORWAY = [TEAL_DARK, TEAL, BRICK, COBRE_CLARO, SAGE, INK_FAINT]
# Cores por categoria clínica: patogênico em cobre (o "positivo" da marca),
# comensal em verde-folha, não classificado em neutro esverdeado.
CAT_COLORS = CATEGORIA_CORES = {"Patogênico": BRICK, "Comensal": TEAL, "Não classificado": SAGE}
PLOTLY_LAYOUT = dict(
    font_family="Instrument Sans, sans-serif",
    font_color=INK_SOFT,
    plot_bgcolor=SURFACE,
    paper_bgcolor=SURFACE,
    colorway=CHART_COLORWAY,
    margin=dict(t=20, b=20, l=10, r=10),
)


def section_title(text, caption=None):
    st.markdown(f'<div class="pj-section-title">{text}</div>', unsafe_allow_html=True)
    if caption:
        st.markdown(f'<div class="pj-section-caption">{caption}</div>', unsafe_allow_html=True)


def subsection_title(text, caption=None):
    st.markdown(f'<div class="pj-section-subtitle">{text}</div>', unsafe_allow_html=True)
    if caption:
        st.markdown(f'<div class="pj-section-caption">{caption}</div>', unsafe_allow_html=True)


def step_header(number, title):
    st.markdown(
        f"""<div class="pj-step">
        <div class="badge">{number}</div>
        <div class="step-title">{title}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def format_ic(inf, sup):
    """Formata um par (limite_inferior, limite_superior) de IC95% para exibição.
    Retorna um texto neutro quando o intervalo não pôde ser calculado (n=0)."""
    if inf is None or sup is None:
        return "IC95% não calculável (n=0)"
    return f"IC95%: {inf:.1f}–{sup:.1f}%"


def prev_valor(prev, n):
    """Prevalência para exibição: '—' quando não há nenhum paciente conclusivo
    no denominador (0,0% daria a entender que houve exame e deu negativo)."""
    return f"{prev:.1f}%" if n else "—"


def prev_legenda(inf, sup, n, tem_metodo, dominio):
    """Legenda sob a métrica: IC95% quando há base; senão explica por que o
    domínio não foi avaliado."""
    if not tem_metodo:
        return f"Não avaliado — nenhum método de {dominio} nesta planilha."
    if not n:
        return "Não avaliado — nenhum resultado conclusivo."
    return format_ic(inf, sup)


def with_ic_column(df: pd.DataFrame, prev_col="prevalencia", inf_col="ic95_inf", sup_col="ic95_sup",
                    label="IC 95%") -> pd.DataFrame:
    """Devolve uma cópia do DataFrame com uma coluna extra combinando o IC95% num
    único texto legível ('11.0 – 42.1%'), para exibir ao lado da prevalência sem
    poluir a tabela com duas colunas numéricas soltas."""
    out = df.copy()
    if inf_col in out.columns and sup_col in out.columns:
        out[label] = out.apply(
            lambda r: f"{r[inf_col]:.1f} – {r[sup_col]:.1f}%" if pd.notna(r[inf_col]) and pd.notna(r[sup_col]) else "—",
            axis=1,
        )
        out = out.drop(columns=[inf_col, sup_col])
    return out




def grafico_especies(esp_df: pd.DataFrame, somente_patogenicos: bool, vazio_msg: str, key: str):
    """Barras horizontais de prevalência por espécie. Com somente_patogenicos,
    mostra só as espécies classificadas como patogênicas na configuração."""
    d = esp_df
    if not d.empty and somente_patogenicos:
        d = d[d["categoria"] == "Patogênico"]
    if d.empty:
        st.info(vazio_msg)
        return
    d = d.sort_values("prevalencia").copy()
    d["rotulo"] = d["prevalencia"].map(lambda v: f"{v:.1f}%")
    d["IC 95%"] = [
        f"{i:.1f}–{s:.1f}%" if pd.notna(i) and pd.notna(s) else "—"
        for i, s in zip(d.get("ic95_inf", [None] * len(d)), d.get("ic95_sup", [None] * len(d)))
    ]
    fig = px.bar(
        d, x="prevalencia", y="especie", orientation="h", color="categoria",
        color_discrete_map=CAT_COLORS, text="rotulo",
        labels={"prevalencia": "Prevalência (%)", "especie": "", "categoria": ""},
        hover_data={"n": True, "IC 95%": True, "rotulo": False},
    )
    vmax = float(d["prevalencia"].max())
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(
        **PLOTLY_LAYOUT, height=max(220, 36 * len(d) + 90), showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=""),
    )
    fig.update_xaxes(range=[0, max(10.0, min(115.0, vmax * 1.3))])
    fig.update_yaxes(categoryorder="total ascending")
    st.plotly_chart(fig, width="stretch", key=key)


def bloco_dominio(titulo, caption, esp_df, n_base, n_pos, prev, ic, n_pat, prev_pat, ic_pat, tem_metodo, key):
    """Seção de um tipo de amostra (fezes OU lâmina): positividade geral e só de
    patogênicos, gráfico com todos os parasitos e gráfico só com patogênicos."""
    section_title(titulo, caption)
    if not tem_metodo:
        st.info("Nenhum método deste tipo de amostra foi incluído na análise (veja o passo 03).")
        return
    if not n_base:
        st.info("Nenhum paciente com resultado conclusivo neste tipo de amostra.")
        return
    m1, m2 = st.columns(2)
    with m1:
        st.metric("Positividade — todos os parasitos", prev_valor(prev, n_base))
        st.caption(f"{n_pos} de {n_base} pacientes · {format_ic(*ic)}")
    with m2:
        st.metric("Positividade — somente patogênicos", prev_valor(prev_pat, n_base))
        st.caption(f"{n_pat} de {n_base} pacientes · {format_ic(*ic_pat)}")
    g1, g2 = st.columns(2)
    with g1:
        subsection_title("Todos os parasitos")
        grafico_especies(esp_df, False, "Nenhum parasito detectado.", key=f"{key}-todos")
    with g2:
        subsection_title("Somente patogênicos")
        grafico_especies(esp_df, True, "Nenhum parasito patogênico detectado.", key=f"{key}-pat")
    with st.expander("Tabela por espécie com IC95% (Wilson)"):
        tab = with_ic_column(esp_df).rename(columns={
            "especie": "Espécie", "n": "N", "prevalencia": "Prevalência %", "categoria": "Categoria",
        })
        st.dataframe(tab, width="stretch", hide_index=True)


@st.cache_data(show_spinner=False)
def _ler_limites_cache(conteudo: bytes, nome: str):
    return mapas.ler_limites(conteudo, nome)


def painel_mapa(metrics: dict):
    """Controles e saída do mapa opcional (seção Território da Visão geral)."""
    c1, c2, c3 = st.columns(3)
    with c1:
        nivel = st.radio("Nível", ["Município", "Bairro"], horizontal=True, key="mapa_nivel")
    with c2:
        indicador = st.radio("Indicador", ["Todos os parasitos", "Somente patogênicos"], horizontal=True,
                             key="mapa_ind")
    with c3:
        modo = st.radio("Classes de prevalência", ["Automáticas", "Fixas"], horizontal=True, key="mapa_cls",
                        help="Automáticas: 5 faixas de 5 em 5 pontos (ou mais largas) a partir dos dados. "
                             "Fixas: <10, 10–20, 20–40, 40–60, ≥60% — use para comparar estudos.")
    limites, col_nome, foco = None, None, None
    if nivel == "Bairro":
        cidades = mapas.municipios_com_bairro(metrics)
        if len(cidades) > 1:
            foco = st.selectbox(
                "Município do mapa de bairros", cidades, key="mapa_foco",
                help="O mapa por bairro mostra uma cidade por vez (em ordem de nº de pacientes).",
            )
        elif cidades:
            foco = cidades[0]
    if nivel == "Bairro":
        fonte_b = st.radio(
            "Limites dos bairros", ["Malha de bairros do IBGE (Censo 2022)", "Arquivo próprio (ex.: prefeitura)"],
            horizontal=True, key="mapa_fonte_bairros",
            help="A malha do IBGE só tem bairros nos municípios com divisão oficial em bairros. Se o seu "
                 "município não tiver, ou se preferir os limites da prefeitura, envie um arquivo próprio.",
        )
    if nivel == "Bairro" and fonte_b.startswith("Arquivo"):
        st.caption(
            "Envie os limites dos bairros em GeoJSON, ou shapefile compactado em .zip (com os arquivos .shp, "
            ".shx, .dbf e .prj). Qualquer sistema de coordenadas — o painel converte para SIRGAS 2000."
        )
        arq = st.file_uploader("Arquivo de limites dos bairros", type=["geojson", "json", "zip"], key="mapa_lim")
        if arq is None:
            st.info("Envie o arquivo de limites dos bairros para gerar este mapa.")
            st.session_state.pop("mapa_pdf", None)
            return
        try:
            limites, cols = _ler_limites_cache(arq.getvalue(), arq.name)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Não consegui ler esse arquivo de limites ({exc}).")
            st.session_state.pop("mapa_pdf", None)
            return
        if not cols:
            st.error("O arquivo de limites não tem nenhuma coluna de texto com o nome do bairro.")
            return
        sug = mapas.coluna_nome_provavel(cols)
        col_nome = st.selectbox("Coluna com o nome do bairro no arquivo", cols,
                                index=cols.index(sug) if sug in cols else 0, key="mapa_colnome")
    if nivel == "Município":
        n_areas = len(metrics["territorio_municipio"])
    else:
        tb_ = metrics["territorio_bairro"]
        n_areas = int((tb_["municipio"].astype(str) + "/" + tb_["uf"].astype(str).str.upper()).eq(foco or "").sum()) \
            if foco else len(tb_)
    rot = st.checkbox("Mostrar nome e valor dentro das áreas", value=n_areas <= 15, key=f"mapa_rot_{nivel}",
                      help="Com muitas áreas pequenas os rótulos se sobrepõem; os valores continuam ao "
                           "passar o mouse no mapa interativo.")

    with st.spinner("Desenhando o mapa…"):
        try:
            r = mapas.preparar_mapa(
                metrics, "municipio" if nivel == "Município" else "bairro",
                "todos" if indicador == "Todos os parasitos" else "patogenicos",
                modo_classes="fixas" if modo == "Fixas" else "auto",
                limites=limites, col_nome=col_nome, mostrar_rotulos=rot, municipio_foco=foco,
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Não foi possível gerar o mapa ({exc}).")
            st.session_state.pop("mapa_pdf", None)
            return
    for a in r.get("avisos", []):
        st.warning(a)
    if not r["ok"]:
        st.info(r["erro"])
        st.session_state.pop("mapa_pdf", None)
        return
    st.plotly_chart(r["fig_interativa"], width="stretch", key="mapa_plot",
                    config={"displaylogo": False, "scrollZoom": True})
    png = mapas.figura_bytes(r["fig_estatica"], "png", 300)
    tif = mapas.figura_bytes(r["fig_estatica"], "tiff", 300)
    mapas.plt.close(r["fig_estatica"])
    st.session_state["mapa_pdf"] = (r["titulo"], png)
    st.caption("Figura para artigo (300 dpi), com rosa dos ventos, escala, grade de coordenadas, mapa de "
               "localização, legenda e fonte. Ela também entra no relatório em PDF.")
    with st.expander("Ver a figura para artigo"):
        st.image(png, width="stretch")
    d1, d2 = st.columns(2)
    nome_base = "mapa_prevalencia_" + ("municipio" if nivel == "Município" else "bairro")
    with d1:
        st.download_button("⬇ Figura PNG (300 dpi)", data=png, file_name=f"{nome_base}.png", mime="image/png",
                           width="stretch")
    with d2:
        st.download_button("⬇ Figura TIFF (300 dpi)", data=tif, file_name=f"{nome_base}.tiff", mime="image/tiff",
                           width="stretch")


# colunas da planilha que nunca são método (não aparecem como opção no passo 03)
COLUNAS_NAO_METODO = set(REQUIRED_COLUMNS) | {
    "nome_crianca", "nome_responsavel", "status_amostra", "status_lamina", "observacoes", "observacao",
    "bairro", "municipio", "uf",
}


def passo_configuracao(df: pd.DataFrame, file_bytes: bytes, file_name: str, cfg_planilha: dict, file_id: str):
    """Passo 03 — configuração híbrida. Pré-preenchida pelas abas Config_* da
    planilha (se houver) ou pelo que foi detectado nos resultados; editável no
    site; exportável para reaproveitar. Devolve (AnalysisConfig, avisos)."""
    ss = st.session_state
    if ss.get("cfg_file_id") != file_id:
        par, met, n, mx, avisos = montar_tabelas_iniciais(df, cfg_planilha)
        ss["cfg_file_id"] = file_id
        ss["cfg_par"], ss["cfg_met"], ss["cfg_n"], ss["cfg_max"] = par, met, n, mx
        ss["cfg_avisos"] = avisos
        ss["cfg_crit"] = {**CRITERIOS_PADRAO, **cfg_planilha.get("criterios", {})}
        ss["cfg_origem"] = sorted(cfg_planilha.keys())
        ss["cfg_ver"] = ss.get("cfg_ver", 0) + 1
    ver = ss["cfg_ver"]

    with st.container(key="pj-step-3"):
        step_header(3, "Configure a análise")
        if ss["cfg_origem"]:
            partes = {"parasitos": "parasitos", "metodos": "métodos", "n_amostras": "nº de amostras",
                      "criterios": "critérios de inclusão"}
            st.success(
                "Configuração lida da própria planilha ("
                + ", ".join(partes[k] for k in ss["cfg_origem"])
                + "). Revise abaixo; se mudar algo, clique em **Aplicar**."
            )
        else:
            st.info(
                "Esta planilha não tem abas de configuração, então a lista abaixo foi montada com o "
                "que aparece nos resultados. Marque os parasitos e métodos que entram na análise, "
                "classifique cada parasito e defina a quantidade de amostras. Depois, baixe a "
                "configuração para não precisar repetir."
            )
        for a in ss.get("cfg_avisos", []):
            st.warning(a)

        with st.form(f"pj-cfg-{ver}", border=False):
            t_par, t_met, t_amo, t_cri = st.tabs(
                ["🦠  Parasitos", "🔬  Métodos", "🧪  Amostras", "✅  Critérios de inclusão"]
            )
            with t_par:
                st.caption(
                    "Desmarque **Incluir** para deixar um parasito fora da análise (uma amostra que só "
                    "tinha parasitos excluídos passa a contar como negativa). A **Classificação** "
                    "define o que entra nos gráficos de patogênicos. Use **Agrupar como** para juntar "
                    "nomes diferentes da mesma espécie — escreva o nome final nas linhas a juntar."
                )
                ed_par = st.data_editor(
                    ss["cfg_par"], key=f"ed-par-{ver}", hide_index=True, width="stretch", num_rows="fixed",
                    column_config={
                        "Incluir": st.column_config.CheckboxColumn("Incluir", default=True),
                        "Parasito": st.column_config.TextColumn("Parasito", disabled=True),
                        "Classificação": st.column_config.SelectboxColumn(
                            "Classificação", options=list(CATEGORIAS_VALIDAS), required=True),
                        "Agrupar como": st.column_config.TextColumn(
                            "Agrupar como", help="Opcional. Nome final da espécie no relatório."),
                        "Encontrado em": st.column_config.TextColumn("Encontrado em", disabled=True),
                        "Ocorrências": st.column_config.NumberColumn(
                            "Ocorrências", disabled=True, help="Nº de células de resultado com esse parasito."),
                    },
                )
            with t_met:
                st.caption(
                    "Marque os métodos que entram na análise e indique o tipo de amostra: métodos de "
                    "**Fezes** e de **Lâmina (Graham)** são sempre analisados separadamente. Para usar "
                    "um método fora do catálogo, adicione uma linha e escolha a coluna da planilha."
                )
                opcoes_col = [c for c in df.columns if c not in COLUNAS_NAO_METODO]
                ed_met = st.data_editor(
                    ss["cfg_met"], key=f"ed-met-{ver}", hide_index=True, width="stretch", num_rows="dynamic",
                    column_config={
                        "Incluir": st.column_config.CheckboxColumn("Incluir", default=True),
                        "Coluna": st.column_config.SelectboxColumn(
                            "Coluna na planilha", options=opcoes_col, required=True),
                        "Método": st.column_config.TextColumn("Nome do método", required=True),
                        "Amostra": st.column_config.SelectboxColumn(
                            "Tipo de amostra", options=list(AMOSTRAS_VALIDAS), required=True,
                            default=AMOSTRAS_VALIDAS[0]),
                    },
                )
            with t_amo:
                mx = int(ss["cfg_max"] or 0)
                limite = max(mx, int(ss["cfg_n"]), 1)
                n_sel = st.number_input(
                    "Quantidade de amostras (coletas) por paciente", min_value=1, max_value=limite,
                    value=min(int(ss["cfg_n"]), limite), step=1,
                    help="Coletas P1..Pn consideradas. Coletas acima desse número são ignoradas.",
                )
                st.caption(
                    (f"A planilha tem coletas até **P{mx}**. " if mx else "Nenhum rótulo P1, P2... reconhecido. ")
                    + "Reduzir o número permite, por exemplo, ver o resultado com só 1 ou 2 amostras por paciente."
                )
            with t_cri:
                st.caption(
                    "Defina quais pacientes entram na análise. Quem não atender a algum critério fica "
                    "**fora de todas as contas** (numeradores e denominadores) e aparece no relatório na "
                    "lista de excluídos, com o motivo. Com tudo desligado, todos os pacientes entram."
                )
                crit = ss["cfg_crit"]
                n_ref = int(ss["cfg_n"])

                def _opcoes_min(n):
                    return [0] + list(range(1, n)) + [TODAS]

                def _rotulo_min(v, n=n_ref):
                    if v == 0:
                        return "Sem exigência"
                    if v == TODAS:
                        return f"Todas as coletas (P1–P{n})"
                    return f"Pelo menos {v}"

                def _valor_atual(v, n=n_ref):
                    if v == TODAS or v in _opcoes_min(n):
                        return v
                    return TODAS if v >= n else 0

                c_f, c_l = st.columns(2)
                with c_f:
                    sel_min_f = st.selectbox(
                        "Coletas com pote de fezes entregue", _opcoes_min(n_ref),
                        index=_opcoes_min(n_ref).index(_valor_atual(crit["min_fezes"])),
                        format_func=_rotulo_min, key=f"cri-f-{ver}",
                        help="Nº mínimo de coletas (P1..Pn) em que o paciente entregou o pote de fezes.",
                    )
                with c_l:
                    sel_min_l = st.selectbox(
                        "Coletas com lâmina entregue", _opcoes_min(n_ref),
                        index=_opcoes_min(n_ref).index(_valor_atual(crit["min_lamina"])),
                        format_func=_rotulo_min, key=f"cri-l-{ver}",
                        help="Nº mínimo de coletas (P1..Pn) em que o paciente entregou a lâmina.",
                    )
                sel_inc = st.checkbox(
                    "Excluir paciente com alguma amostra sem resultado",
                    value=bool(crit["excluir_inconclusivos"]), key=f"cri-inc-{ver}",
                    help="Amostra entregue com 'Amostra insuficiente' ou célula vazia em algum método incluído.",
                )
                sel_todos = st.checkbox(
                    "Excluir paciente com algum método não realizado",
                    value=bool(crit["exigir_todos_metodos"]), key=f"cri-met-{ver}",
                    help="Algum método incluído marcado 'Não realizado' em amostra entregue.",
                )
                st.caption(
                    "Exemplo: para considerar só quem entregou e teve analisadas **todas** as amostras, "
                    "escolha *Todas as coletas* para fezes (e lâmina, se for o caso) e marque as duas opções."
                    " A quantidade de coletas segue a aba **Amostras**."
                )
            aplicar = st.form_submit_button("Aplicar configuração e atualizar relatório", type="primary")

        if aplicar:
            met = ed_met.copy()
            met = met[met["Coluna"].notna() & (met["Coluna"].astype(str).str.strip() != "")]
            met["Incluir"] = met["Incluir"].fillna(True).astype(bool)
            met["Método"] = [m if isinstance(m, str) and m.strip() else c for m, c in zip(met["Método"], met["Coluna"])]
            met["Amostra"] = met["Amostra"].fillna(AMOSTRAS_VALIDAS[0])
            ss["cfg_met"] = met.reset_index(drop=True)
            par = ed_par.copy()
            par["Incluir"] = par["Incluir"].fillna(True).astype(bool)
            par["Agrupar como"] = par["Agrupar como"].fillna("")
            ss["cfg_par"] = atualizar_contagens(par, df, ss["cfg_met"])
            ss["cfg_n"] = int(n_sel)
            ss["cfg_crit"] = {
                "min_fezes": sel_min_f, "min_lamina": sel_min_l,
                "excluir_inconclusivos": bool(sel_inc), "exigir_todos_metodos": bool(sel_todos),
            }
            ss["cfg_avisos"] = []
            ss["cfg_ver"] = ver + 1
            st.rerun()

        cfg, avisos_cfg = construir_config(ss["cfg_par"], ss["cfg_met"], ss["cfg_n"], ss["cfg_crit"])
        for a in avisos_cfg:
            st.warning(a)

        fezes = [n for _, n, _, d in cfg.metodos if d == "fecal"]
        lamina = [n for _, n, _, d in cfg.metodos if d == "lamina"]
        n_pat = sum(1 for c in cfg.categorias.values() if c == "Patogênico")
        n_com = sum(1 for c in cfg.categorias.values() if c == "Comensal")
        st.caption(
            f"**Em uso:** {len(cfg.categorias)} parasito(s) — {n_pat} patogênico(s), {n_com} comensal(is)"
            + (f", {len(cfg.excluidos)} excluído(s)" if cfg.excluidos else "")
            + f" · fezes: {', '.join(fezes) or '—'} · lâmina: {', '.join(lamina) or '—'}"
            + f" · até P{cfg.n_amostras} por paciente"
            + (" · critérios de inclusão ligados." if criterios_ativos(cfg.criterios) else ".")
        )

        base_nome = Path(file_name).stem
        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "⬇ Baixar só a configuração (.xlsx)",
                data=config_xlsx_bytes(ss["cfg_par"], ss["cfg_met"], ss["cfg_n"], ss["cfg_crit"]),
                file_name=f"Configuracao_{base_nome}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
        with d2:
            st.download_button(
                "⬇ Baixar minha planilha com a configuração",
                data=planilha_com_config_bytes(file_bytes, ss["cfg_par"], ss["cfg_met"], ss["cfg_n"], ss["cfg_crit"]),
                file_name=f"{base_nome}_com_configuracao.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
                help="A mesma planilha enviada, com as abas Config_* anexadas. Da próxima vez, é só enviar este arquivo.",
            )
    st.write("")
    return cfg


# ----------------------------------------------------------------
# Modelo de planilha (bytes) — usado no Passo 01 e na sidebar
#
# O modelo traz colunas para TODOS os métodos do catálogo (METHOD_CATALOG),
# não só os quatro originais — mas isso é só o ponto de partida. Bianca (ou
# qualquer usuária) pode apagar as colunas de método que o laboratório não
# usa: a planilha enviada só precisa trazer os métodos que de fato foram
# empregados na coleta, e o sistema detecta sozinho quais estão presentes
# (ver get_active_methods / validate_columns em analysis_engine.py). Também
# é possível enviar uma planilha com métodos que nem estão no modelo — desde
# que a coluna siga o padrão 'metodo_<nome>' e a coluna de status do domínio
# certo (status_amostra / status_lamina) esteja presente — mas nesse caso é
# preciso adicionar o método ao METHOD_CATALOG no código para que ele seja
# reconhecido e entre nas análises.
# ----------------------------------------------------------------
def generate_template_bytes() -> bytes:
    metodo_cols_fecal = [col for col, _, _, dominio in METHOD_CATALOG if dominio == "fecal"]
    metodo_cols_lamina = [col for col, _, _, dominio in METHOD_CATALOG if dominio == "lamina"]

    headers = (
        ["id_paciente", "coleta", "nome_paciente", "nome_responsavel", "bairro", "municipio", "uf",
         "status_amostra", "status_lamina"]
        + metodo_cols_lamina
        + metodo_cols_fecal
        + ["observacoes"]
    )

    def _linha(id_paciente, coleta, status_amostra, status_lamina, valores_metodo, observacoes):
        row = {
            "id_paciente": id_paciente, "coleta": coleta, "nome_paciente": "Exemplo Da Silva",
            "nome_responsavel": "Nome Do Responsável",
            "bairro": "Lagoa Nova" if id_paciente == "F-001" else "Felipe Camarão",
            "municipio": "Natal", "uf": "RN", "status_amostra": status_amostra,
            "status_lamina": status_lamina, "observacoes": observacoes,
        }
        for col in metodo_cols_lamina + metodo_cols_fecal:
            row[col] = valores_metodo.get(col, "-")
        return [row[h] for h in headers]

    linha1 = _linha("F-001", "P1", "Entregue", "Entregue", {"metodo_hpj": "E. nana"}, "")
    linha2 = _linha("F-001", "P2", "Entregue", "Entregue",
                     {col: "Enterobius vermicularis" for col in metodo_cols_lamina}, "")
    linha3 = _linha("F-001", "P3", "Não entregue", "Entregue",
                     {col: "" for col in metodo_cols_fecal}, "amostra fecal não coletada")
    linha4 = _linha("F-002", "P1", "Entregue", "Entregue",
                     {"metodo_hpj": "E. nana + G. lamblia",
                      **{col: "Não realizado" for col in metodo_cols_lamina if col != "metodo_graham"}},
                     "poliparasitismo (2 espécies na mesma célula, separadas por '+')")

    example = pd.DataFrame([linha1, linha2, linha3, linha4], columns=headers)

    metodo_legenda = {
        "metodo_graham": "Resultado do Graham — Enterobius vermicularis, Taenia sp.",
        "metodo_hpj": "Resultado do HPJ (Hoffman, Pons e Janer / Lutz) — sedimentação espontânea.",
        "metodo_willis": "Resultado do Willis — flutuação espontânea, ovos leves (ancilostomídeos).",
        "metodo_baermann_picanco": "Resultado do Baermann-Picanço — larvas de Strongyloides.",
        "metodo_faust": "Resultado do Faust — centrífugo-flutuação, cistos/oocistos de protozoários.",
        "metodo_kato_katz": "Resultado do Kato-Katz — quantificação de ovos de helmintos.",
        "metodo_mifc": "Resultado do MIFC (Blagg) — sedimentação por centrifugação.",
        "metodo_ritchie": "Resultado do Ritchie (formol-éter) — sedimentação por centrifugação.",
    }
    valores_aceitos_metodo = (
        "'-' (negativo) · 'Amostra insuficiente' (tentou, mas não deu resultado) · "
        "'Não realizado' (esse método não foi feito nessa amostra — não entra em nenhuma conta) · "
        "ou espécie(s) reconhecida(s) (veja a aba 'Espécies reconhecidas'). Para poliparasitismo, "
        "escreva mais de uma espécie na MESMA célula separadas por ' + ' (ex.: 'E. nana + G. lamblia')."
    )
    legenda_rows = [
        ["id_paciente", "Código único do paciente (repete nas linhas de P1/P2/P3)", "texto livre, ex.: F-001"],
        ["coleta", "Qual coleta essa linha representa", "P1, P2, P3 ... (quantas o estudo tiver)"],
        ["nome_paciente", "Nome da criança", "texto livre"],
        ["nome_responsavel", "Nome do responsável (opcional)", "texto livre ou vazio"],
        ["bairro", "Bairro onde o paciente MORA (opcional — usado na prevalência por bairro e no mapa). "
                   "Só o nome do bairro, nunca o endereço. Em São Paulo/SP use o DISTRITO; no DF, a "
                   "REGIÃO ADMINISTRATIVA (com municipio = Brasília).", "texto, ex.: Lagoa Nova"],
        ["municipio", "Município onde o paciente mora (opcional, mas necessário para o bairro: há bairros "
                      "com o mesmo nome em cidades diferentes)", "texto, ex.: Natal"],
        ["uf", "Sigla do estado do município (opcional)", "RN, PB, PE..."],
        ["status_amostra", "Status de entrega do POTE DE FEZES — usado pelos métodos fecais abaixo", "Entregue / Não entregue"],
        ["status_lamina", "Status de entrega da LÂMINA — usado pelo(s) método(s) de lâmina abaixo", "Entregue / Não entregue"],
    ]
    for col, nome, _, dominio in METHOD_CATALOG:
        legenda_rows.append([
            col, metodo_legenda.get(col, f"Resultado do {nome}."), valores_aceitos_metodo,
        ])
    legenda_rows.append(["observacoes", "Observações livres (opcional)", "texto livre ou vazio"])
    legenda = pd.DataFrame(legenda_rows, columns=["Coluna", "O que é", "Valores aceitos"])

    # ----------------------------------------------------------------
    # Aba "Espécies reconhecidas" — lista, a partir do próprio PARASITE_MAP do
    # sistema (fonte única de verdade, sem duplicar a lista manualmente), o
    # nome padronizado de cada espécie, sua categoria clínica e todas as
    # grafias abreviadas aceitas. Uma espécie digitada fora dessas grafias
    # (e fora do nome completo) não é reconhecida como erro — ela ainda é
    # registrada no relatório, mas cai em "Não classificado" em vez de entrar
    # como Patogênico/Comensal, e pode aparecer como uma linha própria em vez
    # de ser agrupada com a grafia já cadastrada da mesma espécie.
    # ----------------------------------------------------------------
    variantes_por_especie = {}
    for chave, canonical in PARASITE_MAP.items():
        variantes_por_especie.setdefault(canonical, []).append(chave)

    especies_rows = []
    for especie in sorted(variantes_por_especie):
        variantes = sorted(set(variantes_por_especie[especie]), key=len)
        categoria = "Patogênico" if especie in PATOGENICOS else ("Comensal" if especie in COMENSAIS else "Não classificado")
        especies_rows.append([especie, categoria, ", ".join(variantes)])
    especies_reconhecidas = pd.DataFrame(
        especies_rows,
        columns=["Espécie (nome padronizado no relatório)", "Categoria clínica", "Grafias aceitas na célula (maiúsc./minúsc. tanto faz)"],
    )
    especies_nota = pd.DataFrame(
        [[
            "Maiúsculas/minúsculas não importam, e 'e.coli', 'e. coli' e 'e .coli' são todos "
            "reconhecidos como a mesma grafia. Uma espécie escrita de um jeito que NÃO está nesta "
            "lista (nem por extenso, nem abreviada como aqui) ainda é aceita e aparece no relatório, "
            "mas como 'Não classificado' — sem entrar automaticamente em Patogênico ou Comensal — e "
            "pode virar uma linha separada da mesma espécie já cadastrada com outra grafia. Prefira "
            "sempre uma das grafias desta lista, ou o nome científico completo (ex.: 'Giardia "
            "lamblia').\n\n"
            "Poliparasitismo: para registrar mais de uma espécie na MESMA amostra/método, escreva "
            "todas na mesma célula separadas por ' + ' (ex.: 'E. nana + G. lamblia + Enterobius "
            "vermicularis'). Vírgula também é aceita como separador. Não crie uma linha extra nem "
            "repita a coleta — é uma célula só, com todas as espécies encontradas."
        ]],
        columns=["Como preencher espécies e poliparasitismo"],
    )

    aviso = pd.DataFrame(
        [[
            "Este modelo traz uma coluna para cada método que o Pirajá reconhece. Se o seu "
            "laboratório não usa algum deles, pode simplesmente APAGAR a coluna inteira antes de "
            "enviar — o sistema detecta sozinho quais métodos estão presentes na planilha e ajusta "
            "as análises (denominadores, gráficos e tabelas) de acordo. Não é preciso preencher "
            "nem manter colunas de métodos não utilizados.\n\n"
            "Veja a aba 'Espécies reconhecidas' para a lista de parasitos que o sistema já sabe "
            "identificar e a grafia aceita para cada um, e como anotar poliparasitismo (mais de uma "
            "espécie na mesma célula).\n\n"
            "Use 'Não realizado' numa célula de método quando aquele método específico não chegou a "
            "ser executado NESSA amostra (mesmo com o pote/lâmina entregue) — diferente de 'Amostra "
            "insuficiente', que é quando o método foi tentado mas não deu resultado. Uma célula "
            "'Não realizado' não entra em nenhum denominador do relatório para aquele método.\n\n"
            "Território (opcional): preencha bairro, municipio e uf com o lugar onde o paciente MORA. "
            "Com isso o relatório mostra a prevalência por bairro e por município e pode gerar o mapa (opcional). "
            "Escreva o nome do bairro sempre do mesmo jeito; acentos e maiúsculas não importam. Não "
            "coloque endereço. Em São Paulo (SP), use o nome do DISTRITO (ex.: Capão Redondo, Itaquera); "
            "no Distrito Federal, o nome da REGIÃO ADMINISTRATIVA (ex.: Ceilândia, Taguatinga, Plano Piloto) "
            "e 'Brasília' como município.\n\n"
            "CONFIGURAÇÃO DA ANÁLISE (opcional) — abas Config_Parasitos, Config_Metodos, "
            "Config_Amostras e Config_Criterios: defina quais parasitos entram na análise (Incluir = Sim/Não), se cada "
            "um é Patogênico ou Comensal, quais métodos entram e se são de Fezes ou de Lâmina "
            "(Graham), e quantas amostras (P1..Pn) por paciente considerar e os critérios de inclusão de pacientes (por exemplo, "
            "só quem entregou todas as amostras). 'Agrupar como' junta "
            "grafias diferentes numa só espécie. Se essas abas estiverem na planilha, o site já abre "
            "a configuração preenchida; se não estiverem, você configura no próprio site e pode "
            "baixar a configuração para reaproveitar."
        ]],
        columns=["Leia antes de preencher"],
    )

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        aviso.to_excel(writer, sheet_name="Leia-me", index=False)
        example.to_excel(writer, sheet_name="Dados", index=False)
        legenda.to_excel(writer, sheet_name="Legenda", index=False)
        especies_nota.to_excel(writer, sheet_name="Especies_Reconhecidas", index=False, startrow=0)
        especies_reconhecidas.to_excel(writer, sheet_name="Especies_Reconhecidas", index=False, startrow=3)
        # Abas de configuração (opcionais): se estiverem na planilha enviada, o
        # site já abre a configuração da análise preenchida com elas.
        for nome_aba, aba in abas_config_modelo().items():
            aba.to_excel(writer, sheet_name=nome_aba, index=False)
    # acabamento visual (cores, larguras, listas suspensas) — não altera dados
    return estilizar_modelo(
        buf.getvalue(),
        logo_path=LOGO_PDF_PATH,
        categorias=CATEGORIAS_VALIDAS,
        amostras=AMOSTRAS_VALIDAS,
        colunas_lamina=set(metodo_cols_lamina),
    )


TEMPLATE_BYTES = generate_template_bytes()

# ==================================================================
# SIDEBAR — marca, fluxo de trabalho e status
# ==================================================================
with st.sidebar:
    if LOGO_SIDEBAR_URI:
        st.markdown(
            f'<div class="pj-sidebar-brand"><img src="{LOGO_SIDEBAR_URI}" alt="Pirajá Entero"></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown("### Pirajá")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<span class="pj-eyebrow">Fluxo de trabalho</span>', unsafe_allow_html=True)
    st.markdown(
        """
- **01 · Baixe** o modelo de planilha
- **02 · Envie** a planilha preenchida
- **03 · Configure** parasitos, métodos e amostras
- **04 · Receba** o relatório
        """
    )

    st.divider()
    st.download_button(
        "⬇ Modelo (.xlsx)",
        data=TEMPLATE_BYTES,
        file_name="Modelo_Levantamento_Parasitoses.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

    st.divider()
    st.markdown('<span class="pj-eyebrow">Sobre as amostras</span>', unsafe_allow_html=True)
    st.caption(
        "Alguns dos métodos aceitos, por tipo de amostra:\n\n"
        "**Pote de fezes** → HPJ, Willis, Baermann-Picanço, Faust, Kato-Katz, MIFC, Ritchie, "
        "entre outros.\n\n"
        "**Lâmina (swab)** → Graham, entre outros.\n\n"
        "Outros métodos também podem ser usados: basta incluir a coluna na planilha e indicar, "
        "no passo 03, se é de fezes ou de lâmina. A planilha não precisa trazer todos os métodos "
        "listados, só os que você usou."
    )

    st.divider()
    st.markdown('<span class="pj-eyebrow">Classificação clínica</span>', unsafe_allow_html=True)
    st.caption(
        "Você define no passo 03 se cada parasito é **patogênico** ou **comensal**. O sistema "
        "sugere uma classificação padrão — por exemplo, *Entamoeba histolytica/dispar* vem como "
        "patogênica, já que a diferenciação morfológica entre as duas formas não é possível no "
        "laboratório; *Blastocystis* vem sem classificação."
    )

# ==================================================================
# TOPO — marca + título
# ==================================================================
st.markdown(
    f"""<div class="pj-topbar">
        <div>
            <div class="name">Painel de análise epidemiológica</div>
        </div>
        <div>
            <div class="sub">Pirajá · Entero · parasitos intestinais</div>
        </div>
    </div>""",
    unsafe_allow_html=True,
)

# Pequeno aglomerado de "positivos" em cobre claro sobre o padrão de pontos
# do hero — o mesmo gesto do padrão "Campo" da identidade visual.
HERO_CLUSTER_SVG = (
    '<svg class="pj-hero-cluster" viewBox="0 0 120 90" xmlns="http://www.w3.org/2000/svg">'
    + "".join(
        f'<circle cx="{x}" cy="{y}" r="6" fill="{COBRE_CLARO}"/>'
        for x, y in [(39, 13), (65, 13), (91, 13), (52, 39), (78, 39), (65, 65), (104, 65)]
    )
    + "</svg>"
)

# ==================================================================
# HERO
# ==================================================================
st.markdown(
    f"""<div class="pj-hero">
    {HERO_CLUSTER_SVG}
    <h2>Seus dados de coleta, transformados em relatório epidemiológico.</h2>
    <p>Baixe o modelo de planilha e registre uma linha por coleta de cada paciente (P1, P2, P3…),
    com o resultado de cada método. Ao enviar a planilha, você escolhe quais parasitos entram na
    análise, classifica cada um como patogênico ou comensal e define os métodos e a quantidade de
    amostras consideradas. O relatório mostra a prevalência por paciente, sempre separada entre
    fezes e lâmina (Graham), considerando todos os parasitos e só os patogênicos, com intervalos
    de confiança de 95%, comparação entre métodos e efeito do número de amostras. Amostras
    insuficientes não entram no cálculo como negativas. Se a planilha trouxer o bairro e o município
    onde cada paciente mora, o painel também mostra a prevalência por território e pode gerar mapas
    por município e por bairro, no padrão cartográfico, prontos para artigo. No final, você baixa o
    relatório em PDF e em Excel.</p>
    </div>""",
    unsafe_allow_html=True,
)


# ==================================================================
# PASSO 01 — Baixar modelo
# ==================================================================
with st.container(key="pj-step-1"):
    step_header(1, "Baixe o modelo de planilha")
    st.write(
        "Um arquivo .xlsx com as colunas certas, os valores aceitos em cada uma, a lista de "
        "espécies reconhecidas e uma linha de exemplo — para preencher com os dados da sua coleta. "
        "Traz uma coluna para cada método que o sistema reconhece; apague as que o seu laboratório "
        "não usa antes de enviar."
    )
    st.download_button(
        "⬇ Baixar modelo (.xlsx)",
        data=TEMPLATE_BYTES,
        file_name="Modelo_Levantamento_Parasitoses.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

st.write("")

# ==================================================================
# PASSO 02 — Enviar planilha
# ==================================================================
with st.container(key="pj-step-2"):
    step_header(2, "Envie a planilha preenchida")
    st.write(
        "Aceita o modelo baixado acima, preenchido com uma linha por coleta (P1, P2, P3...) de cada "
        "paciente. Não precisa conter todos os métodos do modelo — só os que o laboratório "
        "efetivamente utilizou. Se a planilha trouxer as abas de configuração (Config_*), elas já "
        "vêm aplicadas no passo seguinte."
    )
    uploaded_file = st.file_uploader("Escolha o arquivo .xlsx", type=["xlsx", "xls"], label_visibility="collapsed")

st.write("")

# ==================================================================
# PASSO 03 — Relatório (sectorizado em abas)
# ==================================================================
if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    file_id = hashlib.md5(file_bytes).hexdigest()
    errors, df, cfg_planilha, cfg = [], None, {}, None
    try:
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
        _cfg_keys = {x.strip().lower() for x in CONFIG_SHEETS}
        abas_dados = [s for s in xls.sheet_names if s.strip().lower() not in _cfg_keys] or xls.sheet_names
        sheet_name = next((s for s in abas_dados if s.strip().lower() == "dados"), abas_dados[0])
        df_raw = pd.read_excel(xls, sheet_name=sheet_name)
        df = normalize_columns(df_raw)
        cfg_planilha = ler_config_da_planilha(xls)
    except Exception as exc:  # noqa: BLE001
        errors = [f"Não consegui ler esse arquivo. Confira se é um .xlsx válido, exportado a "
                  f"partir do modelo. ({exc})"]
        df = None

    if df is not None and not errors:
        faltando = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if faltando:
            errors.append(f"Colunas ausentes: {', '.join(faltando)}. Baixe o modelo novamente e confira os cabeçalhos.")
        elif not detectar_colunas_metodo(df) and "metodos" not in cfg_planilha:
            errors.append("Nenhuma coluna de método encontrada (cabeçalhos 'metodo_<nome>'). Confira a planilha "
                          "ou inclua a aba Config_Metodos indicando as colunas de resultado.")

    if not errors:
        cfg = passo_configuracao(df, file_bytes, uploaded_file.name, cfg_planilha, file_id)
        errors = validate_columns(df, cfg.metodos)

    if errors:
        for e in errors:
            st.error(e)
    else:
        metrics = compute_metrics(df, cfg)
        metodos_ativos_nomes = metrics.get("metodos_ativos_nomes", [])

        if metrics["total"] == 0 and metrics.get("total_antes_criterios"):
            st.error(
                f"Nenhum dos {metrics['total_antes_criterios']} pacientes atende aos critérios de inclusão "
                "definidos no passo 03. Revise a aba **Critérios de inclusão**."
            )
        elif metrics["total"] == 0:
            st.error("Nenhum paciente identificado. Confira se a coluna **id_paciente** está preenchida.")
        else:
            # conta só linhas com paciente identificado (linhas em branco no fim da
            # planilha não são coletas)
            n_coletas = int(df["id_paciente"].apply(norm_text).notna().sum())
            st.success(
                f"Planilha processada: {metrics.get('total_antes_criterios') or metrics['total']} pacientes, {n_coletas} coletas. "
                f"Métodos detectados: {', '.join(metodos_ativos_nomes)}. "
                "Relatório gerado abaixo."
            )

            dups = coletas_duplicadas(df)
            if not dups.empty:
                lista = ", ".join(f"{r.id_paciente} ({r.coleta}, {r.n_linhas} linhas)" for r in dups.head(15).itertuples())
                extra = f" e mais {len(dups) - 15}" if len(dups) > 15 else ""
                st.warning(
                    f"**Coletas repetidas na planilha:** {lista}{extra}. Cada coleta repetida foi "
                    "contada como UM pote/lâmina só; os resultados das linhas repetidas foram "
                    "somados (positivo em qualquer uma = positivo). Confira se não é erro de "
                    "digitação ou linha copiada."
                )
            rotulos_ruins = coletas_nao_reconhecidas(df)
            if rotulos_ruins:
                st.warning(
                    "**Rótulos de coleta não reconhecidos:** "
                    + ", ".join(f"'{r}'" for r in rotulos_ruins[:15])
                    + ". Use P1, P2, P3... Essas linhas entram nas prevalências, mas ficam de "
                    "fora da curva cumulativa."
                )

            with st.container(key="pj-step-4"):
                step_header(4, "Relatório da análise")
                st.caption(
                    f"{metrics['total']} pacientes {'incluídos' if metrics.get('criterios') else 'cadastrados'} · {len(metrics['fecal'])} com amostra "
                    f"fecal entregue · {len(metrics['apenas_lamina'])} só com lâmina · métodos: "
                    f"{', '.join(metodos_ativos_nomes)}."
                )

                if metrics.get("criterios"):
                    exc = metrics["excluidos_criterios"]
                    st.markdown(
                        f"""<div class="pj-note"><strong>Critérios de inclusão:</strong>
                        {"; ".join(metrics["criterios"])}. Entraram na análise <strong>{metrics['total']}</strong>
                        de {metrics['total_antes_criterios']} pacientes; <strong>{len(exc)}</strong> foram
                        excluídos de todas as contas.</div>""",
                        unsafe_allow_html=True,
                    )
                    if len(exc):
                        with st.expander(f"Ver os {len(exc)} pacientes excluídos e o motivo"):
                            st.dataframe(
                                exc.rename(columns={"id_paciente": "Paciente", "nome_paciente": "Nome",
                                                    "motivo": "Motivo da exclusão"}),
                                width="stretch", hide_index=True,
                            )
                    st.write("")

                n_inconclusivas = (
                    len(metrics["fecal_inconclusivo"])
                    + len(metrics["lamina_inconclusivo"])
                )

                tab_geral, tab_especies, tab_metodos, tab_base, tab_export = st.tabs(
                    ["📊  Visão geral", "🦠  Espécies & parasitos", "🔬  Métodos & amostragem", "📋  Base por paciente", "⬇  Exportar"]
                )

                # ---------------------------------------------------------
                # ABA 1 — VISÃO GERAL
                # ---------------------------------------------------------
                with tab_geral:
                    section_title("Resumo executivo")
                    dominios_ativos = {m[3] for m in metrics.get("metodos_ativos", [])}
                    tem_fecal = "fecal" in dominios_ativos
                    tem_lamina = "lamina" in dominios_ativos
                    n_fecal = len(metrics["fecal_conclusivo"])
                    n_lamina = len(metrics["lamina_conclusivo"])
                    n_comb = len(metrics["combinada_base"])
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Prevalência — amostra fecal", prev_valor(metrics['prev_fecal'], n_fecal),
                                   help="Base: pacientes com resultado CONCLUSIVO em pelo menos um método "
                                        "fecal presente nesta planilha. Achados exclusivos de métodos de "
                                        "lâmina não entram aqui — veja 'Espécies & parasitos' para a "
                                        "prevalência de Enterobius. Pacientes com todos os resultados "
                                        "fecais marcados como 'Amostra insuficiente' são excluídos do "
                                        "denominador (não contam como negativos). IC95% calculado pelo "
                                        "método de Wilson.")
                        st.caption(prev_legenda(metrics["prev_fecal_ic95_inf"], metrics["prev_fecal_ic95_sup"],
                                                n_fecal, tem_fecal, "amostra fecal"))
                    with c2:
                        st.metric("Prevalência — lâmina (todos os pacientes)", prev_valor(metrics['prev_lamina'], n_lamina),
                                   help="Base: TODOS os pacientes com resultado conclusivo do(s) método(s) "
                                        "de lâmina desta planilha (Graham) — tenham eles entregado só a "
                                        "lâmina ou fezes e lâmina. Reflete tipicamente Enterobius "
                                        "vermicularis — o único parasita pesquisável só com a lâmina. O "
                                        "subgrupo que entregou exclusivamente lâmina é reportado à parte "
                                        "logo abaixo, mas seus resultados já estão somados aqui. IC95% "
                                        "calculado pelo método de Wilson.")
                        st.caption(prev_legenda(metrics["prev_lamina_ic95_inf"], metrics["prev_lamina_ic95_sup"],
                                                n_lamina, tem_lamina, "lâmina"))
                    with c3:
                        st.metric("Prevalência combinada", prev_valor(metrics['prev_combinada'], n_comb),
                                   help="Todos os pacientes com pelo menos um resultado conclusivo, em "
                                        "qualquer domínio (fezes e/ou lâmina) — use com cautela, mistura "
                                        "profundidades diagnósticas diferentes. IC95% calculado pelo "
                                        "método de Wilson.")
                        st.caption(prev_legenda(metrics["prev_combinada_ic95_inf"], metrics["prev_combinada_ic95_sup"],
                                                n_comb, True, "nenhum domínio"))

                    p1, p2, _p3 = st.columns(3)
                    with p1:
                        st.metric("Fezes — somente patogênicos", prev_valor(metrics["prev_fecal_patogenico"], n_fecal),
                                  help="Mesma base da prevalência fecal; conta só pacientes com ao menos um "
                                       "parasito classificado como patogênico no passo 03.")
                        st.caption(prev_legenda(metrics["prev_fecal_patogenico_ic95_inf"],
                                                metrics["prev_fecal_patogenico_ic95_sup"], n_fecal, tem_fecal,
                                                "amostra fecal"))
                    with p2:
                        st.metric("Lâmina — somente patogênicos", prev_valor(metrics["prev_lamina_patogenico"], n_lamina),
                                  help="Mesma base da prevalência de lâmina; conta só pacientes com ao menos um "
                                       "parasito classificado como patogênico no passo 03.")
                        st.caption(prev_legenda(metrics["prev_lamina_patogenico_ic95_inf"],
                                                metrics["prev_lamina_patogenico_ic95_sup"], n_lamina, tem_lamina,
                                                "lâmina"))

                    if n_inconclusivas > 0:
                        st.markdown(
                            f"""<div class="pj-note"><strong>Amostras inconclusivas:</strong>
                            {len(metrics['fecal_inconclusivo'])} paciente(s) entregaram pote de fezes mas
                            tiveram <em>todos</em> os métodos fecais marcados como "Amostra insuficiente"
                            (ou sem resultado registrado){', ' + str(len(metrics['lamina_inconclusivo'])) + ' paciente(s) com lâmina entregue na mesma situação' if len(metrics['lamina_inconclusivo']) else ''}.
                            Esses pacientes foram excluídos dos denominadores de prevalência acima — eles
                            <u>não</u> contam como negativos, pois não houve diagnóstico conclusivo.
                            Células marcadas como "Não realizado" não entram nesta contagem — elas são
                            excluídas do denominador do método sem contar como inconclusivas.</div>""",
                            unsafe_allow_html=True,
                        )

                    if len(metrics["apenas_lamina"]) > 0:
                        st.markdown(
                            f"""<div class="pj-note" style="margin-top:8px;"><strong>Atenção:</strong> {len(metrics['apenas_lamina'])}
                            paciente(s) só entregaram a lâmina, nunca o pote de fezes — para eles, apenas
                            o(s) método(s) de lâmina desta planilha pôde(puderam) ser pesquisado(s). Esses
                            resultados já estão somados na "Prevalência — lâmina (todos os pacientes)"
                            acima; isoladamente, a prevalência só neste subgrupo é de
                            {metrics['prev_lamina_only']:.1f}%
                            ({int(metrics['lamina_only_conclusivo']['positivo_lamina'].sum())} de
                            {len(metrics['lamina_only_conclusivo'])} pacientes conclusivos).</div>""",
                            unsafe_allow_html=True,
                        )

                    st.write("")
                    section_title("Pacientes por profundidade de amostragem")
                    cat_df = metrics["cat_counts"].rename("n_pacientes").to_frame()
                    cat_df["%"] = (100 * cat_df["n_pacientes"] / metrics["total"]).round(1)
                    st.dataframe(cat_df, width='stretch')

                    # ---- território (moradia do paciente) ----
                    st.write("")
                    if metrics.get("tem_territorio"):
                        section_title(
                            "Prevalência por território (moradia)",
                            "Pacientes com resultado conclusivo, agrupados pelo bairro e município onde moram. "
                            "Positivo = qualquer parasito em qualquer tipo de amostra (mesma base da "
                            "prevalência combinada). IC95% pelo método de Wilson.",
                        )

                        def _tab_territorio(d, nivel):
                            cols = ["municipio", "uf"] if nivel == "municipio" else ["bairro", "municipio", "uf"]
                            t = with_ic_column(d)[cols + ["n_pacientes", "n_positivos", "prevalencia", "IC 95%",
                                                         "prevalencia_patogenico"]]
                            return t.rename(columns={
                                "bairro": "Bairro", "municipio": "Município", "uf": "UF", "n_pacientes": "Pacientes",
                                "n_positivos": "Positivos", "prevalencia": "Prevalência %",
                                "prevalencia_patogenico": "Só patogênicos %",
                            })

                        tm = metrics["territorio_municipio"]
                        tb = metrics["territorio_bairro"]
                        t_m, t_b = st.tabs(["Por município", "Por bairro"])
                        with t_m:
                            if tm.empty:
                                st.info("Nenhum paciente com município preenchido.")
                            else:
                                st.dataframe(_tab_territorio(tm, "municipio"), width="stretch", hide_index=True)
                        with t_b:
                            if tb.empty:
                                st.info("Nenhum paciente com bairro preenchido.")
                            else:
                                st.dataframe(_tab_territorio(tb, "bairro"), width="stretch", hide_index=True)
                                pequenos = int((tb["n_pacientes"] < 10).sum())
                                if pequenos:
                                    st.caption(
                                        f"{pequenos} bairro(s) com menos de 10 pacientes: a prevalência desses "
                                        "bairros é pouco precisa (veja a largura do IC95%)."
                                    )
                        avisos_t = []
                        if metrics["territorio_sem_bairro"]:
                            avisos_t.append(f"{metrics['territorio_sem_bairro']} paciente(s) sem bairro preenchido "
                                            "ficaram fora da tabela por bairro")
                        if metrics["territorio_sem_municipio"]:
                            avisos_t.append(f"{metrics['territorio_sem_municipio']} sem município ficaram fora da "
                                            "tabela por município")
                        inc = metrics["territorio_inconsistentes"]
                        if inc:
                            avisos_t.append(
                                f"{len(inc)} paciente(s) com bairro/município diferentes entre as coletas — foi "
                                f"usado o da primeira linha ({', '.join(map(str, inc[:10]))}"
                                + ("…" if len(inc) > 10 else "") + ")")
                        if avisos_t:
                            st.caption("Atenção: " + "; ".join(avisos_t) + ".")

                        # ---- mapa (opcional) ----
                        st.write("")
                        gerar_mapa = st.toggle(
                            "🗺️  Gerar mapa", key="mapa_on",
                            help="Mapa de prevalência por município ou bairro de residência, no padrão "
                                 "cartográfico (para artigo) e interativo. Opcional.",
                        )
                        if not gerar_mapa:
                            st.session_state.pop("mapa_pdf", None)
                        else:
                            painel_mapa(metrics)

                # ---------------------------------------------------------
                # ABA 2 — ESPÉCIES & PARASITOS
                # ---------------------------------------------------------
                with tab_especies:
                    _ativos = metrics.get("metodos_ativos", [])
                    fec_nomes = [n for _, n, _, d in _ativos if d == "fecal"]
                    lam_nomes = [n for _, n, _, d in _ativos if d == "lamina"]
                    fc, lc = metrics["fecal_conclusivo"], metrics["lamina_conclusivo"]
                    bloco_dominio(
                        "Amostras de fezes — todos os parasitos x somente patogênicos",
                        f"Métodos de fezes: {', '.join(fec_nomes) or '—'}. Base: pacientes com resultado "
                        "conclusivo nas fezes; um paciente conta uma vez por espécie, mesmo que ela tenha "
                        "aparecido em mais de uma coleta ou método. Achados da lâmina não entram aqui.",
                        metrics["especies_resumo"], len(fc), int(fc["positivo_fecal"].sum()) if len(fc) else 0,
                        metrics["prev_fecal"], (metrics["prev_fecal_ic95_inf"], metrics["prev_fecal_ic95_sup"]),
                        metrics["n_fecal_patogenico"], metrics["prev_fecal_patogenico"],
                        (metrics["prev_fecal_patogenico_ic95_inf"], metrics["prev_fecal_patogenico_ic95_sup"]),
                        bool(fec_nomes), key="dom-fezes",
                    )
                    st.write("")
                    bloco_dominio(
                        f"Lâmina ({' / '.join(lam_nomes) or 'Graham'}) — todos os parasitos x somente patogênicos",
                        "Base: pacientes com resultado conclusivo na lâmina (fita/swab perianal). Analisada "
                        "separadamente das fezes, porque a lâmina pesquisa um conjunto diferente de "
                        "parasitos (tipicamente Enterobius vermicularis).",
                        metrics["especies_lamina_resumo"], len(lc), int(lc["positivo_lamina"].sum()) if len(lc) else 0,
                        metrics["prev_lamina"], (metrics["prev_lamina_ic95_inf"], metrics["prev_lamina_ic95_sup"]),
                        metrics["n_lamina_patogenico"], metrics["prev_lamina_patogenico"],
                        (metrics["prev_lamina_patogenico_ic95_inf"], metrics["prev_lamina_patogenico_ic95_sup"]),
                        bool(lam_nomes), key="dom-lamina",
                    )

                    st.write("")
                    section_title("Mono x poliparasitismo", "Base: espécies de origem fecal.")
                    colC, colD = st.columns([2, 3])
                    with colC:
                        fig2 = go.Figure(
                            data=[go.Pie(
                                labels=["Negativo", "Monoparasitismo", "Poliparasitismo"],
                                values=[metrics["neg"], metrics["mono"], metrics["poli"]],
                                marker_colors=[SAGE, TEAL, BRICK],
                                hole=0.45,
                            )]
                        )
                        fig2.update_layout(**PLOTLY_LAYOUT)
                        st.plotly_chart(fig2, width='stretch')
                    with colD:
                        st.markdown("**Combinações mais frequentes**")
                        if metrics["combos_resumo"].empty:
                            st.info("Nenhuma coinfecção registrada.")
                        else:
                            st.dataframe(metrics["combos_resumo"], width='stretch', hide_index=True)

                    st.write("")
                    subsection_title(
                        "Prevalência por método diagnóstico e espécie",
                        "Cada célula mostra a prevalência (%) daquela espécie especificamente pelo "
                        "método indicado, com denominador = pacientes com resultado conclusivo NAQUELE "
                        "método. Uma mesma espécie pode aparecer em mais de um método fecal (ex.: um "
                        "ovo de helminto pode ser visto tanto no HPJ quanto no Willis). Colunas mostram "
                        "só os métodos presentes nesta planilha.",
                    )
                    if not metrics["metodo_especie_resumo"].empty and metodos_ativos_nomes:
                        pivot = metrics["metodo_especie_resumo"].pivot_table(
                            index="especie", columns="metodo", values="prevalencia", aggfunc="first",
                        ).reindex(columns=metodos_ativos_nomes)
                        st.dataframe(pivot, width='stretch')
                        with st.expander("Ver com intervalos de confiança (IC95%, Wilson)"):
                            me_display = with_ic_column(metrics["metodo_especie_resumo"]).rename(columns={
                                "metodo": "Método", "especie": "Espécie", "n": "N",
                                "prevalencia": "Prevalência %", "categoria": "Categoria",
                            })
                            st.dataframe(me_display, width='stretch', hide_index=True)
                    else:
                        st.info("Nenhum dado suficiente para o cruzamento método x espécie.")


                    st.write("")
                    with st.expander("Visão unificada — fezes e lâmina num só gráfico"):
                        section_title(
                            "Prevalência de todos os parasitos",
                            "Reúne, num só gráfico, as espécies encontradas por métodos fecais e por "
                            "métodos de lâmina presentes nesta planilha. As bases de cálculo diferem por "
                            "domínio — a tabela ao lado do gráfico mostra o denominador (Base N) e o(s) "
                            "método(s) que detectou(aram) cada espécie. Quando a mesma espécie foi "
                            "encontrada em métodos de domínios diferentes (ex.: Enterobius vermicularis, "
                            "tipicamente por um método de lâmina, mas ocasionalmente também visível num "
                            "método fecal), ela aparece numa única linha \"Fecal + Lâmina\" — o cálculo é "
                            "feito por paciente, então quem foi detectado por mais de um método conta uma "
                            "vez só, não duas.",
                        )
                        colT, colU = st.columns([3, 2])
                        with colT:
                            if not metrics["todos_parasitos_resumo"].empty:
                                fig_all = px.bar(
                                    metrics["todos_parasitos_resumo"].sort_values("prevalencia"),
                                    x="prevalencia", y="especie", orientation="h",
                                    color="categoria",
                                    color_discrete_map=CATEGORIA_CORES,
                                    pattern_shape="dominio",
                                    labels={"prevalencia": "Prevalência (%)", "especie": "", "dominio": "Amostra"},
                                    hover_data={"metodos": True, "base_n": True, "n": True},
                                )
                                fig_all.update_layout(**PLOTLY_LAYOUT, showlegend=True, legend_title="")
                                # com várias cores/hachuras o Plotly cria um "trace" por
                                # grupo e perde a ordem do sort_values — força a ordem
                                # pela prevalência (maior em cima).
                                fig_all.update_yaxes(categoryorder="total ascending")
                                st.plotly_chart(fig_all, width='stretch', key="graf-unificado")
                            else:
                                st.info("Nenhum parasito detectado nesta base.")
                        with colU:
                            todos_display = with_ic_column(metrics["todos_parasitos_resumo"]).rename(columns={
                                "especie": "Espécie", "categoria": "Categoria", "dominio": "Amostra",
                                "n": "N", "prevalencia": "Prevalência %", "base_n": "Base N", "metodos": "Método(s)",
                            })
                            st.dataframe(todos_display, width='stretch', hide_index=True)
                            st.caption("IC95% pelo método de Wilson, calculado sobre o denominador (Base N) de cada espécie.")

                # ---------------------------------------------------------
                # ABA 3 — MÉTODOS & AMOSTRAGEM
                # ---------------------------------------------------------
                with tab_metodos:
                    section_title(
                        "Comparação entre métodos diagnósticos",
                        "Denominador = pacientes com resultado conclusivo naquele método específico "
                        "(exclui quem teve só 'Amostra insuficiente' ou 'Não realizado' nesse método). "
                        "Lista só os métodos presentes nesta planilha.",
                    )
                    colE, colF = st.columns([3, 2])
                    with colE:
                        if not metrics["metodos_resumo"].empty:
                            # fezes e lâmina lado a lado, mas em painéis separados — são
                            # amostras diferentes e não devem ser lidas como comparáveis
                            fig3 = px.bar(
                                metrics["metodos_resumo"], x="metodo", y="prevalencia",
                                color="amostra_biologica", facet_col="amostra_biologica",
                                color_discrete_map={"Pote de fezes": TEAL, "Lâmina": BRICK},
                                category_orders={"amostra_biologica": ["Pote de fezes", "Lâmina"]},
                                labels={"prevalencia": "Prevalência (%)", "metodo": "", "amostra_biologica": ""},
                            )
                            fig3.update_xaxes(matches=None)
                            fig3.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
                            fig3.update_layout(**PLOTLY_LAYOUT, showlegend=False)
                            st.plotly_chart(fig3, width='stretch')
                        else:
                            st.info("Nenhum método detectado nesta planilha.")
                    with colF:
                        met_display = with_ic_column(metrics["metodos_resumo"]).rename(columns={
                            "metodo": "Método", "amostra_biologica": "Amostra",
                            "n_pacientes_testaveis": "Testáveis", "n_pacientes_positivas": "Positivas",
                            "n_pacientes_inconclusivas": "Inconclusivas", "prevalencia": "Prevalência %",
                        })
                        st.dataframe(met_display, width='stretch', hide_index=True)
                        st.caption("IC95% pelo método de Wilson.")

                    st.write("")
                    subsection_title(
                        "HPJ x Willis — teste de McNemar",
                        "Compara os dois métodos aplicados à MESMA amostra de fezes da mesma criança "
                        "(dados pareados) — testa se um método detecta mais positivos que o outro, "
                        "usando só os pacientes em que os dois métodos discordaram entre si. Só "
                        "calculado quando a planilha traz os dois métodos.",
                    )
                    mc = metrics["mcnemar_hpj_willis"]
                    if mc["n_pareado"] == 0 or mc["tabela"] is None:
                        st.info("Sem pacientes com resultado conclusivo em HPJ e Willis simultaneamente "
                                "(ou um dos dois métodos não está presente nesta planilha) — teste não "
                                "calculado.")
                    else:
                        tb = mc["tabela"]
                        mc_col1, mc_col2 = st.columns([2, 3])
                        with mc_col1:
                            mc_table = pd.DataFrame(
                                [[tb["pp"], tb["pn"]], [tb["np"], tb["nn"]]],
                                index=["HPJ +", "HPJ −"], columns=["Willis +", "Willis −"],
                            )
                            st.dataframe(mc_table, width='stretch')
                        with mc_col2:
                            metodo_label = {
                                "exato": "teste exato (< 25 discordâncias)",
                                "chi2_corrigido": "qui-quadrado com correção de continuidade",
                                "sem_discordancia": "sem discordâncias — nada a testar",
                            }.get(mc["metodo"], mc["metodo"])
                            st.metric("p-valor (McNemar)", f"{mc['p_valor']:.4f}" if mc["p_valor"] is not None else "—")
                            st.caption(
                                f"n pareado = {mc['n_pareado']} · {tb['pn'] + tb['np']} discordância(s) "
                                f"({tb['pn']} HPJ+/Willis−, {tb['np']} HPJ−/Willis+) · {metodo_label}."
                            )
                            if mc["p_valor"] is not None and mc["p_valor"] < 0.05:
                                st.caption("p < 0,05 — diferença estatisticamente significativa entre os métodos nesta amostra.")
                            elif mc["p_valor"] is not None:
                                st.caption("p ≥ 0,05 — sem evidência estatística de diferença entre os métodos nesta amostra.")

                    st.write("")
                    section_title(
                        "Efeito do número de potes de fezes entregues",
                        "Usa somente positividade fecal (qualquer método fecal presente na "
                        "planilha). Compara SUBGRUPOS diferentes de pacientes (quem entregou 1, 2 ou 3 "
                        "potes), o que pode ter viés de seleção — veja a curva cumulativa abaixo, "
                        "calculada no mesmo grupo de pacientes, para uma estimativa sem esse viés.",
                    )
                    if not metrics["efeito_n_coletas"].empty:
                        fig4 = px.bar(
                            metrics["efeito_n_coletas"], x="n_potes_entregues", y="prevalencia",
                            labels={"prevalencia": "Prevalência (%)", "n_potes_entregues": "Nº de potes entregues"},
                            text="n_pacientes",
                        )
                        fig4.update_traces(marker_color=TEAL_DARK, texttemplate="n=%{text}", textposition="outside")
                        fig4.update_layout(**PLOTLY_LAYOUT)
                        st.plotly_chart(fig4, width='stretch')
                    else:
                        st.info("Dados insuficientes para este gráfico.")

                    ca = metrics["cochran_armitage_efeito_coletas"]
                    if ca["p_valor"] is not None:
                        st.caption(
                            f"Teste de tendência de Cochran-Armitage: Z = {ca['estatistica_z']:.3f}, "
                            f"p = {ca['p_valor']:.4f} ({ca['n_grupos']} grupos). {ca['aviso']}"
                        )
                    elif ca["n_grupos"] and ca["n_grupos"] >= 2:
                        st.caption(f"Teste de tendência de Cochran-Armitage não calculável nesta base. {ca['aviso']}")

                    st.write("")
                    section_title("Ganho marginal por amostra — curva cumulativa")
                    if not metrics["fecal_cumulativa"].empty:
                        n_grupo = int(metrics["fecal_cumulativa"]["n_pacientes"].iloc[0])
                        k_max = int(metrics["fecal_cumulativa"]["k"].max())
                        st.caption(
                            f"Mesmo grupo de {n_grupo} paciente(s) que entregou o número máximo de potes "
                            f"observado no estudo ({k_max}), medindo quantas ficariam positivas se o "
                            "laboratório parasse na 1ª, 2ª ... até a última coleta. Como é a mesma "
                            "paciente sendo acompanhado (medida repetida), este gráfico não sofre o viés "
                            "de comparar subgrupos diferentes de crianças."
                        )
                        fig5 = px.line(
                            metrics["fecal_cumulativa"], x="k", y="prevalencia_cumulativa", markers=True,
                            labels={"k": "Nº de potes considerados (cumulativo)", "prevalencia_cumulativa": "Prevalência cumulativa (%)"},
                        )
                        fig5.update_traces(line_color=TEAL_DARK, marker_color=BRICK)
                        fig5.update_layout(**PLOTLY_LAYOUT)
                        st.plotly_chart(fig5, width='stretch')
                    else:
                        st.info("Dados insuficientes para a curva cumulativa (nenhum paciente com coletas identificadas por P1/P2/P3).")

                # ---------------------------------------------------------
                # ABA 4 — BASE POR CRIANÇA
                # ---------------------------------------------------------
                with tab_base:
                    section_title("Base completa por criança")
                    display_cols = [
                        "id_paciente", "nome_paciente", "categoria_amostragem",
                        "n_coletas_pote_entregue", "n_coletas_lamina_entregue",
                        "fecal_status", "lamina_status",
                        "positivo_algum_metodo", "tem_patogenico", "especies_str",
                    ]
                    st.dataframe(
                        metrics["por_paciente"][display_cols].sort_values("id_paciente"),
                        width='stretch', hide_index=True, height=460,
                    )

                # ---------------------------------------------------------
                # ABA 5 — EXPORTAR
                # ---------------------------------------------------------
                def generate_report_excel_bytes(m: dict) -> bytes:
                    buf = io.BytesIO()
                    metodo_nomes = m.get("metodos_ativos_nomes", [])
                    list_cols = ["especies", "especies_fecais", "especies_lamina"] + [
                        f"especies_{nome}" for nome in metodo_nomes
                    ]
                    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                        m["por_paciente"].drop(columns=[c for c in list_cols if c in m["por_paciente"].columns]).to_excel(
                            writer, sheet_name="Base_por_Crianca", index=False
                        )
                        m["cat_counts"].rename("n").to_frame().to_excel(writer, sheet_name="Categoria_Amostragem")
                        pd.DataFrame([
                            {"metrica": "Prevalência — amostra fecal (conclusiva)", "valor_pct": m["prev_fecal"] if len(m["fecal_conclusivo"]) else None,
                             "ic95_inf": m["prev_fecal_ic95_inf"], "ic95_sup": m["prev_fecal_ic95_sup"],
                             "n_pacientes": len(m["fecal_conclusivo"])},
                            {"metrica": "Prevalência — lâmina, todos os pacientes (conclusiva)", "valor_pct": m["prev_lamina"] if len(m["lamina_conclusivo"]) else None,
                             "ic95_inf": m["prev_lamina_ic95_inf"], "ic95_sup": m["prev_lamina_ic95_sup"],
                             "n_pacientes": len(m["lamina_conclusivo"])},
                            {"metrica": "Prevalência — subgrupo só-lâmina (conclusiva)", "valor_pct": m["prev_lamina_only"] if len(m["lamina_only_conclusivo"]) else None,
                             "ic95_inf": m["prev_lamina_only_ic95_inf"], "ic95_sup": m["prev_lamina_only_ic95_sup"],
                             "n_pacientes": len(m["lamina_only_conclusivo"])},
                            {"metrica": "Prevalência combinada (conclusiva)", "valor_pct": m["prev_combinada"] if len(m["combinada_base"]) else None,
                             "ic95_inf": m["prev_combinada_ic95_inf"], "ic95_sup": m["prev_combinada_ic95_sup"],
                             "n_pacientes": len(m["combinada_base"])},
                            {"metrica": "Inconclusivas — fezes (amostra insuficiente em tudo)", "valor_pct": None,
                             "ic95_inf": None, "ic95_sup": None, "n_pacientes": len(m["fecal_inconclusivo"])},
                            {"metrica": "Inconclusivas — lâmina, todos os pacientes", "valor_pct": None,
                             "ic95_inf": None, "ic95_sup": None, "n_pacientes": len(m["lamina_inconclusivo"])},
                            {"metrica": "Inconclusivas — subgrupo só-lâmina", "valor_pct": None,
                             "ic95_inf": None, "ic95_sup": None, "n_pacientes": len(m["lamina_only_inconclusivo"])},
                            {"metrica": "Métodos detectados nesta planilha", "valor_pct": None,
                             "ic95_inf": None, "ic95_sup": None, "n_pacientes": None,
                             },
                        ]).to_excel(writer, sheet_name="Prevalencia_Geral", index=False)
                        pd.DataFrame({"metodos_ativos": metodo_nomes}).to_excel(
                            writer, sheet_name="Metodos_Ativos", index=False
                        )
                        m["todos_parasitos_resumo"].to_excel(writer, sheet_name="Todos_os_Parasitos", index=False)
                        m["especies_lamina_resumo"].to_excel(writer, sheet_name="Prevalencia_Especie_Lamina", index=False)
                        pd.DataFrame([
                            {"amostra": "Fezes", "grupo": "Todos os parasitos", "valor_pct": m["prev_fecal"],
                             "ic95_inf": m["prev_fecal_ic95_inf"], "ic95_sup": m["prev_fecal_ic95_sup"],
                             "n_positivos": int(m["fecal_conclusivo"]["positivo_fecal"].sum()) if len(m["fecal_conclusivo"]) else 0,
                             "n_base": len(m["fecal_conclusivo"])},
                            {"amostra": "Fezes", "grupo": "Somente patogênicos", "valor_pct": m["prev_fecal_patogenico"],
                             "ic95_inf": m["prev_fecal_patogenico_ic95_inf"], "ic95_sup": m["prev_fecal_patogenico_ic95_sup"],
                             "n_positivos": m["n_fecal_patogenico"], "n_base": len(m["fecal_conclusivo"])},
                            {"amostra": "Lâmina", "grupo": "Todos os parasitos", "valor_pct": m["prev_lamina"],
                             "ic95_inf": m["prev_lamina_ic95_inf"], "ic95_sup": m["prev_lamina_ic95_sup"],
                             "n_positivos": int(m["lamina_conclusivo"]["positivo_lamina"].sum()) if len(m["lamina_conclusivo"]) else 0,
                             "n_base": len(m["lamina_conclusivo"])},
                            {"amostra": "Lâmina", "grupo": "Somente patogênicos", "valor_pct": m["prev_lamina_patogenico"],
                             "ic95_inf": m["prev_lamina_patogenico_ic95_inf"], "ic95_sup": m["prev_lamina_patogenico_ic95_sup"],
                             "n_positivos": m["n_lamina_patogenico"], "n_base": len(m["lamina_conclusivo"])},
                        ]).to_excel(writer, sheet_name="Todos_x_Patogenicos", index=False)
                        m["especies_resumo"].to_excel(writer, sheet_name="Prevalencia_por_Especie", index=False)
                        m["metodo_especie_resumo"].to_excel(writer, sheet_name="Prevalencia_Metodo_x_Especie", index=False)
                        pd.DataFrame([
                            {"categoria": "Negativo", "n": m["neg"]},
                            {"categoria": "Monoparasitismo", "n": m["mono"]},
                            {"categoria": "Poliparasitismo", "n": m["poli"]},
                        ]).to_excel(writer, sheet_name="Poliparasitismo", index=False)
                        m["combos_resumo"].to_excel(writer, sheet_name="Combinacoes", index=False)
                        m["metodos_resumo"].to_excel(writer, sheet_name="Comparacao_Metodos", index=False)
                        m["efeito_n_coletas"].to_excel(writer, sheet_name="Prevalencia_x_NColetas", index=False)
                        m["fecal_cumulativa"].to_excel(writer, sheet_name="Curva_Cumulativa_Fecal", index=False)

                        mc = m["mcnemar_hpj_willis"]
                        tb = mc["tabela"] or {}
                        pd.DataFrame([{
                            "n_pareado": mc["n_pareado"],
                            "HPJ+ / Willis+": tb.get("pp"),
                            "HPJ+ / Willis-": tb.get("pn"),
                            "HPJ- / Willis+": tb.get("np"),
                            "HPJ- / Willis-": tb.get("nn"),
                            "estatistica": mc["estatistica"],
                            "p_valor": mc["p_valor"],
                            "metodo": mc["metodo"],
                        }]).to_excel(writer, sheet_name="McNemar_HPJ_x_Willis", index=False)

                        ca = m["cochran_armitage_efeito_coletas"]
                        pd.DataFrame([{
                            "n_grupos": ca["n_grupos"],
                            "estatistica_z": ca["estatistica_z"],
                            "p_valor": ca["p_valor"],
                            "aviso": ca["aviso"],
                        }]).to_excel(writer, sheet_name="CochranArmitage_NPotes", index=False)
                        if m.get("tem_territorio"):
                            if not m["territorio_municipio"].empty:
                                m["territorio_municipio"].to_excel(writer, sheet_name="Prevalencia_Municipio", index=False)
                            if not m["territorio_bairro"].empty:
                                m["territorio_bairro"].to_excel(writer, sheet_name="Prevalencia_Bairro", index=False)
                        exc = m.get("excluidos_criterios")
                        if exc is not None and len(exc):
                            exc.rename(columns={"id_paciente": "id_paciente", "nome_paciente": "nome_paciente",
                                                "motivo": "motivo_exclusao"}).to_excel(
                                writer, sheet_name="Pacientes_Excluidos", index=False)
                        # configuração usada — permite reproduzir a análise
                        ss_ = st.session_state
                        if "cfg_par" in ss_:
                            cfg_xls = pd.ExcelFile(io.BytesIO(config_xlsx_bytes(
                                ss_["cfg_par"], ss_["cfg_met"], ss_["cfg_n"], ss_.get("cfg_crit"))))
                            for aba in cfg_xls.sheet_names:
                                pd.read_excel(cfg_xls, sheet_name=aba).to_excel(writer, sheet_name=aba, index=False)
                    # capa com sumário + formatação Pirajá (não altera valores)
                    agora = _agora(getattr(st.context, "timezone", None))
                    resumo = (
                        f"{m['total']} pacientes cadastrados · {len(m['fecal'])} com amostra fecal entregue · "
                        f"{len(m['apenas_lamina'])} só com lâmina · métodos: "
                        f"{', '.join(metodo_nomes) if metodo_nomes else '—'}."
                    )
                    return estilizar_relatorio(
                        buf.getvalue(),
                        logo_path=LOGO_PDF_PATH,
                        gerado_em=f"Gerado em {agora.strftime('%d/%m/%Y às %H:%M')}",
                        resumo=resumo,
                        categorias=CATEGORIAS_VALIDAS,
                        amostras=AMOSTRAS_VALIDAS,
                    )

                with tab_export:
                    section_title("Baixe os relatórios completos")
                    st.write(
                        "O Excel traz todas as tabelas em abas separadas, prontas para uso em outras "
                        "análises. O PDF traz um relatório formatado, pronto para impressão ou envio."
                    )
                    col_dl1, col_dl2 = st.columns(2)
                    with col_dl1:
                        st.download_button(
                            "⬇ Baixar relatório em Excel",
                            data=generate_report_excel_bytes(metrics),
                            file_name="Relatorio_Analise_Epidemiologica.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            width="stretch",
                        )
                    with col_dl2:
                        st.download_button(
                            "⬇ Baixar relatório em PDF",
                            data=build_pdf_report(
                                metrics,
                                logo_path=str(LOGO_PDF_PATH) if LOGO_PDF_PATH.exists() else None,
                                fuso=getattr(st.context, "timezone", None),  # fuso do navegador de quem usa
                                mapa=st.session_state.get("mapa_pdf"),  # só se o mapa foi gerado
                            ),
                            file_name="Relatorio_Analise_Epidemiologica.pdf",
                            mime="application/pdf",
                            width="stretch",
                        )


st.divider()
st.caption(
    "Nota metodológica: a prevalência é calculada por paciente, não por exame — um paciente conta "
    "como positiva se qualquer uma de suas coletas (P1, P2, ... Pn) revelou o parasita. O pote de fezes "
    "alimenta os métodos de domínio fecal; a lâmina alimenta exclusivamente os métodos de domínio "
    "lâmina/swab. Crianças cujos únicos resultados foram 'Amostra insuficiente' são reportadas à "
    "parte como inconclusivas, e não entram nos denominadores de prevalência. Uma célula marcada "
    "'Não realizado' é excluída por completo do denominador daquele método para aquela coleta. A "
    "planilha enviada não precisa trazer todos os métodos do modelo — o sistema detecta e analisa "
    "só os presentes."
)
