from __future__ import annotations
import streamlit as st
from supabase import create_client, Client
from datetime import datetime, date
import pandas as pd


# ── Conexão ──────────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


# ── Produtos ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def buscar_produtos() -> list[dict]:
    return get_supabase().table("produtos").select("*").order("id").execute().data


def atualizar_produto(id_produto: int, novo_preco: float, novo_custo: float) -> None:
    get_supabase().table("produtos").update(
        {"preco_venda": novo_preco, "custo_estimado": novo_custo}
    ).eq("id", id_produto).execute()
    st.cache_data.clear()


# ── Vendas ────────────────────────────────────────────────────────────────────
def salvar_venda(
    produto_id: int,
    quantidade: int,
    valor_total: float,
    tipo: str = "kit",          # "kit" ou "avulsa"
) -> None:
    st.cache_data.clear()
    get_supabase().table("vendas").insert({
        "data_venda":  datetime.now().isoformat(),
        "produto_id":  produto_id,
        "quantidade":  quantidade,
        "valor_total": valor_total,
        "tipo":        tipo,
    }).execute()


def editar_venda(id_venda: int, nova_quantidade: int, novo_total: float) -> None:
    st.cache_data.clear()
    get_supabase().table("vendas").update(
        {"quantidade": nova_quantidade, "valor_total": novo_total}
    ).eq("id", id_venda).execute()


def excluir_venda(id_venda: int) -> None:
    st.cache_data.clear()
    get_supabase().table("vendas").delete().eq("id", id_venda).execute()


def buscar_metricas(data_inicio: date, data_fim: date) -> tuple[float, float, float]:
    inicio_str = datetime.combine(data_inicio, datetime.min.time()).isoformat()
    fim_str    = datetime.combine(data_fim,    datetime.max.time()).isoformat()

    res = (
        get_supabase().table("vendas")
        .select("valor_total, quantidade, produtos(custo_estimado)")
        .gte("data_venda", inicio_str)
        .lte("data_venda", fim_str)
        .execute()
    )

    faturamento = custo = 0.0
    for v in res.data:
        faturamento += v["valor_total"]
        custo_unit   = v["produtos"]["custo_estimado"] if v["produtos"] else 0
        custo       += custo_unit * v["quantidade"]

    return faturamento, custo, faturamento - custo


def buscar_historico(data_inicio: date, data_fim: date) -> pd.DataFrame:
    inicio_str = datetime.combine(data_inicio, datetime.min.time()).isoformat()
    fim_str    = datetime.combine(data_fim,    datetime.max.time()).isoformat()

    res = (
        get_supabase().table("vendas")
        .select("id, data_venda, quantidade, valor_total, tipo, produto_id, produtos(nome, preco_venda)")
        .gte("data_venda", inicio_str)
        .lte("data_venda", fim_str)
        .order("id", desc=True)
        .execute()
    )

    rows = []
    for v in res.data:
        tipo      = v.get("tipo", "kit")
        nome_prod = v["produtos"]["nome"] if v["produtos"] else "—"

        rows.append({
            "ID":          v["id"],
            "Data":        v["data_venda"][:16].replace("T", " "),
            "Tipo":        "🧺 Kit" if tipo == "kit" else "🍞 Avulsa",
            "Produto":     nome_prod,
            "Qtd":         v["quantidade"],
            "Total (R$)":  f"R$ {v['valor_total']:.2f}",
            # Ocultas — usadas no formulário de edição
            "_produto_id": v["produto_id"],
            "_preco_unit": v["produtos"]["preco_venda"] if v["produtos"] else 0,
        })
    return pd.DataFrame(rows)