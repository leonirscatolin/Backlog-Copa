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
        return g.get_repo("leonirscatolin/dashboard-backlog")
    except Exception as e:
        st.error(f"Erro ao conectar ao repositório do GitHub: {e}")
        st.stop()

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
        return pd.DataFrame(), None

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
    
    st.sidebar.success("Snapshot de hoje salvo no GitHub!")
    st.cache_data.clear()
    
def get_base_64_of_bin_file(bin_file):
    try:
        with open(bin_file, 'rb') as f: data = f.read()
        return base64.b64encode(data).decode()
    except FileNotFoundError: return None

def categorizar_idade_vetorizado(dias_series):
    #...
    pass
def analisar_aging(df_para_analise):
    #...
    pass
def get_status(row):
    #...
    pass

# --- INTERFACE DO APLICATIVO ---
st.title("Backlog Copa Energia + Belago")

gif_path = "237f1d13493514962376f142bb68_1691760314.gif"
belago_logo_path = "logo_belago.png"
gif_base64 = get_base_64_of_bin_file(gif_path)
belago_logo_base64 = get_base_64_of_bin_file(belago_logo_path)
if gif_base64 and belago_logo_base64:
    st.sidebar.markdown(f"""...""", unsafe_allow_html=True)

# --- LÓGICA DE LOGIN E UPLOAD ---
st.sidebar.header("Área do Administrador")
password = st.sidebar.text_input("Digite a senha para atualizar os dados:", type="password")
is_admin = password == st.secrets.get("ADMIN_PASSWORD", "")

if is_admin:
    st.sidebar.success("Acesso de administrador liberado!")
    st.sidebar.header("Carregar e Salvar Backlog do Dia")
    uploaded_file_atual = st.sidebar.file_uploader("Carregue o arquivo de backlog ATUAL (.csv)", type="csv")
    
    repo = get_github_repo()

    if uploaded_file_atual:
        try:
            df_atual_upload = pd.read_csv(uploaded_file_atual, delimiter=';', encoding='latin1')
            df_atual_filtrado_upload = df_atual_upload[~df_atual_upload['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
            colunas_necessarias = ['ID do ticket', 'Atribuir a um grupo', 'Data de criação']
            df_para_salvar = df_atual_filtrado_upload[colunas_necessarias].copy()
            _, sha = get_history_from_github(repo)
            update_history_on_github(repo, df_para_salvar, sha)
        except Exception as e:
            st.sidebar.error(f"Erro ao salvar: {e}")
            st.stop()
elif password:
    st.sidebar.error("Senha incorreta.")

st.markdown("---")
st.header("Análises do Backlog")

# --- LÓGICA DE EXIBIÇÃO ---
repo_display = get_github_repo()
df_historico_completo, _ = get_history_from_github(repo_display)

if df_historico_completo.empty:
    st.warning("Nenhum histórico encontrado. O administrador precisa carregar o arquivo do dia.")
else:
    # (Resto do código para exibir as abas e os dashboards)
    pass
