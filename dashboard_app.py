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
    """Conecta ao repositório do GitHub usando o token."""
    auth = Auth.Token(st.secrets["GITHUB_TOKEN"])
    g = Github(auth=auth)
    # !!! IMPORTANTE: Substitua "SEU-USUARIO-GITHUB" pelo seu nome de usuário no GitHub !!!
    return g.get_repo("leonirscatolin/dashboard-backlog")

@st.cache_data(ttl=600) # Cache de 10 minutos para não ler o arquivo a cada recarregamento
def get_history_from_github(_repo):
    """Lê o arquivo de histórico do GitHub."""
    try:
        content_file = _repo.get_contents("historico_backlog.csv")
        content = content_file.decoded_content.decode("utf-8")
        df = pd.read_csv(StringIO(content))
        df['Data'] = pd.to_datetime(df['Data'], dayfirst=True)
        return df, content_file.sha
    except Exception:
        # Se o arquivo não existir ou estiver vazio, retorna um dataframe vazio e sha nulo
        return pd.DataFrame(columns=["Data", "Grupo", "Quantidade"]), None

def update_history_on_github(_repo, df_aging_today, sha):
    """Atualiza o arquivo de histórico no GitHub."""
    hoje_str = datetime.now().strftime("%d/%m/%Y")
    df_historico, _ = get_history_from_github(_repo) # Pega a versão mais recente

    # Se a data de hoje já existe, remove para substituir pelos dados novos
    if not df_historico.empty and hoje_str in df_historico['Data'].dt.strftime('%d/%m/%Y').values:
        df_historico = df_historico[df_historico['Data'].dt.strftime('%d/%m/%Y') != hoje_str]

    contagem_hoje = df_aging_today['Atribuir a um grupo'].value_counts().reset_index()
    contagem_hoje.columns = ['Grupo', 'Quantidade']
    contagem_hoje['Data'] = hoje_str

    df_atualizado = pd.concat([df_historico, contagem_hoje], ignore_index=True)
    csv_string = df_atualizado.to_csv(index=False)

    if sha:
        _repo.update_file("historico_backlog.csv", f"Atualizando histórico {hoje_str}", csv_string, sha)
    else:
        _repo.create_file("historico_backlog.csv", f"Criando histórico {hoje_str}", csv_string)
    
    st.sidebar.success("Histórico salvo no GitHub!")
    st.cache_data.clear() # Limpa o cache para a próxima leitura pegar os dados atualizados

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

def analisar_aging(df_atual):
    df = df_atual.copy()
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

gif_path = "237f1d13493514962376f142bb68_1691760314.gif"
belago_logo_path = "logo_belago.png"
gif_base64 = get_base_64_of_bin_file(gif_path)
belago_logo_base64 = get_base_64_of_bin_file(belago_logo_path)
if gif_base64 and belago_logo_base64:
    st.sidebar.markdown(f"""...""", unsafe_allow_html=True) # Omitido

st.sidebar.header("Carregar Backlog do Dia")
uploaded_file_atual = st.sidebar.file_uploader("Carregue o arquivo de backlog ATUAL (.csv)", type="csv")

repo = get_github_repo()

if uploaded_file_atual:
    try:
        df_atual = pd.read_csv(uploaded_file_atual, delimiter=';', encoding='latin1')
        df_atual_filtrado = df_atual[~df_atual['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
        df_aging = analisar_aging(df_atual_filtrado)
        
        _, sha = get_history_from_github(repo)
        update_history_on_github(repo, df_aging, sha)
    except Exception as e:
        st.error(f"Ocorreu um erro ao carregar e salvar o arquivo: {e}")

st.markdown("---")
st.header("Análises do Backlog")

df_historico, _ = get_history_from_github(repo)

if df_historico.empty:
    st.warning("Nenhum histórico encontrado. Carregue o arquivo de hoje para iniciar.")
else:
    hoje_data = df_historico['Data'].max()
    data_15_dias = hoje_data - timedelta(days=15)
    
    df_hoje_hist = df_historico[df_historico['Data'] == hoje_data]
    df_15_dias_hist = df_historico[df_historico['Data'] == data_15_dias]
    
    df_aging_hoje = analisar_aging(df_hoje_hist.rename(columns={'Grupo': 'Atribuir a um grupo', 'Data': 'Data de criação'})) # Simula o df_aging

    st.markdown("""<style>...</style>""", unsafe_allow_html=True) # Omitido
    
    tab1, tab2 = st.tabs(["Dashboard Completo", "Report Visual"])
    with tab1:
        # (Código da Aba 1, omitido por brevidade)
        pass
    with tab2:
        # (Código da Aba 2, omitido por brevidade)
        pass
