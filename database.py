from __future__ import annotations
import re
import streamlit as st
from supabase import create_client, Client
from datetime import datetime, date, time, timezone, timedelta
import pandas as pd

TZ_BR = timezone(timedelta(hours=-3))


# ── Conexão ──────────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


# ── Produtos ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def buscar_produtos() -> list[dict]:
    return get_supabase().table("produtos").select("*").order("id").execute().data


def _limpar_cache_vendas() -> None:
    """Invalida caches que dependem de dados de vendas."""
    buscar_historico.clear()
    buscar_metricas.clear()


def _limpar_cache_produtos() -> None:
    """Invalida caches que dependem de dados de produtos."""
    buscar_produtos.clear()


def atualizar_produto(id_produto: int, novo_preco: float, novo_custo: float) -> None:
    get_supabase().table("produtos").update(
        {"preco_venda": novo_preco, "custo_estimado": novo_custo}
    ).eq("id", id_produto).execute()
    _limpar_cache_produtos()


# ── Vendas ────────────────────────────────────────────────────────────────────
def salvar_venda(
    produto_id: int | None,
    quantidade: int,
    valor_total: float,
    tipo: str = "kit",
    frete_cobrado: float = 0.0,
    frete_real: float = 0.0,
) -> int:
    """Salva venda e retorna o ID do registro criado."""
    if tipo not in ("kit", "avulsa", "frete"):
        raise ValueError(f"Tipo de venda inválido: {tipo}")
    if quantidade < 0:
        raise ValueError("Quantidade não pode ser negativa.")
    if valor_total < 0:
        raise ValueError("Valor total não pode ser negativo.")
    if frete_cobrado < 0 or frete_real < 0:
        raise ValueError("Valores de frete não podem ser negativos.")
    row = {
        "data_venda":    datetime.now(TZ_BR).isoformat(),
        "quantidade":    quantidade,
        "valor_total":   valor_total,
        "tipo":          tipo,
        "frete_cobrado": frete_cobrado,
        "frete_real":    frete_real,
    }
    if produto_id is not None:
        row["produto_id"] = produto_id
    res = get_supabase().table("vendas").insert(row).execute()
    _limpar_cache_vendas()
    return res.data[0]["id"]


def editar_venda(
    id_venda: int,
    nova_quantidade: int,
    novo_total: float,
    novo_frete_cobrado: float | None = None,
    novo_frete_real: float | None = None,
) -> None:
    campos: dict = {"quantidade": nova_quantidade, "valor_total": novo_total}
    if novo_frete_cobrado is not None:
        campos["frete_cobrado"] = novo_frete_cobrado
    if novo_frete_real is not None:
        campos["frete_real"] = novo_frete_real
    get_supabase().table("vendas").update(campos).eq("id", id_venda).execute()
    _limpar_cache_vendas()


def excluir_venda(id_venda: int) -> None:
    get_supabase().table("vendas").delete().eq("id", id_venda).execute()
    _limpar_cache_vendas()


@st.cache_data(ttl=120)
def buscar_metricas(data_inicio: date, data_fim: date) -> dict:
    """
    Retorna dicionário com:
      faturamento  — soma dos valor_total + frete_cobrado
      custo        — CMV dos produtos + frete_real pago
      lucro        — faturamento - custo
      lucro_frete  — frete_cobrado - frete_real (lucro só do frete)
    """
    inicio_str = datetime.combine(data_inicio, time.min, tzinfo=TZ_BR).isoformat()
    fim_str    = datetime.combine(data_fim,    time.max, tzinfo=TZ_BR).isoformat()

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

        if not v.get("produtos"):
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


@st.cache_data(ttl=120)
def buscar_historico(data_inicio: date, data_fim: date) -> pd.DataFrame:
    inicio_str = datetime.combine(data_inicio, time.min, tzinfo=TZ_BR).isoformat()
    fim_str    = datetime.combine(data_fim,    time.max, tzinfo=TZ_BR).isoformat()

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
        nome  = v["produtos"]["nome"] if v.get("produtos") else "—"
        qtd   = v["quantidade"] if v["quantidade"] else 0
        fc    = v.get("frete_cobrado") or 0
        fr    = v.get("frete_real")    or 0

        # Converte UTC → UTC-3 para exibição correta
        dt_raw = datetime.fromisoformat(v["data_venda"])
        dt_br  = dt_raw.astimezone(TZ_BR)
        data_formatada = dt_br.strftime("%Y-%m-%d %H:%M")

        frete_label = f"R$ {fc:.2f} (pago R$ {fr:.2f})" if fc > 0 else "—"

        rows.append({
            "ID":           v["id"],
            "Data":         data_formatada,
            "Tipo":         "🧺 Kit" if tipo == "kit" else ("🍞 Avulsa" if tipo == "avulsa" else "🚗 Frete"),
            "Produto":      nome,
            "Qtd":          qtd,
            "Produtos (R$)":f"R$ {v['valor_total']:.2f}",
            "Frete":        frete_label,
            "_preco_unit":    round(v["valor_total"] / qtd, 4) if qtd > 0 else 0,
            "_produto_id":   v["produto_id"],
            "_frete_cobrado": fc,
            "_frete_real":    fr,
        })
    return pd.DataFrame(rows)