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
    auth = Auth.Token(st.secrets["GITHUB_TOKEN"])
    # !!! IMPORTANTE: Substitua "SEU-USUARIO-GITHUB" pelo seu nome de usuário no GitHub !!!
    return g.get_repo("SEU-USUARIO-GITHUB/dashboard-backlog")

@st.cache_data(ttl=600)
def get_history_from_github(_repo):
    try:
        content_file = _repo.get_contents("historico_backlog.csv")
        content = content_file.decoded_content.decode("utf-8")
        df = pd.read_csv(StringIO(content))
        if not df.empty:
            df['Data'] = pd.to_datetime(df['Data'], dayfirst=True)
        return df, content_file.sha
    except Exception:
        return pd.DataFrame(columns=["Data", "Grupo", "Quantidade"]), None

def update_history_on_github(_repo, df_atual_para_salvar, sha):
    hoje_str = datetime.now().strftime("%d/%m/%Y")
    df_historico, _ = get_history_from_github(_repo)

    if not df_historico.empty and hoje_str in df_historico['Data'].dt.strftime('%d/%m/%Y').values:
        df_historico = df_historico[df_historico['Data'].dt.strftime('%d/%m/%Y') != hoje_str]
    
    contagem_hoje = df_atual_para_salvar.groupby('Atribuir a um grupo').size().reset_index(name='Quantidade')
    contagem_hoje.columns = ['Grupo', 'Quantidade']
    contagem_hoje['Data'] = hoje_str

    df_atualizado = pd.concat([df_historico, contagem_hoje], ignore_index=True)
    csv_string = df_atualizado.to_csv(index=False)

    if sha:
        _repo.update_file("historico_backlog.csv", f"Atualizando histórico {hoje_str}", csv_string, sha)
    else:
        _repo.create_file("historico_backlog.csv", f"Criando histórico {hoje_str}", csv_string)
    
    st.sidebar.success("Histórico salvo com sucesso!")
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
    # Renomeia colunas do histórico para as que as funções esperam
    df_renomeado = df.rename(columns={'ID do ticket': 'ID do ticket', 'Grupo': 'Atribuir a um grupo', 'Data': 'Data de criação'})
    
    df_renomeado['Data de criação'] = pd.to_datetime(df_renomeado['Data de criação'], errors='coerce', dayfirst=True)
    df_renomeado.dropna(subset=['Data de criação'], inplace=True)
    hoje = pd.to_datetime('today').normalize()
    data_criacao_normalizada = df_renomeado['Data de criação'].dt.normalize()
    df_renomeado['Dias em Aberto'] = (hoje - data_criacao_normalizada).dt.days + 1
    df_renomeado['Faixa de Antiguidade'] = categorizar_idade_vetorizado(df_renomeado['Dias em Aberto'])
    return df_renomeado

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
# (Resto da interface omitida por brevidade)
