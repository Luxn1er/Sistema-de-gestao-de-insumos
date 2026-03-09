


import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
from io import BytesIO
import shutil

# =========================
# CONFIG (AJUSTE AQUI)
# =========================
ABA_ESTOQUE = "Estoque"
ABA_HIST = "Historico"


# 1) Planilha PRINCIPAL (fora do Dropbox) - o app lê e salva AQUI
ARQUIVO_LOCAL = Path(r"data/estoque_base.xlsx")  

# 2) Planilha ESPELHO (dentro do Dropbox do servidor) - o app copia pra cá
ARQUIVO_DROPBOX = Path(r"backup/estoque_mirror.xlsx") 

# Quantidade de registros recentes para mostrar
RECENTES_QTD = 15

st.set_page_config(page_title="Controle de Estoque (Local)", layout="wide")


# =========================
# EXCEL I/O
# =========================
def garantir_arquivo_existe():
    """
    Se a planilha local principal não existir, cria com as abas e colunas corretas.
    """
    if ARQUIVO_LOCAL.exists():
        return

    ARQUIVO_LOCAL.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(columns=["Item", "Quantidade"])
    hist = pd.DataFrame(columns=["Data", "Usuario", "Item", "Movimento", "Quantidade", "Estoque_Atual"])
    salvar_dados(df, hist)  #cópia dropbox


def carregar_dados() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Lê Estoque e Histórico do arquivo local principal.
    """
    garantir_arquivo_existe()

    xls = pd.ExcelFile(ARQUIVO_LOCAL, engine="openpyxl")

    if ABA_ESTOQUE not in xls.sheet_names:
        raise ValueError(f"Não encontrei a aba '{ABA_ESTOQUE}' no Excel: {ARQUIVO_LOCAL}")

    df = pd.read_excel(xls, sheet_name=ABA_ESTOQUE)
    if "Item" not in df.columns or "Quantidade" not in df.columns:
        raise ValueError("A aba 'Estoque' precisa ter colunas: Item e Quantidade.")

    df["Item"] = df["Item"].astype(str).str.strip()
    df["Quantidade"] = pd.to_numeric(df["Quantidade"], errors="coerce").fillna(0).astype(int)

    if ABA_HIST in xls.sheet_names:
        hist = pd.read_excel(xls, sheet_name=ABA_HIST)

        for c in ["Data", "Usuario", "Item", "Movimento", "Quantidade", "Estoque_Atual"]:
            if c not in hist.columns:
                hist[c] = None

        hist = hist[["Data", "Usuario", "Item", "Movimento", "Quantidade", "Estoque_Atual"]].copy()
    else:
        hist = pd.DataFrame(columns=["Data", "Usuario", "Item", "Movimento", "Quantidade", "Estoque_Atual"])

    # normaliza histórico
    if not hist.empty:
        hist["Data"] = hist["Data"].fillna("").astype(str)
        hist["Usuario"] = hist["Usuario"].fillna("").astype(str).str.strip()
        hist["Item"] = hist["Item"].fillna("").astype(str).str.strip()
        hist["Movimento"] = hist["Movimento"].fillna("").astype(str).str.strip().str.upper()
        hist["Quantidade"] = pd.to_numeric(hist["Quantidade"], errors="coerce").fillna(0).astype(int)
        hist["Estoque_Atual"] = pd.to_numeric(hist["Estoque_Atual"], errors="coerce").fillna(0).astype(int)

    return df, hist


def salvar_dados(df: pd.DataFrame, hist: pd.DataFrame) -> None:
    """
    espelha o arquivo.
    """
    ARQUIVO_LOCAL.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(ARQUIVO_LOCAL, engine="openpyxl") as writer:
        df.sort_values("Item").to_excel(writer, sheet_name=ABA_ESTOQUE, index=False)
        hist.to_excel(writer, sheet_name=ABA_HIST, index=False)

    # Copia para o Dropbox (espelho)
    try:
        ARQUIVO_DROPBOX.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ARQUIVO_LOCAL, ARQUIVO_DROPBOX)
    except Exception as e:
        # Não para o sistema por causa do Dropbox; só avisa.
        st.warning(f" Salvei na planilha local, mas não consegui copiar para o Dropbox: {e}")


def gerar_excel_download(df: pd.DataFrame, hist: pd.DataFrame) -> bytes:
    """
    Gera Excel em memória para download (não mexe no arquivo principal).
    """
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.sort_values("Item").to_excel(writer, sheet_name=ABA_ESTOQUE, index=False)
        hist.to_excel(writer, sheet_name=ABA_HIST, index=False)
    buffer.seek(0)
    return buffer.getvalue()


# =========================
# REGRAS
# =========================
def registrar_movimento(hist: pd.DataFrame, usuario: str, item: str, movimento: str, qtd: int, estoque_atual: int) -> pd.DataFrame:
    linha = {
        "Data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "Usuario": usuario,
        "Item": item,
        "Movimento": movimento,
        "Quantidade": int(qtd),
        "Estoque_Atual": int(estoque_atual),
    }
    return pd.concat([hist, pd.DataFrame([linha])], ignore_index=True)


def obter_ultimo_movimento(hist: pd.DataFrame) -> dict | None:
    """
    Retorna a última movimentação (por Data), ou None.
    """
    if hist.empty:
        return None

    temp = hist.copy()
    # tenta ordenar por datetime; se falhar, usa a ordem original
    temp["_dt"] = pd.to_datetime(temp["Data"], errors="coerce", dayfirst=True)
    temp = temp.sort_values("_dt", ascending=False)
    row = temp.iloc[0].drop(labels=["_dt"]).to_dict()
    return row


def movimentos_recentes(hist: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    if hist.empty:
        return hist
    temp = hist.copy()
    temp["_dt"] = pd.to_datetime(temp["Data"], errors="coerce", dayfirst=True)
    temp = temp.sort_values("_dt", ascending=False).drop(columns=["_dt"])
    return temp.head(n)


# =========================
# APP
# =========================
st.title("Controle de Insumos ")

# Sessão: nome do usuário
if "usuario" not in st.session_state:
    st.session_state["usuario"] = ""

# Sempre carrega dados
try:
    df, hist = carregar_dados()
except Exception as e:
    st.error("Erro ao abrir a planilha local.")
    st.write(f"Arquivo local: `{ARQUIVO_LOCAL}`")
    st.exception(e)
    st.stop()

# Cabeçalho de status de arquivos
with st.expander(" Caminhos usados pelo sistema", expanded=False):
    st.write("**Planilha local (principal):**", str(ARQUIVO_LOCAL))
    st.write("**Planilha no Dropbox (espelho):**", str(ARQUIVO_DROPBOX))

# =========================
# BLOQUEIO: só libera se tiver nome
# =========================
st.subheader(" Identificação")
st.session_state["usuario"] = st.text_input(
    "Digite seu nome para liberar o uso do sistema",
    value=st.session_state["usuario"],
    placeholder="Ex: Pedro / João / Wylliam"
)

usuario = (st.session_state["usuario"] or "").strip()

if not usuario:
    st.info("🔒 Digite seu nome acima para liberar o sistema.")
    st.stop()

st.success(f"✅ Acesso liberado para: **{usuario}**")

st.divider()

# =========================
# RESUMO: último movimento + recentes
# =========================
st.subheader("🕒 Movimentação recente")

ultimo = obter_ultimo_movimento(hist)
if ultimo:
    st.markdown(
        f"**Última movimentação:** {ultimo.get('Data','')} — **{ultimo.get('Usuario','')}** "
        f"fez **{ultimo.get('Movimento','')}** de **{ultimo.get('Quantidade','')}** em **{ultimo.get('Item','')}** "
        f"(Estoque Atual: **{ultimo.get('Estoque_Atual','')}**)."
    )
else:
    st.info("Ainda não há movimentações registradas.")

st.dataframe(movimentos_recentes(hist, RECENTES_QTD), use_container_width=True, hide_index=True)

st.divider()

# =========================
# EXPORTAR
# =========================
st.subheader("⬇️ Exportar")
st.download_button(
    "Baixar Excel atualizado",
    data=gerar_excel_download(df, hist),
    file_name="estoque_atual.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)

st.divider()

# =========================
# AÇÕES (Entrada/Saída)
# =========================
colL, colR = st.columns([0.9, 1.1], gap="large")

with colL:
    st.subheader("⚙️ Entrada / Saída")

    if df.empty:
        st.warning("A aba Estoque está vazia. Adicione itens no Excel (Item/Quantidade) e recarregue.")
        st.stop()

    item_sel = st.selectbox("Item", df["Item"].tolist())
    movimento = st.radio("Movimento", ["ENTRADA", "SAIDA"], horizontal=True)
    qtd = st.number_input("Quantidade", min_value=1, step=1, value=1)

    if st.button("Aplicar movimento", use_container_width=True):
        atual = int(df.loc[df["Item"] == item_sel, "Quantidade"].iloc[0])

        if movimento == "SAIDA" and qtd > atual:
            st.error(f"Estoque insuficiente. Atual: {atual}")
        else:
            novo = atual + int(qtd) if movimento == "ENTRADA" else atual - int(qtd)
            df.loc[df["Item"] == item_sel, "Quantidade"] = novo
            hist = registrar_movimento(hist, usuario, item_sel, movimento, int(qtd), novo)

            salvar_dados(df, hist)
            st.success("✅ Salvo na planilha local e espelhado no Dropbox.")
            st.rerun()

with colR:
    st.subheader("📊 Movimentação do item")

    qtd_atual = int(df.loc[df["Item"] == item_sel, "Quantidade"].iloc[0])

    entradas = hist[(hist["Item"] == item_sel) & (hist["Movimento"] == "ENTRADA")]["Quantidade"].sum()
    saidas = hist[(hist["Item"] == item_sel) & (hist["Movimento"] == "SAIDA")]["Quantidade"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Quantidade atual", qtd_atual)
    c2.metric("Total entradas", int(entradas))
    c3.metric("Total saídas", int(saidas))

    st.caption("Histórico do item (com usuário)")
    st.dataframe(
        movimentos_recentes(hist[hist["Item"] == item_sel], RECENTES_QTD),
        use_container_width=True,
        hide_index=True
    )

st.subheader("📋 Estoque completo")
st.dataframe(df.sort_values("Item"), use_container_width=True, hide_index=True)
