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

# <-- ALTERADO: Função de comparativo volta à versão original, mais simples
def processar_dados_comparativos(df_atual, df_15dias):
    contagem_atual = df_atual.groupby('Atribuir a um grupo').size().reset_index(name='Atual')
    contagem_15dias = df_15dias.groupby('Atribuir a um grupo').size().reset_index(name='15 Dias Atrás')
    df_comparativo = pd.merge(contagem_atual, contagem_15dias, on='Atribuir a um grupo', how='outer').fillna(0)
    df_comparativo['Diferença'] = df_comparativo['Atual'] - df_comparativo['15 Dias Atrás']
    df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']] = df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']].astype(int)
    return df_comparativo

def categorizar_idade_vetorizado(dias_series):
    condicoes = [
        dias_series >= 30,
        (dias_series >= 21) & (dias_series <= 29),
        (dias_series >= 11) & (dias_series <= 20),
        (dias_series >= 6) & (dias_series <= 10),
        (dias_series >= 3) & (dias_series <= 5),
        (dias_series >= 0) & (dias_series <= 2)
    ]
    opcoes = ["30+ dias", "21-29 dias", "11-20 dias", "6-10 dias", "3-5 dias", "0-2 dias"]
    return np.select(condicoes, opcoes, default="Erro de Categoria")

def analisar_aging(df_atual):
    df = df_atual.copy()
    df['Data de criação'] = pd.to_datetime(df['Data de criação'], errors='coerce', dayfirst=True)
    df.dropna(subset=['Data de criação'], inplace=True)
    
    hoje = pd.to_datetime('today')
    data_criacao_normalizada = df['Data de criação'].dt.normalize()
    
    df['Dias em Aberto'] = (hoje - data_criacao_normalizada).dt.days
    df['Faixa de Antiguidade'] = categorizar_idade_vetorizado(df['Dias em Aberto'])
    return df

def get_status(row):
    diferenca = row['Diferença']
    if diferenca > 0: return "Alta Demanda"
    elif diferenca == 0: return "Estável / Atenção"
    else: return "Redução de Backlog"

# --- ESTILIZAÇÃO CSS ---
st.html("""<style>...</style>""") # Omitido

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
# (Sem alterações, omitido por brevidade)
st.sidebar.header("Área do Administrador")
password = st.sidebar.text_input("Senha para atualizar dados:", type="password")
is_admin = password == st.secrets.get("ADMIN_PASSWORD", "")
repo = get_github_repo()
if is_admin:
    st.sidebar.success("Acesso de administrador liberado.")
    st.sidebar.header("Carregar Novos Arquivos")
    file_types = ["csv", "xlsx"]
    uploaded_file_atual = st.sidebar.file_uploader("1. Backlog ATUAL", type=file_types)
    uploaded_file_15dias = st.sidebar.file_uploader("2. Backlog de 15 DIAS ATRÁS", type=file_types)
    uploaded_file_fechados = st.sidebar.file_uploader("3. Chamados FECHADOS no dia (Opcional)", type=file_types)
    data_arquivo_15dias = st.sidebar.date_input("Data de referência do arquivo de 15 DIAS", value=date.today())
    if st.sidebar.button("Salvar Novos Dados no Site"):
        if uploaded_file_atual and uploaded_file_15dias:
            with st.spinner("Processando e salvando arquivos..."):
                content_atual = process_uploaded_file(uploaded_file_atual)
                content_15dias = process_uploaded_file(uploaded_file_15dias)
                content_fechados = process_uploaded_file(uploaded_file_fechados)
                if content_atual is not None and content_15dias is not None:
                    update_github_file(repo, "dados_atuais.csv", content_atual)
                    update_github_file(repo, "dados_15_dias.csv", content_15dias)
                    if content_fechados is not None:
                        update_github_file(repo, "dados_fechados.csv", content_fechados)
                    else:
                        update_github_file(repo, "dados_fechados.csv", b"")
                    data_do_upload = date.today()
                    agora_correta = datetime.now(ZoneInfo("America/Sao_Paulo"))
                    hora_atualizacao = agora_correta.strftime('%H:%M')
                    datas_referencia_content = (f"data_atual:{data_do_upload.strftime('%d/%m/%Y')}\n" f"data_15dias:{data_arquivo_15dias.strftime('%d/%m/%Y')}\n" f"hora_atualizacao:{hora_atualizacao}")
                    update_github_file(repo, "datas_referencia.txt", datas_referencia_content.encode('utf-8'))
                    read_github_text_file.clear()
                    read_github_file.clear()
                    st.sidebar.success("Dados salvos com sucesso!")
        else:
            st.sidebar.warning("Carregue os arquivos obrigatórios (Atual e 15 Dias) para salvar.")
elif password:
    st.sidebar.error("Senha incorreta.")


# --- LÓGICA DE EXIBIÇÃO PARA TODOS ---
try:
    needs_scroll = "faixa" in st.query_params
    if "faixa" in st.query_params:
        faixa_from_url = st.query_params.get("faixa")
        ordem_faixas_validas = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
        if faixa_from_url in ordem_faixas_validas:
             st.session_state.faixa_selecionada = faixa_from_url
    if "scroll" in st.query_params or "faixa" in st.query_params:
        st.query_params.clear()

    df_atual = read_github_file(repo, "dados_atuais.csv")
    df_15dias = read_github_file(repo, "dados_15_dias.csv")
    df_fechados = read_github_file(repo, "dados_fechados.csv")
    datas_referencia = read_github_text_file(repo, "datas_referencia.txt")
    data_atual_str = datas_referencia.get('data_atual', 'N/A')
    data_15dias_str = datas_referencia.get('data_15dias', 'N/A')
    hora_atualizacao_str = datas_referencia.get('hora_atualizacao', '')

    if df_atual.empty or df_15dias.empty:
        st.warning("Ainda não há dados para exibir.")
    else:
        # <-- ALTERADO: Separa os chamados em Abertos e Encerrados
        closed_ticket_ids = []
        if not df_fechados.empty and 'ID do ticket' in df_fechados.columns:
            closed_ticket_ids = df_fechados['ID do ticket'].dropna().unique()

        df_encerrados = df_atual[df_atual['ID do ticket'].isin(closed_ticket_ids)]
        df_abertos = df_atual[~df_atual['ID do ticket'].isin(closed_ticket_ids)]

        if not df_encerrados.empty:
            st.info(f"ℹ️ {len(df_encerrados)} chamados fechados no dia foram deduzidos das contagens principais.")
        
        # Filtra RH dos dataframes separados
        df_atual_filtrado = df_abertos[~df_abertos['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
        df_15dias_filtrado = df_15dias[~df_15dias['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
        
        # O resto do dashboard usa apenas os chamados ABERTOS
        df_aging = analisar_aging(df_atual_filtrado)
        
        tab1, tab2 = st.tabs(["Dashboard Completo", "Report Visual"])
        with tab1:
            st.info("""**Filtros e Regras Aplicadas:**\n- Grupos contendo 'RH' foram desconsiderados da análise.\n- A idade do chamado é o número de dias inteiros desde a criação.""")
            st.subheader("Análise de Antiguidade do Backlog Atual")

            texto_hora = f" (atualizado às {hora_atualizacao_str})" if hora_atualizacao_str else ""
            st.markdown(f"<p style='font-size: 0.9em; color: #666;'><i>Data de referência: {data_atual_str}{texto_hora}</i></p>", unsafe_allow_html=True)

            if not df_aging.empty:
                total_chamados = len(df_aging)
                _, col_total, _ = st.columns([2, 1.5, 2])
                with col_total: st.markdown(f"""<div class="metric-box"><span class="value">{total_chamados}</span><span class="label">Total de Chamados</span></div>""", unsafe_allow_html=True)
                st.markdown("---")
                aging_counts = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
                aging_counts.columns = ['Faixa de Antiguidade', 'Quantidade']
                ordem_faixas = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
                todas_as_faixas = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas})
                aging_counts = pd.merge(todas_as_faixas, aging_counts, on='Faixa de Antiguidade', how='left').fillna(0).astype({'Quantidade': int})
                aging_counts['Faixa de Antiguidade'] = pd.Categorical(aging_counts['Faixa de Antiguidade'], categories=ordem_faixas, ordered=True)
                aging_counts = aging_counts.sort_values('Faixa de Antiguidade')
                if 'faixa_selecionada' not in st.session_state:
                    st.session_state.faixa_selecionada = "3-5 dias"
                cols = st.columns(len(ordem_faixas))
                for i, row in aging_counts.iterrows():
                    with cols[i]:
                        faixa_encoded = quote(row['Faixa de Antiguidade'])
                        card_html = f"""<a href="?faixa={faixa_encoded}&scroll=true" target="_self" class="metric-box"><span class="value">{row['Quantidade']}</span><span class="label">{row['Faixa de Antiguidade']}</span></a>"""
                        st.markdown(card_html, unsafe_allow_html=True)
            else: st.warning("Nenhum dado válido para a análise de antiguidade.")
            
            st.markdown(f"<h3>Comparativo de Backlog: Atual vs. 15 Dias Atrás <span style='font-size: 0.6em; color: #666; font-weight: normal;'>({data_15dias_str})</span></h3>", unsafe_allow_html=True)
            
            df_comparativo = processar_dados_comparativos(df_atual_filtrado.copy(), df_15dias_filtrado.copy())
            df_comparativo['Status'] = df_comparativo.apply(get_status, axis=1)
            df_comparativo.rename(columns={'Atribuir a um grupo': 'Grupo'}, inplace=True)
            df_comparativo = df_comparativo[['Grupo', '15 Dias Atrás', 'Atual', 'Diferença', 'Status']]
            st.dataframe(df_comparativo.set_index('Grupo').style.map(lambda val: 'background-color: #ffcccc' if val > 0 else ('background-color: #ccffcc' if val < 0 else 'background-color: white'), subset=['Diferença']), use_container_width=True)

            # <-- ALTERADO: Adiciona a nova tabela de chamados encerrados
            st.markdown("---")
            st.subheader("Chamados Encerrados no Dia")
            if not df_encerrados.empty:
                df_encerrados_filtrado = df_encerrados[~df_encerrados['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
                st.data_editor(
                    df_encerrados_filtrado[['ID do ticket', 'Descrição', 'Atribuir a um grupo']],
                    hide_index=True, disabled=True, use_container_width=True
                )
            else:
                st.info("Nenhum chamado da lista de fechados foi encontrado no backlog atual.")

            if not df_aging.empty:
                st.markdown("---")
                st.subheader("Detalhar e Buscar Chamados")
                
                # ... (resto do código da tab1 e tab2 sem alterações)
                pass

except Exception as e:
    st.error(f"Ocorreu um erro ao carregar os dados: {e}")

# (O restante do seu código de exibição foi omitido para encurtar a resposta)
