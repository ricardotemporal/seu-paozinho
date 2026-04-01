from __future__ import annotations
import re
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
    tipo: str = "kit",
    frete_cobrado: float = 0.0,
    frete_real: float = 0.0,
) -> None:
    get_supabase().table("vendas").insert({
        "data_venda":    datetime.now().isoformat(),
        "produto_id":    produto_id,
        "quantidade":    quantidade,
        "valor_total":   valor_total,
        "tipo":          tipo,
        "frete_cobrado": frete_cobrado,
        "frete_real":    frete_real,
    }).execute()
    st.cache_data.clear()


def editar_venda(id_venda: int, nova_quantidade: int, novo_total: float) -> None:
    get_supabase().table("vendas").update(
        {"quantidade": nova_quantidade, "valor_total": novo_total}
    ).eq("id", id_venda).execute()
    st.cache_data.clear()


def excluir_venda(id_venda: int) -> None:
    get_supabase().table("vendas").delete().eq("id", id_venda).execute()
    st.cache_data.clear()


def buscar_metricas(data_inicio: date, data_fim: date) -> dict:
    """
    Retorna dicionário com:
      faturamento  — soma dos valor_total + frete_cobrado
      custo        — CMV dos produtos + frete_real pago
      lucro        — faturamento - custo
      lucro_frete  — frete_cobrado - frete_real (lucro só do frete)
    """
    inicio_str = datetime.combine(data_inicio, datetime.min.time()).isoformat()
    fim_str    = datetime.combine(data_fim,    datetime.max.time()).isoformat()

    res = (
        get_supabase().table("vendas")
        .select("valor_total, quantidade, tipo, frete_cobrado, frete_real, produtos(custo_estimado, tamanho)")
        .gte("data_venda", inicio_str)
        .lte("data_venda", fim_str)
        .execute()
    )

    faturamento = custo = lucro_frete = 0.0

    for v in res.data:
        fc = v.get("frete_cobrado") or 0
        fr = v.get("frete_real")    or 0
        faturamento  += v["valor_total"] + fc
        lucro_frete  += fc - fr

        if not v["produtos"]:
            continue

        custo_prod = v["produtos"]["custo_estimado"]
        tamanho    = v["produtos"].get("tamanho", "")
        tipo       = v.get("tipo", "kit")

        # Avulsas antigas referenciavam o kit — divide pelo tamanho
        if tipo == "avulsa" and tamanho != "1 unidade":
            m = re.search(r"(\d+)", tamanho)
            kit_size  = int(m.group(1)) if m else 1
            custo_uni = custo_prod / kit_size
        else:
            custo_uni = custo_prod

        custo += custo_uni * v["quantidade"] + fr

    return {
        "faturamento": faturamento,
        "custo":       custo,
        "lucro":       faturamento - custo,
        "lucro_frete": lucro_frete,
    }


def buscar_historico(data_inicio: date, data_fim: date) -> pd.DataFrame:
    inicio_str = datetime.combine(data_inicio, datetime.min.time()).isoformat()
    fim_str    = datetime.combine(data_fim,    datetime.max.time()).isoformat()

    res = (
        get_supabase().table("vendas")
        .select("id, data_venda, quantidade, valor_total, tipo, frete_cobrado, frete_real, produto_id, produtos(nome, preco_venda)")
        .gte("data_venda", inicio_str)
        .lte("data_venda", fim_str)
        .order("id", desc=True)
        .execute()
    )

    rows = []
    for v in res.data:
        tipo  = v.get("tipo", "kit")
        nome  = v["produtos"]["nome"] if v["produtos"] else "—"
        qtd   = v["quantidade"] or 1
        fc    = v.get("frete_cobrado") or 0
        fr    = v.get("frete_real")    or 0

        frete_label = f"R$ {fc:.2f} (pago R$ {fr:.2f})" if fc > 0 else "—"

        rows.append({
            "ID":           v["id"],
            "Data":         v["data_venda"][:16].replace("T", " "),
            "Tipo":         "🧺 Kit" if tipo == "kit" else "🍞 Avulsa",
            "Produto":      nome,
            "Qtd":          qtd,
            "Produtos (R$)":f"R$ {v['valor_total']:.2f}",
            "Frete":        frete_label,
            "_preco_unit":  round(v["valor_total"] / qtd, 4),
            "_produto_id":  v["produto_id"],
        })
    return pd.DataFrame(rows)