from __future__ import annotations
import functools
import re
from io import BytesIO
from pathlib import Path

import streamlit as st


# =============================================================================
# HELPERS DE PRODUTO
# =============================================================================
def qtd_do_kit(tamanho: str) -> int:
    m = re.search(r"(\d+)\s*un", tamanho or "", re.IGNORECASE)
    return int(m.group(1)) if m else 1


def eh_baby(nome: str) -> bool:
    return "Baby" in nome


def eh_tradicional(nome: str) -> bool:
    return "Tradicional" in nome or "Trad." in nome


def _prefixo_variante(nome: str) -> str:
    if eh_baby(nome):
        return "🟠 BABY     "
    if eh_tradicional(nome):
        return "🔵 TRAD.   "
    return "⚪ "


def _nome_curto(nome: str) -> str:
    return (
        nome.replace("Avulsa - ", "")
            .replace(" Tradicional", "")
            .replace(" Baby", "")
            .replace(" Trad.", "")
    )


def label_kit(p: dict) -> str:
    qtd = qtd_do_kit(p["tamanho"])
    return (
        f"{_prefixo_variante(p['nome'])} {_nome_curto(p['nome'])}  "
        f"({qtd} pães)  R$ {p['preco_venda']:.2f}"
    )


def label_avulsa(p: dict) -> str:
    return (
        f"{_prefixo_variante(p['nome'])} {_nome_curto(p['nome'])}  "
        f"R$ {p['preco_venda']:.2f}/un"
    )


def separar_produtos(produtos: list[dict]) -> tuple[list[dict], list[dict]]:
    """Retorna (kits, avulsas), com Tradicionais antes de Baby em cada grupo."""
    def ordenar(lst):
        return (
            [p for p in lst if not eh_baby(p["nome"])]
            + [p for p in lst if eh_baby(p["nome"])]
        )
    kits    = ordenar([p for p in produtos if "Avulsa" not in p["nome"]])
    avulsas = ordenar([p for p in produtos if "Avulsa" in p["nome"]])
    return kits, avulsas


# =============================================================================
# WRAPPER DE SEGURANÇA PARA DB
# =============================================================================
def db_safe(default=None, msg: str = "Erro ao acessar o banco"):
    """
    Envolve uma função de banco em try/except e exibe st.error amigável.
    `default` pode ser um valor ou um callable (para defaults mutáveis).
    Preserva `.clear()` se a função envolvida tiver cache do Streamlit.
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                st.error(f"{msg}: {e}")
                return default() if callable(default) else default
        if hasattr(fn, "clear"):
            wrapper.clear = fn.clear
        return wrapper
    return deco


# =============================================================================
# GERAÇÃO DE CARDÁPIO EM PDF
# =============================================================================
_PALAVRAS_DOCE = (
    "chocolate", "brigadeiro", "doce de leite", "nutella", "goiabada",
    "romeu", "leite ninho", "ninho", "prestígio", "beijinho", "doce",
)
_PALAVRAS_SEM_RECHEIO = ("sem recheio", "sem-recheio", "natural", "puro")


def _categorizar(nome: str) -> str:
    n = nome.lower()
    if any(k in n for k in _PALAVRAS_SEM_RECHEIO):
        return "sem_recheio"
    if any(k in n for k in _PALAVRAS_DOCE):
        return "doces"
    return "salgados"


def gerar_cardapio_pdf(produtos: list[dict]) -> bytes:
    """Gera o cardápio em PDF (bytes) a partir da lista de produtos."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    produtos = [p for p in produtos if "avulsa" not in p["nome"].lower()]

    AMARELO_OURO = colors.HexColor("#F5C518")
    AMARELO      = colors.HexColor("#FFD700")
    MARROM       = colors.HexColor("#4A2C00")
    VERMELHO     = colors.HexColor("#CC0000")
    CREME        = colors.HexColor("#FFF8DC")

    PAGE_W, PAGE_H = A4
    BORDA = 0.6 * cm
    MARGEM = 1.8 * cm

    def _fundo_e_borda(canvas, doc):
        canvas.saveState()
        # fundo amarelo dourado
        canvas.setFillColor(AMARELO_OURO)
        canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        # borda marrom
        canvas.setStrokeColor(MARROM)
        canvas.setLineWidth(3)
        canvas.rect(BORDA, BORDA, PAGE_W - 2 * BORDA, PAGE_H - 2 * BORDA,
                    fill=0, stroke=1)
        # borda interna dourada
        canvas.setStrokeColor(AMARELO)
        canvas.setLineWidth(1.2)
        inner = BORDA + 4
        canvas.rect(inner, inner, PAGE_W - 2 * inner, PAGE_H - 2 * inner,
                    fill=0, stroke=1)
        canvas.restoreState()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGEM, rightMargin=MARGEM,
        topMargin=MARGEM, bottomMargin=MARGEM,
        title="Cardapio - Seu Paozinho",
    )

    base = getSampleStyleSheet()
    estilo_marca = ParagraphStyle(
        "Marca", parent=base["Title"], textColor=MARROM,
        fontSize=16, alignment=1, spaceAfter=2,
        fontName="Helvetica-Bold",
    )
    estilo_titulo = ParagraphStyle(
        "Titulo", parent=base["Title"], textColor=MARROM,
        fontSize=30, alignment=1, spaceAfter=2, spaceBefore=4,
        fontName="Helvetica-Bold",
    )
    estilo_sub = ParagraphStyle(
        "Sub", parent=base["Normal"], textColor=MARROM,
        fontSize=10, alignment=1, spaceAfter=14,
    )
    estilo_rodape = ParagraphStyle(
        "Rodape", parent=base["Normal"], textColor=MARROM,
        fontSize=8, alignment=1, fontName="Helvetica-Bold",
    )

    elems: list = []

    # ── Logo pequena no canto superior direito ──
    logo_path = Path(__file__).resolve().parent / "SeuPaozinho.jpg"
    if logo_path.exists():
        try:
            logo = Image(str(logo_path))
            ratio = logo.imageHeight / logo.imageWidth
            logo_w = 80
            logo.drawWidth = logo_w
            logo.drawHeight = logo_w * ratio
            logo.hAlign = "RIGHT"
            elems.append(logo)
        except Exception:
            pass

    # ── Titulo ──
    elems.append(Paragraph("Seu Paozinho", estilo_marca))
    elems.append(Paragraph("Pao Delicia da Bahia", estilo_sub))
    elems.append(Paragraph("CARDAPIO", estilo_titulo))
    elems.append(Spacer(1, 0.3 * cm))

    # ── Separar produtos por categoria ──
    secoes: dict[str, tuple[str, list[dict]]] = {
        "sem_recheio": ("KIT SEM RECHEIO", []),
        "salgados":    ("RECHEIOS SALGADOS", []),
        "doces":       ("RECHEIOS DOCES", []),
    }
    for p in produtos:
        secoes[_categorizar(p["nome"])][1].append(p)

    largura_util = PAGE_W - 2 * MARGEM

    for chave, (rotulo, lista) in secoes.items():
        if not lista:
            continue

        # ── Cabeçalho de seção: retângulo marrom com texto amarelo ──
        secao_tbl = Table(
            [[rotulo]],
            colWidths=[largura_util],
            rowHeights=[0.7 * cm],
        )
        secao_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), MARROM),
            ("TEXTCOLOR",     (0, 0), (-1, -1), AMARELO),
            ("FONTNAME",      (0, 0), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 12),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        elems.append(Spacer(1, 0.3 * cm))
        elems.append(secao_tbl)

        if chave == "sem_recheio":
            # ── Sem Recheio: linhas separadas ──
            lista_ord = (
                [p for p in lista if not eh_baby(p["nome"])]
                + [p for p in lista if eh_baby(p["nome"])]
            )
            rows = [["Produto", "Variante", "Tamanho", "Preco"]]
            for p in lista_ord:
                if eh_baby(p["nome"]):
                    variante = "Baby (13g/ud)"
                elif eh_tradicional(p["nome"]):
                    variante = "Tradicional (27g/ud)"
                else:
                    variante = "--"
                tamanho = p.get("tamanho") or "--"
                rows.append([
                    _nome_curto(p["nome"]),
                    variante,
                    tamanho,
                    f"R$ {p['preco_venda']:.2f}",
                ])

            tbl = Table(rows, colWidths=[
                5.5 * cm, 4.2 * cm, 3.3 * cm, 3 * cm,
            ])
            tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0), MARROM),
                ("TEXTCOLOR",     (0, 0), (-1, 0), AMARELO),
                ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE",      (0, 0), (-1, -1), 10),
                ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
                ("ALIGN",         (3, 1), (3, -1), "RIGHT"),
                ("GRID",          (0, 0), (-1, -1), 0.3, MARROM),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CREME]),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            elems.append(tbl)

        else:
            # ── Salgados / Doces: duas colunas (Tradicional e Baby) ──
            trads = {_nome_curto(p["nome"]): p
                     for p in lista if eh_tradicional(p["nome"])}
            babys = {_nome_curto(p["nome"]): p
                     for p in lista if eh_baby(p["nome"])}
            todos_nomes = list(dict.fromkeys(
                list(trads.keys()) + list(babys.keys())
            ))

            header_trad = Paragraph(
                '<font color="#CC0000"><b>TRADICIONAL</b></font><br/>'
                '<font size="8">42g/ud</font>',
                ParagraphStyle("_ht", alignment=1, fontSize=10,
                               fontName="Helvetica-Bold", textColor=MARROM),
            )
            header_baby = Paragraph(
                '<font color="#CC0000"><b>BABY</b></font><br/>'
                '<font size="8">21g/ud</font>',
                ParagraphStyle("_hb", alignment=1, fontSize=10,
                               fontName="Helvetica-Bold", textColor=MARROM),
            )

            rows = [["Recheio", header_trad, header_baby]]
            for nome in todos_nomes:
                pt = trads.get(nome)
                pb = babys.get(nome)
                preco_t = f"R$ {pt['preco_venda']:.2f}" if pt else "--"
                preco_b = f"R$ {pb['preco_venda']:.2f}" if pb else "--"
                rows.append([nome, preco_t, preco_b])

            tbl = Table(rows, colWidths=[
                largura_util * 0.46, largura_util * 0.27, largura_util * 0.27,
            ])
            tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0), AMARELO),
                ("TEXTCOLOR",     (0, 0), (0, 0), MARROM),
                ("FONTNAME",      (0, 0), (0, 0), "Helvetica-Bold"),
                ("FONTNAME",      (0, 1), (0, -1), "Helvetica-Bold"),
                ("FONTNAME",      (1, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE",      (0, 0), (-1, -1), 10),
                ("ALIGN",         (1, 0), (-1, -1), "CENTER"),
                ("ALIGN",         (0, 0), (0, -1), "LEFT"),
                ("GRID",          (0, 0), (-1, -1), 0.3, MARROM),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CREME]),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            elems.append(tbl)

    # ── Rodapé ──
    elems.append(Spacer(1, 0.8 * cm))
    elems.append(Paragraph(
        "@seu.paozinho  --  (85) 98141-4010  --  "
        "O pao delicia artesanal que aquece seu coracao",
        estilo_rodape,
    ))

    doc.build(elems, onFirstPage=_fundo_e_borda, onLaterPages=_fundo_e_borda)
    return buf.getvalue()
