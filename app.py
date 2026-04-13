from datetime import date, timedelta

import pandas as pd
import streamlit as st

from database import (
    atualizar_produto,
    buscar_historico,
    buscar_metricas,
    buscar_produtos,
    editar_venda,
    excluir_venda,
    salvar_venda,
)
from utils import (
    eh_baby,
    gerar_cardapio_pdf,
    label_avulsa,
    label_kit,
    separar_produtos,
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
# HELPERS LOCAIS
# =============================================================================
def seletor_periodo(chave: str) -> tuple[date, date]:
    hoje = date.today()
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

aba_vendas, aba_dashboard, aba_historico, aba_gerenciar, aba_cardapio = st.tabs([
    "💰 Venda", "📊 Dashboard", "📝 Histórico", "⚙️ Produtos", "📄 Cardápio",
])

# ── ABA 1: LANÇAMENTO DE VENDA ───────────────────────────────────────────────
if "carrinho" not in st.session_state:
    st.session_state.carrinho = []

with aba_vendas:
    st.subheader("Registrar Venda")
    produtos = buscar_produtos()

    if not produtos:
        st.warning("Nenhum produto cadastrado.")
    else:
        kits, avulsas = separar_produtos(produtos)

        st.caption("🔵 TRAD. = Tradicional (10 pães)   |   🟠 BABY = Baby (20 pães)")
        st.divider()

        # ── Adicionar item ao pedido ─────────────────────────────────────────
        tipo_item = st.radio(
            "Tipo de item:",
            ["🧺 Kit", "🍞 Avulsa"],
            horizontal=True,
            key="tipo_item",
        )

        personalizado = False
        gramatura = None
        preco_combinado = 0.0

        if tipo_item == "🧺 Kit":
            idx = st.radio(
                "Escolha o kit:",
                range(len(kits)),
                format_func=lambda i: label_kit(kits[i]),
                key="radio_kit",
            )
            produto_sel = kits[idx]

            personalizado = st.checkbox(
                "✏️ Pedido personalizado (gramatura maior)?",
                key="chk_personalizado",
            )

            if personalizado:
                st.info(
                    "Pedidos personalizados exigem **mínimo de 6 unidades**. "
                    "Padrão atual: Tradicional 42g • Baby 13g."
                )
                gramatura_padrao = 13 if eh_baby(produto_sel["nome"]) else 42
                cg1, cg2 = st.columns(2)
                with cg1:
                    gramatura = st.number_input(
                        "Gramatura desejada (g/unidade):",
                        min_value=1, value=gramatura_padrao, step=1,
                        key="gramatura_pers",
                    )
                with cg2:
                    preco_combinado = st.number_input(
                        "Preço combinado (R$/unidade):",
                        min_value=0.0, value=0.0, step=0.50,
                        format="%.2f", key="preco_pers",
                    )

            qtd_item = st.number_input(
                "Quantidade:", min_value=1, value=1, step=1, key="qtd_item",
            )

            if personalizado:
                valor_item = preco_combinado * qtd_item
                tipo_db    = "personalizado"
            else:
                valor_item = produto_sel["preco_venda"] * qtd_item
                tipo_db    = "kit"
        else:
            idx_av = st.radio(
                "Sabor da avulsa:",
                range(len(avulsas)),
                format_func=lambda i: label_avulsa(avulsas[i]),
                key="radio_avulsa",
            )
            produto_sel = avulsas[idx_av]
            qtd_item    = st.number_input("Quantidade:", min_value=1, value=1, step=1, key="qtd_avulsa")
            valor_item  = produto_sel["preco_venda"] * qtd_item
            tipo_db     = "avulsa"

        st.caption(f"Subtotal: **R$ {valor_item:.2f}**")

        # Validação do pedido personalizado
        bloqueio_personalizado = False
        if personalizado:
            if qtd_item < 6:
                st.warning("⚠️ Pedido personalizado exige no mínimo 6 unidades.")
                bloqueio_personalizado = True
            if preco_combinado <= 0:
                st.warning("⚠️ Informe o preço combinado com o cliente.")
                bloqueio_personalizado = True

        if st.button(
            "➕ Adicionar ao pedido",
            use_container_width=True,
            disabled=bloqueio_personalizado,
        ):
            item = {
                "produto_id":  produto_sel["id"],
                "nome":        produto_sel["nome"],
                "quantidade":  qtd_item,
                "valor_total": valor_item,
                "tipo":        tipo_db,
                "observacao":  f"{int(gramatura)}g/unidade" if personalizado else None,
            }
            st.session_state.carrinho.append(item)
            st.rerun()

        # ── Carrinho ─────────────────────────────────────────────────────────
        st.markdown("---")
        carrinho = st.session_state.carrinho

        icones_tipo = {"kit": "🧺", "avulsa": "🍞", "personalizado": "✏️"}

        if carrinho:
            st.markdown("### 🛒 Pedido atual")
            total_itens = 0.0
            for i, item in enumerate(carrinho):
                icone = icones_tipo.get(item["tipo"], "•")
                obs   = f" _({item['observacao']})_" if item.get("observacao") else ""
                col_desc, col_btn = st.columns([5, 1])
                with col_desc:
                    st.caption(
                        f"{icone} {item['quantidade']}x {item['nome']}{obs}  —  "
                        f"R$ {item['valor_total']:.2f}"
                    )
                with col_btn:
                    if st.button("🗑️", key=f"rm_{i}"):
                        st.session_state.carrinho.pop(i)
                        st.rerun()
                total_itens += item["valor_total"]
        else:
            total_itens = 0.0

        # ── Frete (opcional) ─────────────────────────────────────────────────
        st.markdown("---")
        tem_frete = st.checkbox("Tem entrega com frete?")
        frete_cobrado = 0.0
        frete_real    = 0.0

        if tem_frete:
            st.caption("Informe o que você cobrou e o que pagou no app de entrega.")
            cf1, cf2 = st.columns(2)
            with cf1:
                frete_cobrado = st.number_input(
                    "💰 Cobrado do cliente (R$):",
                    min_value=0.0, value=10.0, step=0.50, format="%.2f",
                )
            with cf2:
                frete_real = st.number_input(
                    "📱 Pago no app (R$):",
                    min_value=0.0, value=0.0, step=0.50, format="%.2f",
                )
            lucro_frete_now = frete_cobrado - frete_real
            if lucro_frete_now > 0:
                st.caption(f"✅ Você ganha **R$ {lucro_frete_now:.2f}** com o frete.")
            elif lucro_frete_now < 0:
                st.warning(f"⚠️ Você está pagando R$ {abs(lucro_frete_now):.2f} a mais do que cobra!")
            else:
                st.caption("Frete empatado — sem lucro nem prejuízo.")

        valor_total = total_itens + frete_cobrado
        st.markdown(f"### 💵 Total do pedido: R$ {valor_total:.2f}")

        pedido_vazio = len(carrinho) == 0 and not tem_frete
        if pedido_vazio:
            st.warning("Adicione ao menos um item ou um frete ao pedido.")

        if st.button("✅ Registrar Venda", use_container_width=True, disabled=pedido_vazio):
            primeiro = True
            for item in carrinho:
                salvar_venda(
                    item["produto_id"], item["quantidade"], item["valor_total"],
                    tipo=item["tipo"],
                    frete_cobrado=frete_cobrado if primeiro else 0,
                    frete_real=frete_real if primeiro else 0,
                    observacao=item.get("observacao"),
                )
                primeiro = False
            if primeiro and tem_frete:
                salvar_venda(
                    None, 0, 0.0, tipo="frete",
                    frete_cobrado=frete_cobrado,
                    frete_real=frete_real,
                )
            st.session_state.carrinho = []
            st.toast(f"Venda registrada! R$ {valor_total:.2f}", icon="✅")
            st.balloons()
            st.rerun()


# ── ABA 2: DASHBOARD ─────────────────────────────────────────────────────────
with aba_dashboard:
    st.subheader("Resumo Financeiro")
    data_ini, data_fim = seletor_periodo("dash")
    m = buscar_metricas(data_ini, data_fim)

    faturamento = m["faturamento"]
    custo       = m["custo"]
    lucro       = m["lucro"]
    lucro_frete = m["lucro_frete"]
    margem      = (lucro / faturamento * 100) if faturamento > 0 else 0

    c1, c2 = st.columns(2)
    c3, c4 = st.columns(2)
    c5, _  = st.columns(2)

    c1.metric("💰 Faturamento",    f"R$ {faturamento:,.2f}")
    c2.metric("🧾 Custos (CMV)",   f"R$ {custo:,.2f}")
    c3.metric("📈 Lucro Bruto",    f"R$ {lucro:,.2f}")
    c4.metric("📊 Margem",         f"{margem:.1f}%")
    c5.metric("🚗 Lucro c/ Frete", f"R$ {lucro_frete:,.2f}")

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
        colunas_visiveis = ["ID", "Data", "Tipo", "Produto", "Qtd", "Produtos (R$)", "Frete"]
        st.dataframe(df[colunas_visiveis], hide_index=True, use_container_width=True)
        st.caption(f"{len(df)} venda(s) encontrada(s).")

        st.divider()

        with st.expander("✏️ Editar uma venda"):
            with st.form("form_editar_venda"):
                id_editar        = st.number_input("ID da venda:", min_value=1, step=1, key="id_ed")
                linha            = df[df["ID"] == id_editar]
                preco_unit_atual = float(linha["_preco_unit"].values[0]) if not linha.empty else 0.0
                qtd_atual        = int(linha["Qtd"].values[0])           if not linha.empty else 1
                fc_atual         = float(linha["_frete_cobrado"].values[0]) if not linha.empty else 0.0
                fr_atual         = float(linha["_frete_real"].values[0])    if not linha.empty else 0.0

                nova_qtd   = st.number_input("Nova quantidade:", min_value=0, value=qtd_atual, step=1)
                novo_total = preco_unit_atual * nova_qtd
                st.caption(f"Novo total produtos: **R$ {novo_total:.2f}**")

                st.markdown("---")
                st.caption("Frete (deixe 0 se não houver)")
                ce1, ce2 = st.columns(2)
                with ce1:
                    novo_fc = st.number_input(
                        "Cobrado (R$):", min_value=0.0, value=fc_atual,
                        step=0.50, format="%.2f", key="ed_fc",
                    )
                with ce2:
                    novo_fr = st.number_input(
                        "Pago no app (R$):", min_value=0.0, value=fr_atual,
                        step=0.50, format="%.2f", key="ed_fr",
                    )

                if st.form_submit_button("💾 Salvar edição", use_container_width=True):
                    editar_venda(
                        int(id_editar), nova_qtd, novo_total,
                        novo_frete_cobrado=novo_fc,
                        novo_frete_real=novo_fr,
                    )
                    st.toast(f"Venda #{int(id_editar)} atualizada!", icon="✅")
                    st.rerun()

        with st.expander("🗑️ Excluir uma venda"):
            with st.form("form_excluir"):
                id_excluir = st.number_input("ID da venda:", min_value=1, step=1, key="id_ex")
                if st.form_submit_button("🗑️ Excluir", use_container_width=True):
                    excluir_venda(int(id_excluir))
                    st.toast(f"Venda #{int(id_excluir)} excluída!", icon="🗑️")
                    st.rerun()


# ── ABA 4: GERENCIAR PRODUTOS ────────────────────────────────────────────────
with aba_gerenciar:
    st.subheader("Cardápio e Custos")
    st.info("Consulte a tabela e atualize os valores quando necessário.")

    produtos = buscar_produtos()
    if produtos:
        kits_tab, avulsas_tab = separar_produtos(produtos)

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
                    value=float(prod["preco_venda"]), format="%.2f",
                )
            with cB:
                novo_custo = st.number_input(
                    "Novo Custo (R$):", min_value=0.0,
                    value=float(prod["custo_estimado"]), format="%.2f",
                )

            if st.form_submit_button("💾 Salvar alterações", use_container_width=True):
                atualizar_produto(prod["id"], novo_preco, novo_custo)
                st.success(f"✅ '{prod['nome']}' atualizado!")
                st.rerun()


# ── ABA 5: CARDÁPIO EM PDF ───────────────────────────────────────────────────
with aba_cardapio:
    st.subheader("Cardápio em PDF")
    st.caption(
        "Gere uma versão em PDF do cardápio completo, pronta para compartilhar "
        "com clientes. Os dados são puxados do banco em tempo real."
    )

    produtos = buscar_produtos()
    if not produtos:
        st.warning("Nenhum produto cadastrado — não há o que gerar.")
    else:
        if st.button("📄 Gerar Cardápio em PDF", use_container_width=True):
            try:
                pdf_bytes = gerar_cardapio_pdf(produtos)
                st.session_state["cardapio_pdf"] = pdf_bytes
                st.success("Cardápio gerado! Clique abaixo para baixar.")
            except ModuleNotFoundError:
                st.error(
                    "Biblioteca `reportlab` não instalada. "
                    "Rode `pip install reportlab` e reinicie o app."
                )
            except Exception as e:
                st.error(f"Falha ao gerar PDF: {e}")

        if "cardapio_pdf" in st.session_state:
            st.download_button(
                label="⬇️ Baixar cardapio.pdf",
                data=st.session_state["cardapio_pdf"],
                file_name="cardapio_seu_paozinho.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
