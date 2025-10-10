import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import base64
from datetime import datetime, date
from zoneinfo import ZoneInfo
from github import Github, Auth
from io import StringIO, BytesIO
import streamlit.components.v1 as components
from PIL import Image
from urllib.parse import quote

# --- Configuração da Página ---
st.set_page_config(
    layout="wide",
    page_title="Backlog Copa Energia + Belago",
    page_icon="minilogo.png",
    initial_sidebar_state="collapsed"
)

# --- FUNÇÕES ---
@st.cache_resource
def get_github_repo():
    try:
        auth = Auth.Token(st.secrets["GITHUB_TOKEN"])
        g = Github(auth=auth)
        return g.get_repo("leonirscatolin/dashboard-backlog")
    except Exception as e:
        st.error(f"Erro de conexão com o repositório: {e}")
        st.stop()

def update_github_file(_repo, file_path, file_content):
    commit_message = f"Dados atualizados em {datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M')}"
    try:
        contents = _repo.get_contents(file_path)
        _repo.update_file(contents.path, commit_message, file_content, contents.sha)
        st.sidebar.info(f"Arquivo '{file_path}' atualizado.")
    except Exception:
        _repo.create_file(file_path, commit_message, file_content)
        st.sidebar.info(f"Arquivo '{file_path}' criado.")
    
@st.cache_data(ttl=300)
def read_github_file(_repo, file_path):
    try:
        content_file = _repo.get_contents(file_path)
        content = content_file.decoded_content.decode("utf-8")
        if not content.strip():
            return pd.DataFrame()
        df = pd.read_csv(StringIO(content), delimiter=';', encoding='utf-8')
        df.columns = df.columns.str.strip()
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def read_github_text_file(_repo, file_path):
    try:
        content_file = _repo.get_contents(file_path)
        content = content_file.decoded_content.decode("utf-8")
        dates = {}
        for line in content.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                dates[key.strip()] = value.strip()
        return dates
    except Exception:
        return {}

def process_uploaded_file(uploaded_file):
    if uploaded_file is None:
        return None
    try:
        if uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file)
        else:
            try:
                content = uploaded_file.getvalue().decode('utf-8')
            except UnicodeDecodeError:
                content = uploaded_file.getvalue().decode('latin1')
            df = pd.read_csv(StringIO(content), delimiter=';')
        
        df.columns = df.columns.str.strip()
        output = StringIO()
        df.to_csv(output, index=False, sep=';', encoding='utf-8')
        return output.getvalue().encode('utf-8')
    except Exception as e:
        st.sidebar.error(f"Erro ao ler o arquivo {uploaded_file.name}: {e}")
        return None

# <-- ALTERADO: Função modificada para calcular abertos e fechados
def processar_dados_comparativos(df_atual_com_status, df_15dias):
    contagem_15dias = df_15dias.groupby('Atribuir a um grupo').size().reset_index(name='15 Dias Atrás')
    
    df_abertos_hoje = df_atual_com_status[df_atual_com_status['Status Dia'] == 'Aberto']
    contagem_atual_abertos = df_abertos_hoje.groupby('Atribuir a um grupo').size().reset_index(name='Atual (Abertos)')
    
    df_fechados_hoje = df_atual_com_status[df_atual_com_status['Status Dia'] == 'Fechado']
    contagem_fechados = df_fechados_hoje.groupby('Atribuir a um grupo').size().reset_index(name='Fechados no Dia')

    df_comparativo = pd.merge(contagem_15dias, contagem_atual_abertos, on='Atribuir a um grupo', how='outer')
    df_comparativo = pd.merge(df_comparativo, contagem_fechados, on='Atribuir a um grupo', how='outer')
    df_comparativo.fillna(0, inplace=True)
    
    df_comparativo['Diferença'] = df_comparativo['Atual (Abertos)'] - df_comparativo['15 Dias Atrás']
    
    colunas_int = ['15 Dias Atrás', 'Atual (Abertos)', 'Fechados no Dia', 'Diferença']
    for col in colunas_int:
        if col in df_comparativo.columns:
            df_comparativo[col] = df_comparativo[col].astype(int)
            
    return df_comparativo

def categorizar_idade_vetorizado(dias_series):
    # ... (sem alterações)
    pass

def analisar_aging(df_atual):
    # ... (sem alterações)
    pass

def get_status(row):
    # ... (sem alterações)
    pass


# --- ESTILIZAÇÃO CSS, INTERFACE E LOGIN (Sem alterações, omitido por brevidade) ---
# ...

# --- LÓGICA DE EXIBIÇÃO PARA TODOS ---
try:
    # ... (carregamento de arquivos, scroll, etc. sem alterações)
    
    df_atual = read_github_file(repo, "dados_atuais.csv")
    df_15dias = read_github_file(repo, "dados_15_dias.csv")
    df_fechados = read_github_file(repo, "dados_fechados.csv")
    # ... (resto do carregamento)

    if df_atual.empty or df_15dias.empty:
        st.warning("Ainda não há dados para exibir.")
    else:
        # <-- ALTERADO: Cria coluna de Status em vez de remover linhas
        closed_ticket_ids = []
        if not df_fechados.empty and 'ID do ticket' in df_fechados.columns:
            closed_ticket_ids = df_fechados['ID do ticket'].dropna().unique()
        
        df_atual['Status Dia'] = df_atual['ID do ticket'].apply(lambda x: 'Fechado' if x in closed_ticket_ids else 'Aberto')
        
        # Cria um dataframe apenas com os abertos para o resto da análise
        df_atual_abertos = df_atual[df_atual['Status Dia'] == 'Aberto']

        if closed_ticket_ids:
             num_closed = len(df_atual[df_atual['Status Dia'] == 'Fechado'])
             if num_closed > 0:
                st.info(f"ℹ️ {num_closed} chamados fechados no dia foram identificados e desconsiderados das contagens principais.")

        df_atual_filtrado = df_atual[~df_atual['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
        df_15dias_filtrado = df_15dias[~df_15dias['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
        
        # O resto do dashboard usa apenas os chamados abertos
        df_aging = analisar_aging(df_atual_abertos[~df_atual_abertos['Atribuir a um grupo'].str.contains('RH', case=False, na=False)])
        
        tab1, tab2 = st.tabs(["Dashboard Completo", "Report Visual"])
        with tab1:
            # ... (código dos cards, etc. sem alteração) ...
            
            st.markdown(f"<h3>Comparativo de Backlog: ...</h3>", unsafe_allow_html=True) # Omitido
            
            # <-- ALTERADO: A função de comparativo agora recebe o dataframe completo
            df_comparativo = processar_dados_comparativos(df_atual_filtrado.copy(), df_15dias_filtrado.copy())
            df_comparativo.rename(columns={'Atribuir a um grupo': 'Grupo'}, inplace=True)
            
            # Define a ordem final das colunas
            ordem_final = ['Grupo', '15 Dias Atrás', 'Atual (Abertos)', 'Fechados no Dia', 'Diferença']
            df_comparativo = df_comparativo[ordem_final]
            
            st.dataframe(df_comparativo.set_index('Grupo').style.map(lambda val: 'background-color: #ffcccc' if val > 0 else ('background-color: #ccffcc' if val < 0 else 'background-color: white'), subset=['Diferença']), use_container_width=True)

            # ... (resto do código sem alterações) ...
            pass
except Exception as e:
    st.error(f"Ocorreu um erro ao carregar os dados: {e}")
