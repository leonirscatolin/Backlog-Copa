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
        st.error("Erro de conexão com o repositório. Verifique o GITHUB_TOKEN.")
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
        return pd.read_csv(StringIO(content), delimiter=';', encoding='latin1')
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

def processar_dados_comparativos(df_atual, df_15dias):
    contagem_atual = df_atual.groupby('Atribuir a um grupo').size().reset_index(name='Atual')
    contagem_15dias = df_15dias.groupby('Atribuir a um grupo').size().reset_index(name='15 Dias Atrás')
    df_comparativo = pd.merge(contagem_atual, contagem_15dias, on='Atribuir a um grupo', how='outer').fillna(0)
    df_comparativo['Diferença'] = df_comparativo['Atual'] - df_comparativo['15 Dias Atrás']
    df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']] = df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']].astype(int)
    return df_comparativo

def categorizar_idade_vetorizado(dias_series):
    condicoes = [
        dias_series >= 30, (dias_series >= 21) & (dias_series <= 29),
        (dias_series >= 11) & (dias_series <= 20), (dias_series >= 6) & (dias_series <= 10),
        (dias_series >= 3) & (dias_series <= 5), (dias_series >= 0) & (dias_series <= 2)
    ]
    opcoes = ["30+ dias", "21-29 dias", "11-20 dias", "6-10 dias", "3-5 dias", "0-2 dias"]
    return np.select(condicoes, opcoes, default="Erro de Categoria")

def analisar_aging(df_atual):
    df = df_atual.copy()
    df['Data de criação'] = pd.to_datetime(df['Data de criação'], errors='coerce', dayfirst=True)
    df.dropna(subset=['Data de criação'], inplace=True)
    hoje = pd.to_datetime('today').normalize()
    data_criacao_normalizada = df['Data de criação'].dt.normalize()
    df['Dias em Aberto'] = (hoje - data_criacao_normalizada).dt.days
    df['Faixa de Antiguidade'] = categorizar_idade_vetorizado(df['Dias em Aberto'])
    return df

def get_status(row):
    diferenca = row['Diferença']
    if diferenca > 0: return "Alta Demanda"
    elif diferenca == 0: return "Estável / Atenção"
    else: return "Redução de Backlog"

# <-- ALTERADO: Nova função para processar uploads (CSV ou XLSX)
def process_uploaded_file(uploaded_file):
    if uploaded_file is None:
        return None
    try:
        if uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file)
        else:
            # Para CSV, decodificamos o conteúdo antes de ler
            content = uploaded_file.getvalue().decode('latin1')
            df = pd.read_csv(StringIO(content), delimiter=';', encoding='latin1')
        
        # Converte o DataFrame para uma string CSV para salvar no GitHub
        output = StringIO()
        df.to_csv(output, index=False, sep=';', encoding='latin1')
        return output.getvalue().encode('latin1')
    except Exception as e:
        st.sidebar.error(f"Erro ao ler o arquivo {uploaded_file.name}: {e}")
        return None

# --- ESTILIZAÇÃO CSS ---
st.html("""<style> ... </style>""") # CSS Omitido por brevidade

# --- INTERFACE DO APLICATIVO ---
try:
    logo_copa = Image.open("logo_sidebar.png")
    logo_belago = Image.open("logo_belago.png")
    col1, col2, col3 = st.columns([1, 4, 1])
    with col1: st.image(logo_copa, width=150)
    with col2: st.markdown("<h1 style='text-align: center;'>Backlog Copa Energia + Belago</h1>", unsafe_allow_html=True)
    with col3: st.image(logo_belago, width=150)
except FileNotFoundError:
    st.error("Arquivos de logo não encontrados.")

# --- LÓGICA DE LOGIN E UPLOAD ---
st.sidebar.header("Área do Administrador")
password = st.sidebar.text_input("Senha para atualizar dados:", type="password")
is_admin = password == st.secrets.get("ADMIN_PASSWORD", "")
repo = get_github_repo()
if is_admin:
    st.sidebar.success("Acesso de administrador liberado.")
    st.sidebar.header("Carregar Novos Arquivos")
    
    # <-- ALTERADO: Aceita CSV e XLSX
    file_types = ["csv", "xlsx"]
    uploaded_file_atual = st.sidebar.file_uploader("1. Backlog ATUAL", type=file_types)
    uploaded_file_15dias = st.sidebar.file_uploader("2. Backlog de 15 DIAS ATRÁS", type=file_types)
    uploaded_file_fechados = st.sidebar.file_uploader("3. Chamados FECHADOS no dia (Opcional)", type=file_types)
    
    data_arquivo_15dias = st.sidebar.date_input("Data de referência do arquivo de 15 DIAS", value=date.today())
    
    if st.sidebar.button("Salvar Novos Dados no Site"):
        if uploaded_file_atual and uploaded_file_15dias:
            with st.spinner("Processando e salvando arquivos..."):
                # <-- ALTERADO: Usa a nova função para processar cada arquivo
                content_atual = process_uploaded_file(uploaded_file_atual)
                content_15dias = process_uploaded_file(uploaded_file_15dias)
                content_fechados = process_uploaded_file(uploaded_file_fechados)

                if content_atual is not None and content_15dias is not None:
                    update_github_file(repo, "dados_atuais.csv", content_atual)
                    update_github_file(repo, "dados_15_dias.csv", content_15dias)
                    
                    if content_fechados is not None:
                        update_github_file(repo, "dados_fechados.csv", content_fechados)
                    else:
                        update_github_file(repo, "dados_fechados.csv", "")

                    data_do_upload = date.today()
                    agora_correta = datetime.now(ZoneInfo("America/Sao_Paulo"))
                    hora_atualizacao = agora_correta.strftime('%H:%M')
                    datas_referencia_content = (f"data_atual:{data_do_upload.strftime('%d/%m/%Y')}\n" f"data_15dias:{data_arquivo_15dias.strftime('%d/%m/%Y')}\n" f"hora_atualizacao:{hora_atualizacao}")
                    update_github_file(repo, "datas_referencia.txt", datas_referencia_content)

                    read_github_text_file.clear()
                    read_github_file.clear()
                    st.sidebar.success("Dados salvos com sucesso!")
        else:
            st.sidebar.warning("Carregue os arquivos obrigatórios (Atual e 15 Dias) para salvar.")
elif password:
    st.sidebar.error("Senha incorreta.")

# --- LÓGICA DE EXIBIÇÃO PARA TODOS ---
try:
    # O restante do código de exibição continua exatamente o mesmo
    # ...
    pass 
except Exception as e:
    st.error(f"Ocorreu um erro ao carregar os dados: {e}")

# (O restante do seu código de exibição, que não precisa de alterações, foi omitido para encurtar a resposta)
