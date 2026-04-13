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

    AMARELO = colors.HexColor("#FFD700")
    MARROM  = colors.HexColor("#4A2C00")
    CREME   = colors.HexColor("#FFF8DC")

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title="Cardápio — Seu Pãozinho",
    )

    base = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle(
        "Titulo", parent=base["Title"], textColor=MARROM,
        fontSize=28, alignment=1, spaceAfter=4,
        fontName="Helvetica-Bold",
    )
    estilo_sub = ParagraphStyle(
        "Sub", parent=base["Normal"], textColor=MARROM,
        fontSize=12, alignment=1, spaceAfter=18,
    )
    estilo_secao = ParagraphStyle(
        "Secao", parent=base["Heading2"], textColor=MARROM,
        fontSize=16, spaceBefore=14, spaceAfter=8,
        fontName="Helvetica-Bold",
    )
    estilo_rodape = ParagraphStyle(
        "Rodape", parent=base["Normal"], textColor=MARROM,
        fontSize=9, alignment=1,
    )

    elems: list = []
    logo_path = Path(__file__).resolve().parent / "SeuPaozinho.jpg"
    if logo_path.exists():
        try:
            logo = Image(str(logo_path))
            ratio = logo.imageHeight / logo.imageWidth
            logo.drawWidth = 180
            logo.drawHeight = 180 * ratio
            logo.hAlign = "CENTER"
            elems.append(logo)
            elems.append(Spacer(1, 0.3 * cm))
        except Exception:
            pass
    elems.append(Paragraph("Seu Pãozinho 🍞", estilo_titulo))
    elems.append(Paragraph("Pão Delícia da Bahia — Cardápio", estilo_sub))

    secoes: dict[str, tuple[str, list[dict]]] = {
        "sem_recheio": ("Kit Sem Recheio", []),
        "salgados":    ("Recheios Salgados", []),
        "doces":       ("Recheios Doces", []),
    }
    for p in produtos:
        secoes[_categorizar(p["nome"])][1].append(p)

    for _, (rotulo, lista) in secoes.items():
        if not lista:
            continue
        elems.append(Paragraph(rotulo, estilo_secao))

        lista_ord = (
            [p for p in lista if not eh_baby(p["nome"])]
            + [p for p in lista if eh_baby(p["nome"])]
        )

        rows = [["Produto", "Variante", "Tamanho", "Preço"]]
        for p in lista_ord:
            if eh_baby(p["nome"]):
                variante = "Baby (13g)"
            elif eh_tradicional(p["nome"]):
                variante = "Tradicional (42g)"
            else:
                variante = "—"
            tamanho = p.get("tamanho") or (
                "1 unidade" if "Avulsa" in p["nome"] else "—"
            )
            rows.append([
                _nome_curto(p["nome"]),
                variante,
                tamanho,
                f"R$ {p['preco_venda']:.2f}",
            ])

        tbl = Table(rows, colWidths=[5.8 * cm, 4 * cm, 3.5 * cm, 2.7 * cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0), MARROM),
            ("TEXTCOLOR",   (0, 0), (-1, 0), AMARELO),
            ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",    (0, 0), (-1, -1), 10),
            ("ALIGN",       (3, 1), (3, -1), "RIGHT"),
            ("ALIGN",       (0, 0), (-1, 0), "CENTER"),
            ("GRID",        (0, 0), (-1, -1), 0.3, MARROM),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CREME]),
            ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",(0, 0), (-1, -1), 8),
            ("TOPPADDING",  (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ]))
        elems.append(tbl)

    elems.append(Spacer(1, 1 * cm))
    elems.append(Paragraph(
        "📱 Contato: (inserir telefone/Instagram)  •  "
        "O pão delícia artesanal que aquece seu coração 🍞",
        estilo_rodape,
    ))

    doc.build(elems)
    return buf.getvalue()
