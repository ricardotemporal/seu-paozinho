import re
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
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# =============================================================================
# CONEXÃO COM SUPABASE
# =============================================================================
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# =============================================================================
# FUNÇÕES DE BANCO DE DADOS — PRODUTOS
# =============================================================================
@st.cache_data(ttl=300)
def buscar_produtos():
    res = supabase.table("produtos").select("*").order("id").execute()
    return res.data

def atualizar_produto(id_produto: int, novo_preco: float, novo_custo: float):
    supabase.table("produtos").update({
        "preco_venda": novo_preco,
        "custo_estimado": novo_custo
    }).eq("id", id_produto).execute()
    st.cache_data.clear()

# =============================================================================
# FUNÇÕES DE BANCO DE DADOS — VENDAS
# =============================================================================
def salvar_venda(produto_id: int, quantidade: int, valor_total: float):
    supabase.table("vendas").insert({
        "data_venda": datetime.now().isoformat(),
        "produto_id": produto_id,
        "quantidade": quantidade,
        "valor_total": valor_total
    }).execute()

def buscar_metricas(data_inicio: date, data_fim: date) -> tuple:
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

    return faturamento, custo, faturamento - custo

def buscar_historico(data_inicio: date, data_fim: date) -> pd.DataFrame:
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

    rows = []
    for v in res.data:
        rows.append({
            "ID":         v["id"],
            "Data":       v["data_venda"][:16].replace("T", " "),
            "Produto":    v["produtos"]["nome"] if v["produtos"] else "—",
            "Qtd":        v["quantidade"],
            "Total (R$)": f"R$ {v['valor_total']:.2f}"
        })
    return pd.DataFrame(rows)

def excluir_venda(id_venda: int):
    supabase.table("vendas").delete().eq("id", id_venda).execute()

# =============================================================================
# HELPER: SELETOR DE PERÍODO
# =============================================================================
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
    col1, col2 = st.columns(2)
    with col1:
        inicio = st.date_input("De:", value=hoje.replace(day=1), key=f"di_{chave}")
    with col2:
        fim = st.date_input("Até:", value=hoje, key=f"df_{chave}")
    return inicio, fim

# =============================================================================
# HELPER: EXTRAI NÚMERO DE UNIDADES DO CAMPO "tamanho"
# =============================================================================
def unidades_do_kit(tamanho: str) -> str:
    m = re.search(r"(\d+)\s*un", tamanho or "", re.IGNORECASE)
    return f"{m.group(1)} pães" if m else tamanho

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
        # Separa avulsa dos kits
        avulsa = next((p for p in produtos if "Avulsa" in p["nome"]), None)
        kits   = [p for p in produtos if "Avulsa" not in p["nome"]]

        # Label: "Nome (10 pães) — R$ 32,00"
        opcoes = {
            f"{p['nome']}  ({unidades_do_kit(p['tamanho'])})  —  R$ {p['preco_venda']:.2f}": p
            for p in kits
        }

        # Sem st.form → total atualiza em tempo real a cada interação
        produto_sel = st.selectbox("Produto (kit):", list(opcoes.keys()))
        produto     = opcoes[produto_sel]
        qtd_kits    = st.number_input("Quantidade de kits:", min_value=1, value=1, step=1)

        st.markdown("**Unidades avulsas extras** *(para completar pedidos quebrados)*")
        label_avulsa = (
            f"Unidades avulsas — R$ {avulsa['preco_venda']:.2f} cada:"
            if avulsa else "Unidades avulsas:"
        )
        qtd_avulsa = st.number_input(label_avulsa, min_value=0, value=0, step=1)

        # Cálculo em tempo real
        valor_kits   = produto["preco_venda"] * qtd_kits
        valor_avulsa = (avulsa["preco_venda"] * qtd_avulsa) if (avulsa and qtd_avulsa > 0) else 0
        valor_total  = valor_kits + valor_avulsa

        st.markdown(f"### 💵 Total: R$ {valor_total:.2f}")
        if qtd_avulsa > 0 and avulsa:
            st.caption(
                f"Kits: R$ {valor_kits:.2f}  +  "
                f"{qtd_avulsa} avulsa(s): R$ {valor_avulsa:.2f}"
            )

        if st.button("✅ Registrar Venda", use_container_width=True):
            salvar_venda(produto["id"], qtd_kits, valor_kits)
            if qtd_avulsa > 0 and avulsa:
                salvar_venda(avulsa["id"], qtd_avulsa, valor_avulsa)
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
    st.info("Consulte a tabela e use o formulário para atualizar os valores.")

    produtos = buscar_produtos()
    if produtos:
        df_prod = pd.DataFrame(produtos)[["id", "nome", "tamanho", "preco_venda", "custo_estimado"]]
        df_prod.columns = ["ID", "Produto", "Tamanho", "Preço (R$)", "Custo (R$)"]
        st.dataframe(df_prod, hide_index=True, use_container_width=True)

        st.divider()
        st.markdown("**Editar produto:**")
        opcoes_edit = {f"{p['nome']} ({p['tamanho']})": p for p in produtos}

        with st.form("form_editar"):
            prod_edit  = st.selectbox("Selecione:", list(opcoes_edit.keys()))
            prod       = opcoes_edit[prod_edit]
            colA, colB = st.columns(2)
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