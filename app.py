import re
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from database import (
    buscar_historico,
    buscar_metricas,
    buscar_produtos,
    atualizar_produto,
    editar_venda,
    excluir_venda,
    salvar_venda,
)

# =============================================================================
# CONFIGURAÇÃO DA PÁGINA
# =============================================================================
st.set_page_config(
    page_title="Seu Pãozinho 🍞",
    page_icon="🍞",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .stButton > button          { height: 3rem; font-size: 1rem; font-weight: 600; }
    [data-testid="metric-container"] {
        background-color: #f9f9f9;
        border-radius: 12px;
        padding: 12px;
        border: 1px solid #eee;
    }
    /* Remove foco automático que abre teclado no Android */
    [data-baseweb="select"] input { display: none !important; }
    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# HELPERS
# =============================================================================
def qtd_do_kit(tamanho: str) -> int:
    """Extrai o número de unidades de um campo 'tamanho'. Ex: '10 un' → 10."""
    m = re.search(r"(\d+)\s*un", tamanho or "", re.IGNORECASE)
    return int(m.group(1)) if m else 1


def label_kit(p: dict) -> str:
    """Monta o label do selectbox/radio: 'Nome (10 pães) — R$ 32,00'"""
    return f"{p['nome']}  ({qtd_do_kit(p['tamanho'])} pães)  —  R$ {p['preco_venda']:.2f}"


def seletor_periodo(chave: str) -> tuple[date, date]:
    hoje  = date.today()
    opcoes = {
        "📅 Hoje":          (hoje, hoje),
        "🗓️ Esta semana":   (hoje - timedelta(days=hoje.weekday()), hoje),
        "📆 Este mês":      (hoje.replace(day=1), hoje),
        "🗃️ Tudo":          (date(2000, 1, 1), hoje),
        "✏️ Personalizado": None,
    }
    escolha = st.radio("Período:", list(opcoes.keys()), horizontal=True, key=f"radio_{chave}")
    if opcoes[escolha] is not None:
        return opcoes[escolha]
    c1, c2 = st.columns(2)
    with c1:
        inicio = st.date_input("De:", value=hoje.replace(day=1), key=f"di_{chave}")
    with c2:
        fim = st.date_input("Até:", value=hoje, key=f"df_{chave}")
    return inicio, fim


# =============================================================================
# INTERFACE
# =============================================================================
st.title("🍞 Seu Pãozinho")

aba_vendas, aba_dashboard, aba_historico, aba_gerenciar = st.tabs([
    "💰 Venda", "📊 Dashboard", "📝 Histórico", "⚙️ Produtos",
])

# ── ABA 1: LANÇAMENTO DE VENDA ───────────────────────────────────────────────
with aba_vendas:
    st.subheader("Registrar Venda")
    produtos = buscar_produtos()

    if not produtos:
        st.warning("Nenhum produto cadastrado.")
    else:
        kits = [p for p in produtos if "Avulsa" not in p["nome"]]

        # ── Seleção de kit via radio (sem teclado no Android) ──
        labels_kit = [label_kit(p) for p in kits]
        idx = st.radio(
            "Escolha o kit:",
            range(len(labels_kit)),
            format_func=lambda i: labels_kit[i],
            key="radio_kit",
        )
        produto  = kits[idx]
        qtd_kits = st.number_input("Quantidade de kits:", min_value=1, value=1, step=1)

        # ── Unidades avulsas: todas as opções com preço calculado ──
        st.markdown("---")
        st.markdown("**Unidades avulsas extras** *(para completar pedidos quebrados)*")

        # Monta lista de avulsas com preço = preco_venda / qtd_do_kit
        avulsas = []
        for p in kits:
            qtd = qtd_do_kit(p["tamanho"])
            preco_unit = round(p["preco_venda"] / qtd, 2)
            # Simplifica o nome: retira "Tradicional"/"Baby" para label mais curto
            nome_curto = p["nome"].replace(" Tradicional", " Trad.").replace(" Traditional", " Trad.")
            avulsas.append({
                "label":      f"{nome_curto}  —  R$ {preco_unit:.2f}/un",
                "preco_unit": preco_unit,
                "nome":       p["nome"],
                "kit_id":     p["id"],   # referenciamos o produto-pai
            })

        # Mostra selectbox só se o usuário quiser avulsas
        adicionar_avulsa = st.checkbox("Adicionar unidades avulsas?")
        qtd_avulsa   = 0
        avulsa_sel   = None

        if adicionar_avulsa:
            labels_av = [a["label"] for a in avulsas]
            idx_av    = st.radio(
                "Sabor da avulsa:",
                range(len(labels_av)),
                format_func=lambda i: labels_av[i],
                key="radio_avulsa",
            )
            avulsa_sel = avulsas[idx_av]
            qtd_avulsa = st.number_input("Quantas unidades avulsas?", min_value=1, value=1, step=1)

        # ── Total em tempo real ──
        valor_kits   = produto["preco_venda"] * qtd_kits
        valor_avulsa = (avulsa_sel["preco_unit"] * qtd_avulsa) if avulsa_sel else 0
        valor_total  = valor_kits + valor_avulsa

        st.markdown(f"### 💵 Total: R$ {valor_total:.2f}")
        if valor_avulsa > 0:
            st.caption(
                f"Kits: R$ {valor_kits:.2f}  +  "
                f"{qtd_avulsa} avulsa(s) {avulsa_sel['nome']}: R$ {valor_avulsa:.2f}"
            )

        if st.button("✅ Registrar Venda", use_container_width=True):
            salvar_venda(produto["id"], qtd_kits, valor_kits)
            if avulsa_sel and qtd_avulsa > 0:
                # Registra a avulsa referenciando o produto-kit correspondente
                salvar_venda(avulsa_sel["kit_id"], qtd_avulsa, valor_avulsa)
            st.success(f"Venda registrada! **R$ {valor_total:.2f}**")
            st.balloons()


# ── ABA 2: DASHBOARD ─────────────────────────────────────────────────────────
with aba_dashboard:
    st.subheader("Resumo Financeiro")
    data_ini, data_fim = seletor_periodo("dash")
    faturamento, custo, lucro = buscar_metricas(data_ini, data_fim)
    margem = (lucro / faturamento * 100) if faturamento > 0 else 0

    c1, c2 = st.columns(2)
    c3, c4 = st.columns(2)
    c1.metric("💰 Faturamento",  f"R$ {faturamento:,.2f}")
    c2.metric("🧾 Custos (CMV)", f"R$ {custo:,.2f}")
    c3.metric("📈 Lucro Bruto",  f"R$ {lucro:,.2f}")
    c4.metric("📊 Margem",       f"{margem:.1f}%")

    if faturamento == 0:
        st.info("Nenhuma venda no período.")


# ── ABA 3: HISTÓRICO ─────────────────────────────────────────────────────────
with aba_historico:
    st.subheader("Histórico de Vendas")
    data_ini, data_fim = seletor_periodo("hist")
    df = buscar_historico(data_ini, data_fim)

    if df.empty:
        st.info("Nenhuma venda no período selecionado.")
    else:
        # Exibe só as colunas visíveis
        colunas_visiveis = ["ID", "Data", "Produto", "Qtd", "Total (R$)"]
        st.dataframe(df[colunas_visiveis], hide_index=True, use_container_width=True)
        st.caption(f"{len(df)} venda(s) encontrada(s).")

        st.divider()

        # ── Editar venda ──
        with st.expander("✏️ Editar uma venda"):
            with st.form("form_editar_venda"):
                id_editar = st.number_input("ID da venda:", min_value=1, step=1, key="id_ed")

                # Busca os dados da venda selecionada para pré-preencher
                linha = df[df["ID"] == id_editar]
                preco_unit_atual = float(linha["_preco_unit"].values[0]) if not linha.empty else 0.0
                qtd_atual        = int(linha["Qtd"].values[0])           if not linha.empty else 1

                nova_qtd = st.number_input(
                    "Nova quantidade:", min_value=1, value=qtd_atual, step=1
                )
                novo_total = preco_unit_atual * nova_qtd
                st.caption(f"Novo total calculado: **R$ {novo_total:.2f}**")

                if st.form_submit_button("💾 Salvar edição", use_container_width=True):
                    editar_venda(int(id_editar), nova_qtd, novo_total)
                    st.success(f"Venda #{int(id_editar)} atualizada! Atualize a página.")

        # ── Excluir venda ──
        with st.expander("🗑️ Excluir uma venda"):
            with st.form("form_excluir"):
                id_excluir = st.number_input("ID da venda:", min_value=1, step=1, key="id_ex")
                if st.form_submit_button("🗑️ Excluir", use_container_width=True):
                    excluir_venda(int(id_excluir))
                    st.success(f"Venda #{int(id_excluir)} excluída. Atualize a página.")


# ── ABA 4: GERENCIAR PRODUTOS ────────────────────────────────────────────────
with aba_gerenciar:
    st.subheader("Cardápio e Custos")
    st.info("Consulte a tabela e atualize os valores quando necessário.")

    produtos = buscar_produtos()
    if produtos:
        df_prod = pd.DataFrame(produtos)[
            ["id", "nome", "tamanho", "preco_venda", "custo_estimado"]
        ]
        df_prod.columns = ["ID", "Produto", "Tamanho", "Preço (R$)", "Custo (R$)"]
        st.dataframe(df_prod, hide_index=True, use_container_width=True)

        st.divider()
        st.markdown("**Editar produto:**")
        opcoes_edit = {f"{p['nome']} ({p['tamanho']})": p for p in produtos}

        with st.form("form_editar_prod"):
            prod_edit  = st.selectbox("Selecione:", list(opcoes_edit.keys()))
            prod       = opcoes_edit[prod_edit]
            cA, cB     = st.columns(2)
            with cA:
                novo_preco = st.number_input(
                    "Novo Preço (R$):", min_value=0.0,
                    value=float(prod["preco_venda"]), format="%.2f"
                )
            with cB:
                novo_custo = st.number_input(
                    "Novo Custo (R$):", min_value=0.0,
                    value=float(prod["custo_estimado"]), format="%.2f"
                )
            if st.form_submit_button("💾 Salvar", use_container_width=True):
                atualizar_produto(prod["id"], novo_preco, novo_custo)
                st.success("Produto atualizado! Atualize a página para ver.")