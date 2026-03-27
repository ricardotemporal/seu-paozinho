import streamlit as st
import re
from datetime import date, timedelta
import pandas as pd

from database import (
    atualizar_produto,
    buscar_historico,
    buscar_metricas,
    buscar_produtos,
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
    .stButton > button {
        height: 3rem;
        font-size: 1rem;
        font-weight: 600;
    }
    [data-testid="metric-container"] {
        background-color: #f9f9f9;
        border-radius: 12px;
        padding: 12px;
        border: 1px solid #eee;
    }
    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# HELPERS
# =============================================================================
def qtd_do_kit(tamanho: str) -> int:
    """Extrai número de unidades do campo tamanho. Ex: 'Kit 10 un' → 10."""
    m = re.search(r"(\d+)\s*un", tamanho or "", re.IGNORECASE)
    return int(m.group(1)) if m else 1


def label_kit(p: dict) -> str:
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
        # Separa kits e avulsas direto do banco
        kits    = [p for p in produtos if "Avulsa" not in p["nome"]]
        avulsas = [p for p in produtos if "Avulsa" in p["nome"]]

        # ── Kits (opcional) ──────────────────────────────────────────────────
        adicionar_kit  = st.checkbox("Adicionar kit(s)?", value=True)
        produto        = None
        qtd_kits       = 0
        valor_kits     = 0.0

        if adicionar_kit:
            labels_kit = [label_kit(p) for p in kits]
            idx = st.radio(
                "Escolha o kit:",
                range(len(labels_kit)),
                format_func=lambda i: labels_kit[i],
                key="radio_kit",
            )
            produto    = kits[idx]
            qtd_kits   = st.number_input("Quantidade de kits:", min_value=1, value=1, step=1)
            valor_kits = produto["preco_venda"] * qtd_kits

        # ── Avulsas (opcional) ───────────────────────────────────────────────
        st.markdown("---")
        adicionar_avulsa = st.checkbox("Adicionar unidades avulsas?")
        avulsa_sel       = None
        qtd_avulsa       = 0
        valor_avulsa     = 0.0

        if adicionar_avulsa:
            # Avulsas vêm do banco com preço e custo por unidade já corretos
            labels_av = [
                f"{p['nome'].replace('Avulsa - ', '')}  —  R$ {p['preco_venda']:.2f}/un"
                for p in avulsas
            ]
            idx_av = st.radio(
                "Sabor da avulsa:",
                range(len(labels_av)),
                format_func=lambda i: labels_av[i],
                key="radio_avulsa",
            )
            avulsa_sel   = avulsas[idx_av]
            qtd_avulsa   = st.number_input("Quantas unidades avulsas?", min_value=1, value=1, step=1)
            valor_avulsa = avulsa_sel["preco_venda"] * qtd_avulsa

        # ── Total em tempo real ──────────────────────────────────────────────
        valor_total = valor_kits + valor_avulsa
        st.markdown(f"### 💵 Total: R$ {valor_total:.2f}")

        detalhes = []
        if valor_kits > 0 and produto:
            detalhes.append(f"{qtd_kits} kit(s) {produto['nome']}: R$ {valor_kits:.2f}")
        if valor_avulsa > 0 and avulsa_sel:
            detalhes.append(
                f"{qtd_avulsa} avulsa(s) "
                f"{avulsa_sel['nome'].replace('Avulsa - ', '')}: R$ {valor_avulsa:.2f}"
            )
        if len(detalhes) > 1:
            st.caption("  +  ".join(detalhes))

        # ── Registrar ────────────────────────────────────────────────────────
        sem_item = not adicionar_kit and not adicionar_avulsa
        if sem_item:
            st.warning("Selecione ao menos um kit ou uma unidade avulsa.")

        if st.button("✅ Registrar Venda", use_container_width=True, disabled=sem_item):
            if adicionar_kit and produto and qtd_kits > 0:
                salvar_venda(produto["id"], qtd_kits, valor_kits, tipo="kit")
            if adicionar_avulsa and avulsa_sel and qtd_avulsa > 0:
                # FIX: usa o ID do produto avulso próprio (não mais o kit_id)
                salvar_venda(avulsa_sel["id"], qtd_avulsa, valor_avulsa, tipo="avulsa")
            st.success(f"Venda registrada! **R$ {valor_total:.2f}**")
            st.rerun()  # FIX: removido st.balloons() antes do rerun


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
        colunas_visiveis = ["ID", "Data", "Tipo", "Produto", "Qtd", "Total (R$)"]
        st.dataframe(df[colunas_visiveis], hide_index=True, use_container_width=True)
        st.caption(f"{len(df)} venda(s) encontrada(s).")

        st.divider()

        with st.expander("✏️ Editar uma venda"):
            with st.form("form_editar_venda"):
                id_editar = st.number_input("ID da venda:", min_value=1, step=1, key="id_ed")
                linha     = df[df["ID"] == id_editar]
                preco_unit_atual = float(linha["_preco_unit"].values[0]) if not linha.empty else 0.0
                qtd_atual        = int(linha["Qtd"].values[0])           if not linha.empty else 1

                nova_qtd   = st.number_input("Nova quantidade:", min_value=1, value=qtd_atual, step=1)
                novo_total = preco_unit_atual * nova_qtd
                st.caption(f"Novo total: **R$ {novo_total:.2f}**")

                if st.form_submit_button("💾 Salvar edição", use_container_width=True):
                    editar_venda(int(id_editar), nova_qtd, novo_total)
                    st.success(f"Venda #{int(id_editar)} atualizada!")
                    st.rerun()

        with st.expander("🗑️ Excluir uma venda"):
            with st.form("form_excluir"):
                id_excluir = st.number_input("ID da venda:", min_value=1, step=1, key="id_ex")
                if st.form_submit_button("🗑️ Excluir", use_container_width=True):
                    excluir_venda(int(id_excluir))
                    st.success(f"Venda #{int(id_excluir)} excluída!")
                    st.rerun()


# ── ABA 4: GERENCIAR PRODUTOS ────────────────────────────────────────────────
with aba_gerenciar:
    st.subheader("Cardápio e Custos")
    st.info("Consulte a tabela e atualize os valores quando necessário.")

    produtos = buscar_produtos()
    if produtos:
        # Exibe kits e avulsas em seções separadas
        kits_tab    = [p for p in produtos if "Avulsa" not in p["nome"]]
        avulsas_tab = [p for p in produtos if "Avulsa" in p["nome"]]

        st.markdown("**🧺 Kits**")
        df_kits = pd.DataFrame(kits_tab)[["id", "nome", "tamanho", "preco_venda", "custo_estimado"]]
        df_kits.columns = ["ID", "Produto", "Tamanho", "Preço (R$)", "Custo (R$)"]
        st.dataframe(df_kits, hide_index=True, use_container_width=True)

        st.markdown("**🍞 Avulsas**")
        df_avulsas = pd.DataFrame(avulsas_tab)[["id", "nome", "preco_venda", "custo_estimado"]]
        df_avulsas.columns = ["ID", "Produto", "Preço/un (R$)", "Custo/un (R$)"]
        st.dataframe(df_avulsas, hide_index=True, use_container_width=True)

        st.divider()
        st.markdown("**Editar produto:**")

        nomes_prod = [f"[{p['id']}] {p['nome']} ({p['tamanho']})" for p in produtos]

        with st.form("form_editar_prod"):
            escolha  = st.selectbox("Selecione o produto:", nomes_prod)
            idx_prod = nomes_prod.index(escolha)
            prod     = produtos[idx_prod]

            st.caption(
                f"Valores atuais → Preço: R$ {prod['preco_venda']:.2f}  |  "
                f"Custo: R$ {prod['custo_estimado']:.2f}"
            )

            cA, cB = st.columns(2)
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

            if st.form_submit_button("💾 Salvar alterações", use_container_width=True):
                atualizar_produto(prod["id"], novo_preco, novo_custo)
                st.success(f"✅ '{prod['nome']}' atualizado!")
                st.rerun()