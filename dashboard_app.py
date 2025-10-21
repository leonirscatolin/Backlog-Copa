import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import base64
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from github import Github, Auth, GithubException
from io import StringIO, BytesIO
import streamlit.components.v1 as components
from PIL import Image
from urllib.parse import quote
import json

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

def update_github_file(_repo, file_path, file_content, commit_message):
    try:
        contents = _repo.get_contents(file_path)
        _repo.update_file(contents.path, commit_message, file_content, contents.sha)
        if file_path != "contacted_tickets.json":
            st.sidebar.info(f"Arquivo '{file_path}' atualizado com sucesso.")
    except GithubException as e:
        if e.status == 404:
            _repo.create_file(file_path, commit_message, file_content)
            if file_path != "contacted_tickets.json":
                st.sidebar.info(f"Arquivo '{file_path}' criado com sucesso.")
        else:
            st.sidebar.error(f"Falha ao salvar '{file_path}': {e}")

@st.cache_data(ttl=300)
def read_github_file(_repo, file_path):
    try:
        content_file = _repo.get_contents(file_path)
        content = content_file.decoded_content.decode("utf-8")
        if not content.strip():
            return pd.DataFrame()
        df = pd.read_csv(StringIO(content), delimiter=';', encoding='utf-8', dtype={'ID do ticket': str, 'ID do Ticket': str})
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"Erro ao ler arquivo do GitHub '{file_path}': {e}")
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
        return None, 0
    try:
        # Lê o arquivo para memória para obter o conteúdo e a contagem de linhas
        file_buffer = BytesIO(uploaded_file.getvalue())
        if uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(file_buffer)
        else:
            # Tenta diferentes delimitadores
            try:
                df = pd.read_csv(file_buffer, delimiter=';')
            except Exception:
                file_buffer.seek(0) # Reseta o buffer
                df = pd.read_csv(file_buffer, delimiter=',')

        num_rows = len(df)
        
        # Reconstrói o CSV com o delimitador padrão (;) para consistência
        output = StringIO()
        df.to_csv(output, index=False, sep=';', encoding='utf-8')
        return output.getvalue().encode('utf-8'), num_rows
    except Exception as e:
        st.sidebar.error(f"Erro ao processar o arquivo {uploaded_file.name}: {e}")
        return None, 0

# ... (outras funções permanecem iguais) ...
@st.cache_data
def analisar_aging(_df_atual):
    df = _df_atual.copy()
    date_col_name = None
    if 'Data de criação' in df.columns: date_col_name = 'Data de criação'
    elif 'Data de Criacao' in df.columns: date_col_name = 'Data de Criacao'

    if not date_col_name:
        st.error("Nenhuma coluna de data ('Data de criação' ou 'Data de Criacao') foi encontrada no arquivo.")
        return pd.DataFrame()

    df[date_col_name] = pd.to_datetime(df[date_col_name], errors='coerce')
    
    linhas_invalidas = df[df[date_col_name].isna()]
    if not linhas_invalidas.empty:
        with st.expander(f"⚠️ Atenção: {len(linhas_invalidas)} chamados foram descartados por data inválida ou vazia. Clique para ver exemplos:"):
            st.write("Estas são algumas das linhas com datas que não puderam ser reconhecidas e foram removidas da análise:")
            st.dataframe(linhas_invalidas.head())
    
    df.dropna(subset=[date_col_name], inplace=True)
    
    hoje = pd.to_datetime('today')
    data_criacao_normalizada = df[date_col_name].dt.normalize()
    
    dias_calculados = (hoje - data_criacao_normalizada).dt.days
    df['Dias em Aberto'] = (dias_calculados - 1).clip(lower=0) 
    
    df['Faixa de Antiguidade'] = categorizar_idade_vetorizado(df['Dias em Aberto'])
    return df

def get_status(row):
    diferenca = row['Diferença']
    if diferenca > 0: return "Alta Demanda"
    elif diferenca == 0: return "Estável / Atenção"
    else: return "Redução de Backlog"

def get_image_as_base64(path):
    try:
        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode()
    except FileNotFoundError:
        return None

def sync_contacted_tickets():
    previous_state = set(st.session_state.contacted_tickets)

    for row_index, changes in st.session_state.ticket_editor['edited_rows'].items():
        ticket_id = st.session_state.last_filtered_df.iloc[row_index]['ID do ticket']
        if 'Contato' in changes:
            if changes['Contato']:
                st.session_state.contacted_tickets.add(ticket_id)
            else:
                st.session_state.contacted_tickets.discard(ticket_id)

    if previous_state != st.session_state.contacted_tickets:
        data_to_save = list(st.session_state.contacted_tickets)
        json_content = json.dumps(data_to_save, indent=4)
        commit_msg = f"Atualizando tickets contatados em {datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M')}"
        
        update_github_file(st.session_state.repo, "contacted_tickets.json", json_content.encode('utf-8'), commit_msg)
    
    st.session_state.scroll_to_details = True

# --- INTERFACE E LÓGICA PRINCIPAL ---
st.set_page_config(layout="wide", page_title="Backlog Copa Energia + Belago", page_icon="minilogo.png", initial_sidebar_state="collapsed")
st.html("""<style>...</style>""") # CSS omitido para brevidade

logo_copa_b64 = get_image_as_base64("logo_sidebar.png")
logo_belago_b64 = get_image_as_base64("logo_belago.png")
# ... (código do cabeçalho omitido para brevidade) ...

st.sidebar.header("Área do Administrador")
password = st.sidebar.text_input("Senha para atualizar dados:", type="password")
is_admin = password == st.secrets.get("ADMIN_PASSWORD", "")
repo = get_github_repo()
st.session_state.repo = repo 

if is_admin:
    st.sidebar.success("Acesso de administrador liberado.")
    st.sidebar.header("Carregar Novos Arquivos")
    
    file_types = ["csv", "xlsx"]
    uploaded_file_atual = st.sidebar.file_uploader("1. Backlog ATUAL", type=file_types)
    uploaded_file_15dias = st.sidebar.file_uploader("2. Backlog de 15 DIAS ATRÁS", type=file_types)
    uploaded_file_fechados = st.sidebar.file_uploader("3. Chamados FECHADOS no dia (Opcional)", type=file_types)
    
    if st.sidebar.button("Salvar Novos Dados no Site"):
        if uploaded_file_atual and uploaded_file_15dias:
            with st.spinner("Processando e salvando arquivos..."):
                commit_msg = f"Dados atualizados em {datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M')}"
                
                # Processa os arquivos e obtém a contagem de linhas
                content_atual, num_rows_atual = process_uploaded_file(uploaded_file_atual)
                content_15dias, _ = process_uploaded_file(uploaded_file_15dias)
                content_fechados, _ = process_uploaded_file(uploaded_file_fechados)

                # ######################## DIAGNÓSTICO 1 ########################
                st.sidebar.info(f"Diagnóstico: O arquivo '{uploaded_file_atual.name}' que você selecionou contém {num_rows_atual} linhas de dados.")

                if content_atual is not None and content_15dias is not None:
                    update_github_file(repo, "dados_atuais.csv", content_atual, commit_msg)
                    update_github_file(repo, "dados_15_dias.csv", content_15dias, commit_msg)
                    
                    if content_fechados is not None:
                        update_github_file(repo, "dados_fechados.csv", content_fechados, commit_msg)
                    else:
                        update_github_file(repo, "dados_fechados.csv", b"", commit_msg)

                    # ... (código de atualização de datas de referência omitido) ...

                    read_github_file.clear() # Limpa o cache para forçar a releitura
                    read_github_text_file.clear()
                    st.sidebar.success("Processo finalizado! Recarregando a página...")
                    st.experimental_rerun() # Força o recarregamento completo
        else:
            st.sidebar.warning("Carregue os arquivos obrigatórios (Atual e 15 Dias) para salvar.")
elif password:
    st.sidebar.error("Senha incorreta.")

try:
    # ######################## DIAGNÓSTICO 2 ########################
    try:
        last_commit = repo.get_commits(path="dados_atuais.csv")[0]
        last_commit_date = last_commit.commit.author.date
        last_commit_date_br = last_commit_date.astimezone(ZoneInfo("America/Sao_Paulo"))
        st.info(f"ℹ️ Exibindo dados do arquivo 'dados_atuais.csv' salvo no GitHub em: **{last_commit_date_br.strftime('%d/%m/%Y às %H:%M:%S')}**")
    except Exception:
        st.warning("Não foi possível verificar a data da última atualização do arquivo de dados.")

    # ... (o resto do código principal permanece o mesmo) ...

    # Inicialização do session state e lógica de rolagem
    if 'contacted_tickets' not in st.session_state:
        try:
            file_content = repo.get_contents("contacted_tickets.json").decoded_content.decode("utf-8")
            st.session_state.contacted_tickets = set(json.loads(file_content))
        except GithubException as e:
            if e.status == 404: st.session_state.contacted_tickets = set()
            else: st.error(f"Erro ao carregar o estado dos tickets: {e}"); st.session_state.contacted_tickets = set()
    
    # ... (código de leitura de dados, filtros, e exibição das abas omitido para brevidade, pois permanece igual) ...

except Exception as e:
    st.error(f"Ocorreu um erro ao carregar os dados: {e}")

# ... (o código completo das abas e seus conteúdos precisa ser inserido aqui a partir da versão anterior)
