import streamlit as st
from supabase import create_client, Client
from datetime import datetime, date, timedelta
import pandas as pd

# =============================================================================
# CONFIGURAÇÃO DA PÁGINA
# =============================================================================
st.set_page_config(
    page_title="Seu Pãozinho 🍞",
    page_icon="🍞",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# CSS para melhorar experiência mobile
st.markdown("""
<style>
    /* Aumenta botões para toque no celular */
    .stButton > button {
        height: 3rem;
        font-size: 1rem;
        font-weight: 600;
    }
    /* Métricas com fundo levemente colorido */
    [data-testid="metric-container"] {
        background-color: #f9f9f9;
        border-radius: 12px;
        padding: 12px;
        border: 1px solid #eee;
    }
    /* Esconde menu hamburguer no celular */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# =============================================================================
# CONEXÃO COM SUPABASE
# =============================================================================
@st.cache_resource
def init_supabase() -> Client:
    """Inicializa a conexão com o Supabase usando os segredos do Streamlit."""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# =============================================================================
# FUNÇÕES DE BANCO DE DADOS — PRODUTOS
# =============================================================================
@st.cache_data(ttl=300)  # Cache de 5 minutos para não sobrecarregar o banco
def buscar_produtos():
    """Retorna todos os produtos cadastrados."""
    res = supabase.table("produtos").select("*").order("id").execute()
    return res.data  # Lista de dicionários

def atualizar_produto(id_produto: int, novo_preco: float, novo_custo: float):
    """Atualiza preço e custo de um produto."""
    supabase.table("produtos").update({
        "preco_venda": novo_preco,
        "custo_estimado": novo_custo
    }).eq("id", id_produto).execute()
    st.cache_data.clear()  # Limpa o cache para refletir a mudança

# =============================================================================
# FUNÇÕES DE BANCO DE DADOS — VENDAS
# =============================================================================
def salvar_venda(produto_id: int, quantidade: int, valor_total: float):
    """Registra uma nova venda no banco."""
    supabase.table("vendas").insert({
        "data_venda": datetime.now().isoformat(),
        "produto_id": produto_id,
        "quantidade": quantidade,
        "valor_total": valor_total
    }).execute()

def buscar_metricas(data_inicio: date, data_fim: date) -> tuple:
    """
    Retorna (faturamento, custo, lucro) para o período informado.
    Faz a junção com a tabela de produtos para calcular o CMV real.
    """
    # Converte datas para ISO string com hora (início do dia / fim do dia)
    inicio_str = datetime.combine(data_inicio, datetime.min.time()).isoformat()
    fim_str    = datetime.combine(data_fim,    datetime.max.time()).isoformat()

    res = (
        supabase.table("vendas")
        .select("valor_total, quantidade, produtos(custo_estimado)")
        .gte("data_venda", inicio_str)
        .lte("data_venda", fim_str)
        .execute()
    )

    faturamento = 0.0
    custo       = 0.0

    for venda in res.data:
        faturamento += venda["valor_total"]
        custo_unit   = venda["produtos"]["custo_estimado"] if venda["produtos"] else 0
        custo       += custo_unit * venda["quantidade"]

    lucro = faturamento - custo
    return faturamento, custo, lucro

def buscar_historico(data_inicio: date, data_fim: date) -> pd.DataFrame:
    """Retorna o histórico de vendas do período como DataFrame."""
    inicio_str = datetime.combine(data_inicio, datetime.min.time()).isoformat()
    fim_str    = datetime.combine(data_fim,    datetime.max.time()).isoformat()

    res = (
        supabase.table("vendas")
        .select("id, data_venda, quantidade, valor_total, produtos(nome)")
        .gte("data_venda", inicio_str)
        .lte("data_venda", fim_str)
        .order("id", desc=True)
        .execute()
    )

    # Achata o resultado para um DataFrame legível
    rows = []
    for v in res.data:
        rows.append({
            "ID":          v["id"],
            "Data":        v["data_venda"][:16].replace("T", " "),
            "Produto":     v["produtos"]["nome"] if v["produtos"] else "—",
            "Qtd":         v["quantidade"],
            "Total (R$)":  f"R$ {v['valor_total']:.2f}"
        })

    return pd.DataFrame(rows)

def excluir_venda(id_venda: int):
    """Remove uma venda pelo ID."""
    supabase.table("vendas").delete().eq("id", id_venda).execute()

# =============================================================================
# HELPER: SELETOR DE PERÍODO
# =============================================================================
def seletor_periodo(chave: str) -> tuple[date, date]:
    """
    Renderiza um seletor de período reutilizável.
    Retorna (data_inicio, data_fim).
    """
    hoje = date.today()
    opcoes = {
        "📅 Hoje":        (hoje, hoje),
        "🗓️ Esta semana": (hoje - timedelta(days=hoje.weekday()), hoje),
        "📆 Este mês":    (hoje.replace(day=1), hoje),
        "🗃️ Tudo":        (date(2000, 1, 1), hoje),
        "✏️ Personalizado": None,
    }

    escolha = st.radio(
        "Período:", list(opcoes.keys()),
        horizontal=True, key=f"radio_{chave}"
    )

    if opcoes[escolha] is not None:
        return opcoes[escolha]
    else:
        col1, col2 = st.columns(2)
        with col1:
            inicio = st.date_input("De:", value=hoje.replace(day=1), key=f"di_{chave}")
        with col2:
            fim = st.date_input("Até:", value=hoje, key=f"df_{chave}")
        return inicio, fim

# =============================================================================
# INTERFACE PRINCIPAL
# =============================================================================
st.title("🍞 Seu Pãozinho")

aba_vendas, aba_dashboard, aba_historico, aba_gerenciar = st.tabs([
    "💰 Venda", "📊 Dashboard", "📝 Histórico", "⚙️ Produtos"
])

# ── ABA 1: LANÇAMENTO DE VENDA ───────────────────────────────────────────────
with aba_vendas:
    st.subheader("Registrar Venda")
    produtos = buscar_produtos()

    if not produtos:
        st.warning("Nenhum produto cadastrado. Configure o banco de dados primeiro.")
    else:
        # Monta opções: "Nome - R$ Preço"
        opcoes = {
            f"{p['nome']}  —  R$ {p['preco_venda']:.2f}": p
            for p in produtos
        }

        with st.form("form_venda", clear_on_submit=True):
            produto_sel = st.selectbox("Produto:", list(opcoes.keys()))
            quantidade  = st.number_input("Quantidade:", min_value=1, value=1, step=1)

            produto     = opcoes[produto_sel]
            valor_total = produto["preco_venda"] * quantidade

            st.markdown(f"### 💵 Total: R$ {valor_total:.2f}")
            salvar = st.form_submit_button("✅ Registrar Venda", use_container_width=True)

            if salvar:
                salvar_venda(produto["id"], quantidade, valor_total)
                st.success(f"Venda registrada! **R$ {valor_total:.2f}**")
                st.balloons()

# ── ABA 2: DASHBOARD ─────────────────────────────────────────────────────────
with aba_dashboard:
    st.subheader("Resumo Financeiro")

    data_ini, data_fim = seletor_periodo("dash")

    faturamento, custo, lucro = buscar_metricas(data_ini, data_fim)
    margem = (lucro / faturamento * 100) if faturamento > 0 else 0

    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)

    col1.metric("💰 Faturamento",  f"R$ {faturamento:,.2f}")
    col2.metric("🧾 Custos (CMV)", f"R$ {custo:,.2f}")
    col3.metric("📈 Lucro Bruto",  f"R$ {lucro:,.2f}")
    col4.metric("📊 Margem",       f"{margem:.1f}%")

    if faturamento == 0:
        st.info("Nenhuma venda encontrada para o período selecionado.")

# ── ABA 3: HISTÓRICO ─────────────────────────────────────────────────────────
with aba_historico:
    st.subheader("Histórico de Vendas")

    data_ini, data_fim = seletor_periodo("hist")
    df = buscar_historico(data_ini, data_fim)

    if df.empty:
        st.info("Nenhuma venda no período selecionado.")
    else:
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.caption(f"{len(df)} venda(s) encontrada(s).")

        st.divider()
        with st.form("form_excluir"):
            st.markdown("**Excluir uma venda:**")
            id_excluir = st.number_input("ID da venda:", min_value=1, step=1)
            excluir    = st.form_submit_button("🗑️ Excluir", use_container_width=True)
            if excluir:
                excluir_venda(id_excluir)
                st.success(f"Venda #{id_excluir} excluída. Atualize a página.")

# ── ABA 4: GERENCIAR PRODUTOS ────────────────────────────────────────────────
with aba_gerenciar:
    st.subheader("Cardápio e Custos")
    st.info("Aqui você pode consultar e atualizar os valores de cada produto.")

    produtos = buscar_produtos()
    if produtos:
        df_prod = pd.DataFrame(produtos)[["id", "nome", "tamanho", "preco_venda", "custo_estimado"]]
        df_prod.columns = ["ID", "Produto", "Tamanho", "Preço (R$)", "Custo (R$)"]
        st.dataframe(df_prod, hide_index=True, use_container_width=True)

        st.divider()
        st.markdown("**Editar produto:**")

        opcoes_edit = {f"{p['nome']} ({p['tamanho']})": p for p in produtos}

        with st.form("form_editar"):
            prod_edit   = st.selectbox("Selecione:", list(opcoes_edit.keys()))
            prod        = opcoes_edit[prod_edit]

            colA, colB  = st.columns(2)
            with colA:
                novo_preco = st.number_input(
                    "Novo Preço (R$):", min_value=0.0,
                    value=float(prod["preco_venda"]), format="%.2f"
                )
            with colB:
                novo_custo = st.number_input(
                    "Novo Custo (R$):", min_value=0.0,
                    value=float(prod["custo_estimado"]), format="%.2f"
                )

            salvar_edit = st.form_submit_button("💾 Salvar", use_container_width=True)
            if salvar_edit:
                atualizar_produto(prod["id"], novo_preco, novo_custo)
                st.success("Produto atualizado! Atualize a página para ver.")