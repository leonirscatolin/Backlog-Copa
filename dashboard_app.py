import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import base64
from datetime import datetime, timedelta
from github import Github, Auth
from io import StringIO

# --- Configuração da Página ---
st.set_page_config(
    layout="wide", 
    page_title="Backlog Copa Energia + Belago",
    page_icon="copaenergialogo_1691612041.webp"
)

# --- FUNÇÕES ---
@st.cache_resource
def get_github_repo():
    try:
        auth = Auth.Token(st.secrets["GITHUB_TOKEN"])
        g = Github(auth=auth)
        # NOME DE USUÁRIO INSERIDO AQUI
        return g.get_repo("leonirscatolin/dashboard-backlog")
    except Exception as e:
        st.error(f"Erro ao conectar ao repositório do GitHub: {e}")
        return None

@st.cache_data(ttl=600)
def get_history_from_github(_repo):
    try:
        content_file = _repo.get_contents("historico_dados_completos.csv")
        content = content_file.decoded_content.decode("utf-8")
        df = pd.read_csv(StringIO(content))
        if not df.empty:
            df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])
        return df, content_file.sha
    except Exception:
        return pd.DataFrame(columns=["snapshot_date", "ID do ticket", "Atribuir a um grupo", "Data de criação"]), None

def update_history_on_github(_repo, df_novo_snapshot, sha):
    hoje_date = datetime.now().date()
    df_historico, _ = get_history_from_github(_repo)

    if not df_historico.empty:
        df_historico = df_historico[df_historico['snapshot_date'].dt.date != hoje_date]

    df_novo_snapshot['snapshot_date'] = hoje_date
    df_atualizado = pd.concat([df_historico, df_novo_snapshot], ignore_index=True)
    csv_string = df_atualizado.to_csv(index=False)
    
    commit_message = f"Atualizando histórico {hoje_date.strftime('%Y-%m-%d')}"
    if sha:
        _repo.update_file("historico_dados_completos.csv", commit_message, csv_string, sha)
    else:
        _repo.create_file("historico_dados_completos.csv", commit_message, csv_string)
    
    st.sidebar.success("Snapshot de hoje salvo!")
    st.cache_data.clear()

def get_base_64_of_bin_file(bin_file):
    try:
        with open(bin_file, 'rb') as f: data = f.read()
        return base64.b64encode(data).decode()
    except FileNotFoundError: return None

def categorizar_idade_vetorizado(dias_series):
    condicoes = [
        dias_series >= 30, (dias_series >= 21) & (dias_series <= 29),
        (dias_series >= 11) & (dias_series <= 20), (dias_series >= 6) & (dias_series <= 10),
        (dias_series >= 3) & (dias_series <= 5), (dias_series >= 1) & (dias_series <= 2)
    ]
    opcoes = ["30+ dias", "21-29 dias", "11-20 dias", "6-10 dias", "3-5 dias", "1-2 dias"]
    return np.select(condicoes, opcoes, default="Erro de Categoria")

def analisar_aging(df_para_analise):
    df = df_para_analise.copy()
    df['Data de criação'] = pd.to_datetime(df['Data de criação'], errors='coerce', dayfirst=True)
    df.dropna(subset=['Data de criação'], inplace=True)
    hoje = pd.to_datetime('today').normalize()
    data_criacao_normalizada = df['Data de criação'].dt.normalize()
    df['Dias em Aberto'] = (hoje - data_criacao_normalizada).dt.days + 1
    df['Faixa de Antiguidade'] = categorizar_idade_vetorizado(df['Dias em Aberto'])
    return df

def get_status(row):
    diferenca = row['Diferença']
    if diferenca > 0:
        return "Alta Demanda"
    elif diferenca == 0:
        return "Estável / Atenção"
    else:
        return "Redução de Backlog"

# --- INTERFACE DO APLICATIVO ---
st.title("Backlog Copa Energia + Belago")
# (Resto da interface omitida)
