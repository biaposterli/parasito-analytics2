"""Ilustrações autorais (SVG) da apresentação do painel — identidade Pirajá.

Linguagem visual: formas geométricas simples, o ponto como unidade (cada ponto
é um paciente, como no símbolo da marca) e o cobre marcando o "positivo".
Tudo vetorial e embutido no HTML: nenhum arquivo externo, nenhuma fonte de
terceiros além das da identidade.
"""

MATA = "#11483D"
FOLHA = "#328567"
COBRE = "#9C4A2F"
COBRE_CLARO = "#D08A6A"
PAPEL = "#F4F1EA"
TINTA = "#1B2421"
LINHA = "#DCD6C8"
TINTA_SUAVE = "#4E5B55"
FOLHA_CLARA = "#E3EEE8"
COBRE_TINT = "#F3E4DB"
BRANCO = "#FFFFFF"
MATA_PONTO = "#1F6150"
RAMPA = ["#F3E4DB", "#E2B49A", "#C97E5C", "#9C4A2F", "#5E2A19"]

_TXT = "font-family:'Instrument Sans',sans-serif;font-weight:600"


def _svg(corpo: str, w: int = 220, h: int = 150, classe: str = "pj-ilu", titulo: str = "") -> str:
    t = f"<title>{titulo}</title>" if titulo else ""
    return (f'<svg class="{classe}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
            f'role="img" aria-label="{titulo}">{t}{corpo}</svg>')


# ------------------------------------------------------------------ 1. planilha
def planilha() -> str:
    c = []
    c.append(f'<rect x="38" y="14" width="144" height="124" rx="9" fill="{BRANCO}" stroke="{LINHA}" stroke-width="1.5"/>')
    c.append(f'<path d="M38 23a9 9 0 0 1 9-9h126a9 9 0 0 1 9 9v13H38z" fill="{MATA}"/>')
    for i, x in enumerate([102, 124, 146, 168]):
        c.append(f'<rect x="{x-6}" y="22" width="12" height="4" rx="2" fill="{PAPEL}" opacity=".55"/>')
    # linhas: P1, P2, P3 do mesmo paciente e P1 do seguinte
    linhas = [("P1", ["n", "p", "n", "n"]), ("P2", ["n", "p", "p", "n"]),
              ("P3", ["i", "n", "p", "n"]), ("P1", ["n", "n", "n", "n"])]
    for k, (rot, cel) in enumerate(linhas):
        y = 40 + k * 23
        if k % 2 == 0:
            c.append(f'<rect x="39" y="{y}" width="142" height="23" fill="{PAPEL}"/>')
        cor_rot = MATA if k < 3 else TINTA_SUAVE
        c.append(f'<rect x="48" y="{y+5}" width="26" height="13" rx="6.5" fill="{FOLHA_CLARA if k < 3 else LINHA}"/>')
        c.append(f'<text x="61" y="{y+14.6}" text-anchor="middle" font-size="9" fill="{cor_rot}" style="{_TXT}">{rot}</text>')
        c.append(f'<rect x="80" y="{y+9.5}" width="12" height="4" rx="2" fill="{LINHA}"/>')
        for j, s in enumerate(cel):
            cx, cy = 102 + j * 22, y + 11.5
            if s == "p":
                c.append(f'<circle cx="{cx}" cy="{cy}" r="5" fill="{COBRE}"/>')
            elif s == "n":
                c.append(f'<circle cx="{cx}" cy="{cy}" r="5" fill="{FOLHA}"/>')
            else:  # amostra insuficiente: anel tracejado
                c.append(f'<circle cx="{cx}" cy="{cy}" r="4.3" fill="none" stroke="{TINTA_SUAVE}" '
                         f'stroke-width="1.4" stroke-dasharray="2 2"/>')
    # chave que agrupa P1–P3 (um paciente)
    c.append(f'<path d="M34 44v58" stroke="{COBRE}" stroke-width="2" stroke-linecap="round"/>')
    c.append(f'<path d="M34 44h3M34 102h3" stroke="{COBRE}" stroke-width="2" stroke-linecap="round"/>')
    c.append(f'<rect x="146" y="124" width="48" height="20" rx="10" fill="{COBRE}"/>')
    c.append(f'<text x="170" y="137.5" text-anchor="middle" font-size="10" fill="{PAPEL}" style="{_TXT}">.xlsx</text>')
    return _svg("".join(c), titulo="Planilha com uma linha por coleta")


# ------------------------------------------------------------------ 2. configurar
def _ovo_ascaris(cx, cy, cor):
    pts = "".join(
        f'<circle cx="{cx + 15 * __import__("math").cos(a / 10 * 6.2832):.1f}" '
        f'cy="{cy + 10.5 * __import__("math").sin(a / 10 * 6.2832):.1f}" r="2.6" fill="{cor}"/>'
        for a in range(10))
    return (pts + f'<ellipse cx="{cx}" cy="{cy}" rx="14" ry="9.5" fill="{cor}"/>'
            f'<ellipse cx="{cx}" cy="{cy}" rx="8" ry="5" fill="{BRANCO}" opacity=".35"/>')


def _ovo_trichuris(cx, cy, cor):
    return (f'<ellipse cx="{cx}" cy="{cy}" rx="13" ry="8" fill="{cor}"/>'
            f'<rect x="{cx-17.5}" y="{cy-3}" width="5" height="6" rx="2.5" fill="{cor}"/>'
            f'<rect x="{cx+12.5}" y="{cy-3}" width="5" height="6" rx="2.5" fill="{cor}"/>'
            f'<ellipse cx="{cx}" cy="{cy}" rx="8" ry="4" fill="{BRANCO}" opacity=".35"/>')


def _cisto(cx, cy, cor):
    return (f'<ellipse cx="{cx}" cy="{cy}" rx="12" ry="9" fill="none" stroke="{cor}" stroke-width="2.6"/>'
            f'<circle cx="{cx-4}" cy="{cy-2}" r="2.2" fill="{cor}"/><circle cx="{cx+4}" cy="{cy-2}" r="2.2" fill="{cor}"/>'
            f'<circle cx="{cx-4}" cy="{cy+3.2}" r="2.2" fill="{cor}"/><circle cx="{cx+4}" cy="{cy+3.2}" r="2.2" fill="{cor}"/>')


def _toggle(x, y, on):
    fundo = MATA if on else LINHA
    kx = x + 21 if on else x + 9
    return (f'<rect x="{x}" y="{y}" width="30" height="18" rx="9" fill="{fundo}"/>'
            f'<circle cx="{kx}" cy="{y+9}" r="6.5" fill="{BRANCO}"/>')


def configurar() -> str:
    c = [f'<rect x="20" y="14" width="180" height="124" rx="9" fill="{BRANCO}" stroke="{LINHA}" stroke-width="1.5"/>']
    linhas = [(_ovo_ascaris, COBRE, "Patogênico", COBRE_TINT, COBRE, True),
              (_cisto, FOLHA, "Comensal", FOLHA_CLARA, MATA, True),
              (_ovo_trichuris, COBRE, "Patogênico", COBRE_TINT, COBRE, False)]
    for k, (desenho, cor, rot, chip, cor_txt, on) in enumerate(linhas):
        y = 39 + k * 37
        if k:
            c.append(f'<line x1="32" y1="{y-18.5}" x2="188" y2="{y-18.5}" stroke="{LINHA}" stroke-width="1"/>')
        cinza = "#C9C3B5"
        c.append(desenho(52, y, cor if on else cinza))
        if not on:
            chip, cor_txt, rot = PAPEL, TINTA_SUAVE, "Fora da análise"
        c.append(f'<rect x="78" y="{y-9}" width="70" height="18" rx="9" fill="{chip}"/>')
        c.append(f'<text x="113" y="{y+3.6}" text-anchor="middle" font-size="9.5" fill="{cor_txt}" style="{_TXT}">{rot}</text>')
        c.append(_toggle(156, y - 9, on))
    return _svg("".join(c), titulo="Escolha e classificação dos parasitos")


# ------------------------------------------------------------------ 3. prevalência
def prevalencia() -> str:
    c = []
    positivos = {2, 7, 9, 13, 16, 22, 25, 28}
    for i in range(30):
        cx, cy = 28 + (i % 5) * 15, 30 + (i // 5) * 15
        c.append(f'<circle cx="{cx}" cy="{cy}" r="5.4" fill="{COBRE if i in positivos else FOLHA}"/>')
    # seta
    c.append(f'<path d="M106 68h16" stroke="{TINTA_SUAVE}" stroke-width="2" stroke-linecap="round"/>'
             f'<path d="M117 62l6 6-6 6" fill="none" stroke="{TINTA_SUAVE}" stroke-width="2" '
             f'stroke-linecap="round" stroke-linejoin="round"/>')
    # eixo e barras com IC
    base = 122
    c.append(f'<line x1="134" y1="{base}" x2="206" y2="{base}" stroke="{TINTA}" stroke-width="1.5"/>')
    for x, h, cor, lo, hi, rot in [(144, 58, MATA, 44, 74, "Fezes"), (178, 36, FOLHA, 24, 50, "Lâmina")]:
        c.append(f'<rect x="{x}" y="{base-h}" width="22" height="{h}" rx="3" fill="{cor}"/>')
        xm = x + 11
        c.append(f'<path d="M{xm} {base-hi}V{base-lo}M{xm-5} {base-hi}h10M{xm-5} {base-lo}h10" '
                 f'stroke="{COBRE}" stroke-width="2" stroke-linecap="round"/>')
        c.append(f'<text x="{xm}" y="{base+14}" text-anchor="middle" font-size="9.5" fill="{TINTA_SUAVE}" style="{_TXT}">{rot}</text>')
    c.append(f'<rect x="150" y="22" width="48" height="18" rx="9" fill="{COBRE_TINT}"/>'
             f'<text x="174" y="34.6" text-anchor="middle" font-size="9.5" fill="{COBRE}" style="{_TXT}">IC 95%</text>')
    return _svg("".join(c), titulo="Prevalência por paciente com intervalo de confiança")


# ------------------------------------------------------------------ 4. mapa
def mapa() -> str:
    P = dict(A=(42, 40), B=(82, 18), C=(126, 30), D=(152, 70), E=(136, 116), F=(90, 136),
             G=(46, 116), H=(28, 76), I=(86, 56), J=(112, 78), K=(76, 96))
    areas = [("HABIK", 1), ("BCJI", 0), ("CDJ", 2), ("DEJ", 3), ("EFKJ", 2), ("FGHK", 0), ("IJK", 4)]
    c = []
    for nome, cl in areas:
        d = "M" + "L".join(f"{P[p][0]} {P[p][1]}" for p in nome) + "Z"
        c.append(f'<path d="{d}" fill="{RAMPA[cl]}" stroke="{BRANCO}" stroke-width="2" stroke-linejoin="round"/>')
    contorno = "M" + "L".join(f"{P[p][0]} {P[p][1]}" for p in "ABCDEFGH") + "Z"
    c.append(f'<path d="{contorno}" fill="none" stroke="{TINTA}" stroke-width="1.6" stroke-linejoin="round"/>')
    # norte
    c.append(f'<path d="M184 16l7 20-7-5z" fill="{TINTA}"/><path d="M184 16l-7 20 7-5z" fill="none" '
             f'stroke="{TINTA}" stroke-width="1.2" stroke-linejoin="round"/>'
             f'<text x="184" y="50" text-anchor="middle" font-size="10" fill="{TINTA}" style="{_TXT}">N</text>')
    # legenda
    for k, cor in enumerate(RAMPA):
        c.append(f'<rect x="172" y="{62 + k * 11}" width="12" height="9" rx="1.5" fill="{cor}"/>'
                 f'<rect x="188" y="{65.5 + k * 11}" width="{14 - k}" height="2.5" rx="1.25" fill="{LINHA}"/>')
    # escala
    c.append(f'<rect x="150" y="132" width="16" height="5" fill="{TINTA}"/><rect x="166" y="132" width="16" height="5" '
             f'fill="{BRANCO}" stroke="{TINTA}" stroke-width="1"/><rect x="182" y="132" width="16" height="5" fill="{TINTA}"/>')
    return _svg("".join(c), titulo="Mapa de prevalência por território")


# ------------------------------------------------------------------ 5. relatório
def relatorio() -> str:
    c = []
    # Excel (atrás)
    c.append(f'<g transform="rotate(6 140 76)"><rect x="98" y="20" width="84" height="106" rx="7" fill="{BRANCO}" '
             f'stroke="{LINHA}" stroke-width="1.5"/>'
             f'<path d="M98 27a7 7 0 0 1 7-7h70a7 7 0 0 1 7 7v7H98z" fill="{FOLHA}"/>')
    for k in range(5):
        y = 44 + k * 14
        c.append(f'<line x1="104" y1="{y+9}" x2="176" y2="{y+9}" stroke="{LINHA}" stroke-width="1"/>'
                 f'<rect x="106" y="{y+1}" width="22" height="4" rx="2" fill="{LINHA}"/>'
                 f'<rect x="{150 + (k * 7) % 12}" y="{y+1}" width="{18 - (k * 5) % 9}" height="4" rx="2" fill="{FOLHA}"/>')
    c.append(f'<rect x="128" y="106" width="44" height="17" rx="8.5" fill="{FOLHA}"/>'
             f'<text x="150" y="118" text-anchor="middle" font-size="9" fill="{PAPEL}" style="{_TXT}">EXCEL</text></g>')
    # PDF (frente)
    c.append(f'<g transform="rotate(-4 84 82)"><rect x="40" y="26" width="88" height="112" rx="7" fill="{BRANCO}" '
             f'stroke="{LINHA}" stroke-width="1.5"/>'
             f'<rect x="50" y="38" width="48" height="6" rx="3" fill="{MATA}"/>'
             f'<rect x="50" y="49" width="66" height="3.5" rx="1.75" fill="{LINHA}"/>'
             f'<rect x="50" y="56" width="56" height="3.5" rx="1.75" fill="{LINHA}"/>'
             f'<line x1="50" y1="100" x2="118" y2="100" stroke="{TINTA}" stroke-width="1.2"/>')
    for k, h in enumerate([26, 18, 32, 12, 22]):
        c.append(f'<rect x="{53 + k * 13}" y="{100 - h}" width="8" height="{h}" rx="1.5" '
                 f'fill="{COBRE if k == 2 else MATA}"/>')
    c.append(f'<rect x="50" y="108" width="66" height="3.5" rx="1.75" fill="{LINHA}"/>'
             f'<rect x="50" y="115" width="44" height="3.5" rx="1.75" fill="{LINHA}"/>'
             f'<rect x="76" y="122" width="40" height="17" rx="8.5" fill="{COBRE}"/>'
             f'<text x="96" y="134" text-anchor="middle" font-size="9" fill="{PAPEL}" style="{_TXT}">PDF</text></g>')
    # botão de download
    c.append(f'<circle cx="178" cy="128" r="14" fill="{MATA}"/>'
             f'<path d="M178 120v13M172.5 128l5.5 5.5 5.5-5.5M171 137h14" fill="none" stroke="{PAPEL}" '
             f'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>')
    return _svg("".join(c), titulo="Relatório em PDF e Excel")


# ------------------------------------------------------------------ hero: lâmina ao microscópio
def microscopio() -> str:
    """Campo de microscópio com ovos e cistos estilizados sobre o padrão de pontos."""
    import math
    c = ['<defs><clipPath id="pj-campo"><circle cx="110" cy="110" r="96"/></clipPath></defs>']
    c.append(f'<circle cx="110" cy="110" r="104" fill="none" stroke="{MATA_PONTO}" stroke-width="6"/>')
    c.append(f'<circle cx="110" cy="110" r="96" fill="#0D3A31"/>')
    g = ['<g clip-path="url(#pj-campo)">']
    for i in range(9):
        for j in range(9):
            g.append(f'<circle cx="{14 + i * 24}" cy="{14 + j * 24}" r="2.6" fill="{MATA_PONTO}"/>')
    # retículo
    g.append(f'<path d="M110 14V206M14 110H206" stroke="{MATA_PONTO}" stroke-width="1" stroke-dasharray="3 5"/>')
    # Ascaris (casca mamilonada)
    cx, cy = 78, 82
    for a in range(14):
        t = a / 14 * 2 * math.pi
        g.append(f'<circle cx="{cx + 25 * math.cos(t):.1f}" cy="{cy + 19 * math.sin(t):.1f}" r="4" fill="{COBRE_CLARO}"/>')
    g.append(f'<ellipse cx="{cx}" cy="{cy}" rx="23.5" ry="17.5" fill="{COBRE_CLARO}"/>'
             f'<ellipse cx="{cx}" cy="{cy}" rx="14" ry="10" fill="{COBRE}"/>')
    # Trichuris (barril com tampões polares)
    tx, ty = 148, 140
    g.append(f'<g transform="rotate(-28 {tx} {ty})"><ellipse cx="{tx}" cy="{ty}" rx="22" ry="12" fill="{PAPEL}"/>'
             f'<rect x="{tx-29}" y="{ty-4.5}" width="9" height="9" rx="4.5" fill="{PAPEL}"/>'
             f'<rect x="{tx+20}" y="{ty-4.5}" width="9" height="9" rx="4.5" fill="{PAPEL}"/>'
             f'<ellipse cx="{tx}" cy="{ty}" rx="14" ry="6.5" fill="{FOLHA}"/></g>')
    # Enterobius (ovo em "D")
    ex, ey = 150, 66
    g.append(f'<g transform="rotate(18 {ex} {ey})"><path d="M{ex-9} {ey-22}C{ex+16} {ey-20} {ex+16} {ey+20} {ex-9} {ey+22}'
             f'C{ex-15} {ey+10} {ex-15} {ey-10} {ex-9} {ey-22}Z" fill="none" stroke="{PAPEL}" stroke-width="3"/>'
             f'<path d="M{ex-5} {ey-12}C{ex+7} {ey-8} {ex+7} {ey+8} {ex-5} {ey+12}" fill="none" stroke="{COBRE_CLARO}" '
             f'stroke-width="3" stroke-linecap="round"/></g>')
    # cisto (4 núcleos)
    gx, gy = 72, 150
    g.append(f'<ellipse cx="{gx}" cy="{gy}" rx="19" ry="14" fill="none" stroke="{FOLHA}" stroke-width="3.2"/>')
    for dx, dy in [(-6, -4), (6, -4), (-6, 5), (6, 5)]:
        g.append(f'<circle cx="{gx+dx}" cy="{gy+dy}" r="3.2" fill="{FOLHA}"/>')
    # cistos pequenos
    for x, y, r in [(118, 104, 7), (176, 104, 5.5), (112, 176, 6)]:
        g.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="none" stroke="{PAPEL}" stroke-width="2" opacity=".55"/>')
    g.append("</g>")
    c.append("".join(g))
    # brilho da lente
    c.append(f'<path d="M48 52A90 90 0 0 1 96 22" fill="none" stroke="{PAPEL}" stroke-width="3" '
             f'stroke-linecap="round" opacity=".25"/>')
    return _svg("".join(c), 220, 220, classe="pj-hero-ilu", titulo="Lâmina ao microscópio")


ETAPAS = [
    ("Planilha", "Preencha o modelo", "Uma linha por coleta de cada paciente (P1, P2, P3…), com o resultado de cada método.", planilha),
    ("Configuração", "Ajuste a análise", "Escolha os parasitos, marque patogênicos e comensais, e defina métodos, amostras e critérios de inclusão.", configurar),
    ("Análise", "Veja a prevalência", "Por paciente, separada entre fezes e lâmina (Graham), com IC 95% e comparação entre métodos.", prevalencia),
    ("Território · opcional", "Gere o mapa", "Com bairro e município na planilha, o painel mapeia a prevalência no padrão cartográfico.", mapa),
    ("Relatório", "Baixe tudo pronto", "Relatório em PDF e Excel, com tabelas, gráficos e mapa, pronto para o artigo.", relatorio),
]


# ================================================================== ícones (24×24)
def _ico(corpo: str, tam: int = 20) -> str:
    return (f'<svg viewBox="0 0 24 24" width="{tam}" height="{tam}" xmlns="http://www.w3.org/2000/svg" '
            f'aria-hidden="true">{corpo}</svg>')


def ico_parasito(cor=MATA, acento=COBRE) -> str:
    """Verme em S (helminto estilizado) com a extremidade anterior em cobre."""
    return _ico(
        f'<path d="M3.2 17.6C5.4 10.4 9.4 9.6 11.3 13.6S16 18.4 18 10.6" fill="none" stroke="{cor}" '
        f'stroke-width="3.4" stroke-linecap="round"/>'
        f'<circle cx="18.6" cy="7.8" r="3.1" fill="{acento}"/>'
        f'<circle cx="3.2" cy="17.6" r=".9" fill="{PAPEL}"/>')


def ico_microscopio(cor=MATA, acento=COBRE) -> str:
    return _ico(
        f'<rect x="7.6" y="2" width="4.6" height="9.4" rx="1.6" fill="{cor}"/>'
        f'<rect x="8.7" y="11.2" width="2.4" height="2.3" rx=".6" fill="{acento}"/>'
        f'<rect x="4.2" y="14.6" width="9.6" height="2.2" rx="1.1" fill="{cor}"/>'
        f'<path d="M12.2 6.2H14a4.2 4.2 0 0 1 4.2 4.2V19.4" fill="none" stroke="{cor}" stroke-width="2.4" '
        f'stroke-linecap="round"/>'
        f'<rect x="3.4" y="19" width="17.2" height="2.8" rx="1.4" fill="{cor}"/>')


def ico_pote(cor=MATA, acento=COBRE) -> str:
    return _ico(
        f'<rect x="5.4" y="2.6" width="13.2" height="4.4" rx="1.3" fill="{acento}"/>'
        f'<path d="M6.4 8.6h11.2l-.9 11.3a2 2 0 0 1-2 1.8H9.3a2 2 0 0 1-2-1.8z" fill="{cor}"/>'
        f'<rect x="8.9" y="11.6" width="6.2" height="4.6" rx="1" fill="{PAPEL}" opacity=".9"/>')


def ico_criterios(cor=MATA, acento=COBRE) -> str:
    return _ico(
        f'<path d="M2.6 3.4h14.2l-5.3 6.6v5.8l-3.6 2.4v-8.2z" fill="{cor}" stroke="{cor}" stroke-width="1" '
        f'stroke-linejoin="round"/>'
        f'<circle cx="17.6" cy="17.4" r="4.9" fill="{acento}"/>'
        f'<path d="M15.3 17.5l1.6 1.6 3.1-3.2" fill="none" stroke="{PAPEL}" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round"/>')


def ico_visao(cor=MATA, acento=COBRE) -> str:
    c = [f'<rect x="2.5" y="21" width="19" height="1.6" rx=".8" fill="{cor}"/>']
    for x, n, topo_cobre in [(6, 2, False), (12, 4, True), (18, 3, False)]:
        for k in range(n):
            cor_k = acento if (topo_cobre and k == n - 1) else cor
            c.append(f'<circle cx="{x}" cy="{17.6 - k * 4.6}" r="2.05" fill="{cor_k}"/>')
    return _ico("".join(c))


def ico_paciente(cor=MATA, acento=COBRE) -> str:
    return _ico(
        f'<circle cx="7.6" cy="7.6" r="3.4" fill="{cor}"/>'
        f'<path d="M1.8 20a5.8 5.8 0 0 1 11.6 0z" fill="{cor}"/>'
        f'<rect x="15.2" y="6" width="7" height="2.2" rx="1.1" fill="{cor}"/>'
        f'<rect x="15.2" y="11.2" width="7" height="2.2" rx="1.1" fill="{cor}"/>'
        f'<rect x="15.2" y="16.4" width="4.6" height="2.2" rx="1.1" fill="{acento}"/>')


def ico_baixar(cor=MATA, acento=COBRE) -> str:
    return _ico(
        f'<path d="M12 3.2v10.6M7.4 9.6l4.6 4.6 4.6-4.6" fill="none" stroke="{acento}" stroke-width="2.4" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<path d="M3.8 14.6v3.8a2.4 2.4 0 0 0 2.4 2.4h11.6a2.4 2.4 0 0 0 2.4-2.4v-3.8" fill="none" '
        f'stroke="{cor}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>')


def ico_mapa(cor=MATA, acento=COBRE) -> str:
    return _ico(
        f'<path d="M2.4 6.4l6.2-2.2v15.4l-6.2 2.2z" fill="{FOLHA}"/>'
        f'<path d="M8.6 4.2l6.8 2.2v15.4l-6.8-2.2z" fill="{COBRE_CLARO}"/>'
        f'<path d="M15.4 6.4l6.2-2.2v15.4l-6.2 2.2z" fill="{cor}"/>'
        f'<path d="M2.4 6.4l6.2-2.2 6.8 2.2 6.2-2.2v15.4l-6.2 2.2-6.8-2.2-6.2 2.2z" fill="none" '
        f'stroke="{cor}" stroke-width="1.2" stroke-linejoin="round"/>')


ICONES = {
    "parasitos": ico_parasito, "metodos": ico_microscopio, "amostras": ico_pote,
    "criterios": ico_criterios, "visao": ico_visao, "paciente": ico_paciente,
    "baixar": ico_baixar, "mapa": ico_mapa,
}
