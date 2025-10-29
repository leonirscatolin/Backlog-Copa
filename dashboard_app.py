# VERSÃO v0.9.30-740 (Corrigida - NameError + Fixes Anteriores)

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
# from PIL import Image # PIL não está sendo usado
from urllib.parse import quote
import json
import colorsys
import re

# ==========================================================
# ||           DEFINIÇÃO DA FUNÇÃO MOVIDA PARA CIMA       ||
# ==========================================================
@st.cache_data
def get_image_as_base64(path):
    """Lê um arquivo de imagem e retorna como string base64."""
    try:
        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode()
    except FileNotFoundError:
        st.warning(f"Arquivo de imagem não encontrado: {path}")
        return None
    except Exception as e:
         st.error(f"Erro ao ler imagem {path}: {e}")
         return None
# ==========================================================

st.set_page_config(
    layout="wide",
    page_title="Backlog Copa Energia + Belago",
    page_icon="minilogo.png", # Certifique-se que este arquivo existe na raiz
    initial_sidebar_state="collapsed"
)

# ==========================================================
# ||           LISTA DE GRUPOS OCULTOS - GLOBAL           ||
# ==========================================================
grupos_excluidos = ['Aprovadores GGM', 'liq liq-sutel', 'liq-sutel']
# ==========================================================


st.html("""
<style>
#GithubIcon { visibility: hidden; }
/* Estilos CSS (mantidos como antes) */
.metric-box {
    border: 1px solid #CCCCCC; padding: 10px; border-radius: 5px; text-align: center;
    box-shadow: 0px 2px 4px rgba(0,0,0,0.1); margin-bottom: 10px; height: 120px;
    display: flex; flex-direction: column; justify-content: center;
}
a.metric-box { display: block; color: inherit; text-decoration: none !important; }
a.metric-box:hover { background-color: #f0f2f6; text-decoration: none !important; }
.metric-box span { display: block; width: 100%; text-decoration: none !important; }
.metric-box .label { font-size: 1em; color: #666666; margin-bottom: 5px; }
.metric-box .value { font-size: 2.5em; font-weight: bold; color: #375623; }
.metric-box .delta { font-size: 0.9em; margin-top: 5px; }
.delta-positive { color: #d9534f; }
.delta-negative { color: #5cb85c; }
.delta-neutral { color: #666666; }
</style>
""")


@st.cache_resource
def get_github_repo():
    """Conecta ao repositório GitHub usando segredos."""
    try:
        expected_repo_name = st.secrets.get("EXPECTED_REPO")
        if not expected_repo_name:
            st.error("Configuração incompleta: Segredo EXPECTED_REPO não encontrado.")
            st.stop()
        github_token = st.secrets.get("GITHUB_TOKEN")
        if not github_token:
             st.error("Configuração incompleta: Segredo GITHUB_TOKEN não encontrado.")
             st.stop()
        auth = Auth.Token(github_token)
        g = Github(auth=auth)
        try:
             _ = g.get_user().login # Valida token
        except GithubException as auth_err:
             if auth_err.status == 401:
                  st.error("Erro GitHub (401): Token inválido ou expirado.")
                  st.stop()
             raise
        
        # Tenta obter o repositório
        repo = g.get_repo(expected_repo_name)
        st.sidebar.caption(f"Conectado a: {repo.full_name}") # Feedback visual
        return repo
        
    except GithubException as e:
        if e.status == 404:
            st.error(f"Erro GitHub (404): Repositório '{expected_repo_name}' não encontrado ou token sem permissão.")
        elif e.status == 401:
             st.error("Erro GitHub (401): Token inválido ou expirado.")
        else:
            st.error(f"Erro GitHub ({e.status}): {e.data.get('message', 'Erro desconhecido')}")
        st.stop()
    except Exception as e:
        st.error(f"Erro inesperado ao conectar ao GitHub: {e}")
        st.stop()

def update_github_file(_repo, file_path, file_content, commit_message):
    """Cria ou atualiza um arquivo no GitHub, tratando conflitos."""
    # Garante que _repo é válido
    if _repo is None:
         st.sidebar.error(f"Erro interno: Tentativa de salvar '{file_path}' sem conexão ao repositório.")
         return # Não levanta exceção, mas impede a operação

    try:
        contents = _repo.get_contents(file_path)
        sha = contents.sha
        if isinstance(file_content, str):
            file_content_bytes = file_content.encode('utf-8')
        else:
            file_content_bytes = file_content # Assume bytes

        # Evita commit se conteúdo for idêntico
        if contents.decoded_content == file_content_bytes:
             if file_path not in ["contacted_tickets.json", "ticket_observations.json", "datas_referencia.txt"]:
                  st.sidebar.info(f"'{file_path}' já atualizado.")
             return 

        _repo.update_file(contents.path, commit_message, file_content_bytes, sha)
        if file_path not in ["contacted_tickets.json", "ticket_observations.json", "datas_referencia.txt"]: 
            st.sidebar.info(f"'{file_path}' atualizado.")
            
    except GithubException as e:
        if e.status == 404: # Cria arquivo
            if isinstance(file_content, str):
                file_content_bytes = file_content.encode('utf-8')
            else:
                file_content_bytes = file_content
            _repo.create_file(file_path, commit_message, file_content_bytes)
            if file_path not in ["contacted_tickets.json", "ticket_observations.json", "datas_referencia.txt"]: 
                st.sidebar.info(f"'{file_path}' criado.")
        elif e.status == 409: # Conflito
             st.sidebar.error(f"Conflito ao salvar '{file_path}': Modificado no GitHub. Recarregue e tente novamente.")
             # Não levanta exceção, usuário precisa recarregar
        else:
            st.sidebar.error(f"Erro GitHub ({e.status}) ao salvar '{file_path}': {e.data.get('message', 'Erro desconhecido')}")
            raise # Re-levanta outros erros

@st.cache_data(ttl=300) # Cache por 5 minutos
def read_github_file(_repo, file_path):
    """Lê um arquivo CSV do GitHub, tratando encoding e erros."""
    if _repo is None:
         st.error(f"Erro interno: Tentativa de ler '{file_path}' sem conexão ao repositório.")
         return pd.DataFrame()

    try:
        content_file = _repo.get_contents(file_path)
        content_bytes = content_file.decoded_content

        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content = content_bytes.decode("latin-1")
                if file_path == "dados_fechados.csv": 
                    st.sidebar.warning(f"'{file_path}' lido como Latin-1.")
            except Exception as decode_err:
                    st.error(f"Erro ao decodificar '{file_path}': {decode_err}")
                    return pd.DataFrame() 

        if not content.strip():
             return pd.DataFrame()

        try:
                # Dtypes explícitos para colunas de ID são cruciais
                dtype_map = {col: str for col in ['ID do ticket', 'ID do Ticket', 'ID'] }
                df = pd.read_csv(StringIO(content), delimiter=';', # Assume ; como padrão
                                     dtype=dtype_map, # Aplica dtype apenas onde encontrar
                                     low_memory=False,
                                     on_bad_lines='warn') 
        except pd.errors.ParserError as parse_err:
                st.error(f"Erro ao parsear CSV '{file_path}': {parse_err}. Verifique delimitador e estrutura.")
                return pd.DataFrame()
        except Exception as read_err:
                st.error(f"Erro inesperado ao ler CSV de '{file_path}': {read_err}")
                return pd.DataFrame()

        df.columns = df.columns.str.strip() 
        df.dropna(how='all', inplace=True) 
        return df

    except GithubException as e:
        if e.status == 404:
             return pd.DataFrame() # Silencioso se não existe
        st.error(f"Erro GitHub ({e.status}) ao ler '{file_path}': {e.data.get('message', 'Erro desconhecido')}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro inesperado ao ler '{file_path}': {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def read_github_text_file(_repo, file_path):
    """Lê um arquivo de texto simples (como datas_referencia.txt)."""
    if _repo is None: return {}
    try:
        content_file = _repo.get_contents(file_path)
        content = content_file.decoded_content.decode("utf-8")
        data = {}
        for line in content.strip().split('\n'):
            if ':' in line and line.strip(): 
                key, value = line.split(':', 1)
                data[key.strip()] = value.strip()
        return data
    except GithubException as e:
        if e.status == 404: return {} 
        else: st.warning(f"Erro GitHub ao ler {file_path}: {e.data.get('message', e)}")
        return {}
    except Exception as e:
        st.warning(f"Erro inesperado ao ler {file_path}: {e}")
        return {}

@st.cache_data(ttl=300)
def read_github_json_dict(_repo, file_path):
    """Lê um arquivo JSON do GitHub e retorna como dicionário."""
    if _repo is None: return {}
    try:
        file_content_obj = _repo.get_contents(file_path)
        file_content_str = file_content_obj.decoded_content.decode("utf-8")
        return json.loads(file_content_str) if file_content_str.strip() else {} 
    except GithubException as e:
        if e.status == 404: return {} 
        st.error(f"Erro GitHub ao carregar JSON '{file_path}': {e.data.get('message', e)}")
        return {}
    except json.JSONDecodeError:
        st.warning(f"Arquivo JSON '{file_path}' vazio ou inválido.")
        return {}
    except Exception as e:
        st.error(f"Erro inesperado ao ler JSON '{file_path}': {e}")
        return {}

def process_uploaded_file(uploaded_file):
    """Processa arquivo carregado (Excel ou CSV) e retorna bytes CSV UTF-8."""
    if uploaded_file is None: return None
    try:
        dtype_spec = {col: str for col in ['ID do ticket', 'ID do Ticket', 'ID'] }
        
        if uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file, dtype=dtype_spec, sheet_name=0) 
        else: 
            try:
                content_bytes = uploaded_file.getvalue()
                try: 
                     content = content_bytes.decode('utf-8')
                     df = pd.read_csv(StringIO(content), delimiter=';', dtype=dtype_spec) 
                except UnicodeDecodeError:
                     content = content_bytes.decode('latin1')
                     st.sidebar.warning(f"{uploaded_file.name} lido como Latin-1.")
                     df = pd.read_csv(StringIO(content), delimiter=';', dtype=dtype_spec) 
            except Exception as read_err: 
                 st.sidebar.error(f"Erro ao ler CSV {uploaded_file.name}: {read_err}")
                 return None

        df.columns = df.columns.str.strip()
        df.dropna(how='all', inplace=True) 

        output = StringIO()
        df.to_csv(output, index=False, sep=';', encoding='utf-8')
        return output.getvalue().encode('utf-8')
        
    except Exception as e: 
        st.sidebar.error(f"Erro ao processar {uploaded_file.name}: {e}")
        return None

def processar_dados_comparativos(df_atual, df_15dias):
    """Compara contagem de chamados por grupo entre dois dataframes."""
    if df_atual is None or df_atual.empty or 'Atribuir a um grupo' not in df_atual.columns:
         st.warning("Dados atuais inválidos para comparação.")
         # Retorna estrutura vazia se dados atuais falham
         return pd.DataFrame(columns=['Grupo', '15 Dias Atrás', 'Atual', 'Diferença', 'Status'])

    contagem_atual = df_atual.groupby('Atribuir a um grupo').size().reset_index(name='Atual')

    # Trata caso onde df_15dias é inválido
    if df_15dias is None or df_15dias.empty or 'Atribuir a um grupo' not in df_15dias.columns:
         st.warning("Dados de 15 dias atrás inválidos. Comparativo mostrará apenas totais atuais.")
         df_comparativo = contagem_atual.copy()
         df_comparativo['15 Dias Atrás'] = 0
         df_comparativo['Diferença'] = df_comparativo['Atual'] # Diferença é o próprio total atual
    else:
         contagem_15dias = df_15dias.groupby('Atribuir a um grupo').size().reset_index(name='15 Dias Atrás')
         df_comparativo = pd.merge(contagem_atual, contagem_15dias, on='Atribuir a um grupo', how='outer').fillna(0)
         df_comparativo['Diferença'] = df_comparativo['Atual'] - df_comparativo['15 Dias Atrás']
    
    # Aplica tipos e status em ambos os casos
    df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']] = df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']].astype(int)
    df_comparativo['Status'] = df_comparativo.apply(get_status, axis=1)
    df_comparativo.rename(columns={'Atribuir a um grupo': 'Grupo'}, inplace=True)
    
    return df_comparativo[['Grupo', '15 Dias Atrás', 'Atual', 'Diferença', 'Status']]


@st.cache_data
def categorizar_idade_vetorizado(dias_series):
    # ... (código categorizar_idade_vetorizado) ...
    condicoes = [
        dias_series >= 30, (dias_series >= 21) & (dias_series <= 29),
        (dias_series >= 11) & (dias_series <= 20), (dias_series >= 6) & (dias_series <= 10),
        (dias_series >= 3) & (dias_series <= 5), (dias_series >= 0) & (dias_series <= 2)
    ]
    opcoes = ["30+ dias", "21-29 dias", "11-20 dias", "6-10 dias", "3-5 dias", "0-2 dias"]
    return np.select(condicoes, opcoes, default="Inválido") 

@st.cache_data
def analisar_aging(_df_atual):
    # ... (código analisar_aging com depuração adicional) ...
    if _df_atual is None or _df_atual.empty:
         st.warning("analisar_aging recebeu DataFrame vazio.") 
         return pd.DataFrame()
         
    df = _df_atual.copy()
    date_col_name = None
    if 'Data de criação' in df.columns: date_col_name = 'Data de criação'
    elif 'Data de Criacao' in df.columns: date_col_name = 'Data de Criacao'
    
    if not date_col_name:
        st.warning(f"Coluna de data não encontrada em analisar_aging. Cols: {df.columns.tolist()}")
        return pd.DataFrame(columns=list(df.columns) + ['Dias em Aberto', 'Faixa de Antiguidade']) 
    
    original_dtype = df[date_col_name].dtype
    df[date_col_name] = pd.to_datetime(df[date_col_name], errors='coerce')
    
    linhas_invalidas = df[df[date_col_name].isna() & _df_atual[date_col_name].notna()]
    if not linhas_invalidas.empty:
        with st.expander(f"⚠️ Atenção (analisar_aging): {len(linhas_invalidas)} chamados descartados por data inválida ('{date_col_name}', tipo: {original_dtype})."):
             colunas_debug = [col for col in ['ID do ticket', date_col_name, 'Atribuir a um grupo'] if col in linhas_invalidas.columns]
             # Mostra valor original da data que falhou
             st.dataframe(linhas_invalidas[colunas_debug].head().assign(**{date_col_name:_df_atual.loc[linhas_invalidas.index, date_col_name].head()}))

    df = df.dropna(subset=[date_col_name]) 
    if df.empty:
        st.warning(f"Nenhum chamado com data válida ('{date_col_name}') após limpeza em analisar_aging.")
        return pd.DataFrame(columns=list(df.columns) + ['Dias em Aberto', 'Faixa de Antiguidade'])

    hoje = pd.to_datetime('today').normalize()
    data_criacao_normalizada = df[date_col_name].dt.normalize() 
    dias_calculados = (hoje - data_criacao_normalizada).dt.days
    
    df['Dias em Aberto'] = (dias_calculados - 1).clip(lower=0) 
    df['Faixa de Antiguidade'] = categorizar_idade_vetorizado(df['Dias em Aberto'])
    
    invalid_categories = df[df['Faixa de Antiguidade'] == 'Inválido']
    if not invalid_categories.empty:
         st.warning(f"{len(invalid_categories)} chamados com idade inválida (categoria 'Inválido') em analisar_aging.")
         
    # Garante que as novas colunas existem mesmo se algo der errado antes
    if 'Dias em Aberto' not in df.columns: df['Dias em Aberto'] = -1 # Valor inválido
    if 'Faixa de Antiguidade' not in df.columns: df['Faixa de Antiguidade'] = 'Erro'

    # Retorna colunas originais + novas
    return df[list(_df_atual.columns) + ['Dias em Aberto', 'Faixa de Antiguidade']]


def get_status(row):
    # ... (código get_status) ...
    diferenca = row.get('Diferença', 0) 
    if diferenca > 0: return "Alta Demanda"
    elif diferenca == 0: return "Estável / Atenção"
    else: return "Redução de Backlog"

# ... (código sync_ticket_data) ...
def sync_ticket_data():
    if 'ticket_editor' not in st.session_state or not st.session_state.ticket_editor.get('edited_rows'):
        return
    edited_rows = st.session_state.ticket_editor['edited_rows']
    contact_changed = False
    observation_changed = False
    original_contacts = st.session_state.contacted_tickets.copy()
    original_observations = st.session_state.observations.copy()

    try:
        for row_index, changes in edited_rows.items():
            try:
                ticket_id = str(st.session_state.last_filtered_df.iloc[row_index].get('ID do ticket', None))
                if ticket_id is None: 
                     st.warning(f"ID não encontrado para linha editada {row_index}.")
                     continue 

                if 'Contato' in changes:
                    current_contact_status = ticket_id in st.session_state.contacted_tickets
                    new_contact_status = changes['Contato']
                    if current_contact_status != new_contact_status:
                        if new_contact_status: st.session_state.contacted_tickets.add(ticket_id)
                        else: st.session_state.contacted_tickets.discard(ticket_id)
                        contact_changed = True
                if 'Observações' in changes:
                    current_observation = st.session_state.observations.get(ticket_id, '')
                    new_observation = str(changes['Observações']) if changes['Observações'] is not None else '' 
                    if current_observation != new_observation:
                        st.session_state.observations[ticket_id] = new_observation
                        observation_changed = True
            except IndexError:
                st.warning(f"Erro de índice ao processar linha {row_index}.")
                continue 
            except Exception as e:
                 st.warning(f"Erro inesperado ao processar linha {row_index}: {e}.")
                 continue 

        if contact_changed or observation_changed:
            now_str = datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M')
            if contact_changed:
                data_to_save = list(st.session_state.contacted_tickets)
                json_content = json.dumps(data_to_save, indent=4)
                commit_msg = f"Atualizando contatos em {now_str}"
                update_github_file(st.session_state.repo, "contacted_tickets.json", json_content.encode('utf-8'), commit_msg)
            if observation_changed:
                json_content = json.dumps(st.session_state.observations, indent=4, ensure_ascii=False)
                commit_msg = f"Atualizando observações em {now_str}"
                update_github_file(st.session_state.repo, "ticket_observations.json", json_content.encode('utf-8'), commit_msg)
        
        st.session_state.ticket_editor['edited_rows'] = {}

    except Exception as e: 
         st.error(f"Falha CRÍTICA ao salvar no GitHub: {e}")
         st.warning("Revertendo alterações locais.")
         st.session_state.contacted_tickets = original_contacts
         st.session_state.observations = original_observations
         st.session_state.ticket_editor['edited_rows'] = {} 

    st.session_state.scroll_to_details = True
    st.rerun() 


# ... (código carregar_dados_evolucao) ...
@st.cache_data(ttl=3600)
def carregar_dados_evolucao(_repo, dias_para_analisar=7):
    global grupos_excluidos
    if _repo is None: return pd.DataFrame() # Valida repo
    try:
        all_files_content = _repo.get_contents("snapshots")
        all_files = [f.path for f in all_files_content]
        df_evolucao_list = []
        end_date = date.today()
        start_date = end_date - timedelta(days=max(dias_para_analisar + 5, 10)) 

        processed_dates = []
        for file_name in all_files:
            if file_name.startswith("snapshots/backlog_") and file_name.endswith(".csv"):
                try:
                    date_str = file_name.replace("snapshots/backlog_", "").replace(".csv", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if start_date <= file_date <= end_date:
                        processed_dates.append((file_date, file_name))
                except ValueError: continue
                except Exception as e: 
                     st.warning(f"Erro nome snapshot {file_name}: {e}")
                     continue

        processed_dates.sort(key=lambda x: x[0])
        files_to_process = processed_dates[-dias_para_analisar:] 

        for file_date, file_name in files_to_process:
                try:
                    # Passa _repo explicitamente
                    df_snapshot = read_github_file(_repo, file_name) 
                    if df_snapshot.empty or 'Atribuir a um grupo' not in df_snapshot.columns:
                        continue
                    
                    df_snapshot_final = df_snapshot[~df_snapshot['Atribuir a um grupo'].isin(grupos_excluidos)]
                    df_snapshot_final = df_snapshot_final[~df_snapshot_final['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
                    
                    if df_snapshot_final.empty:
                         continue 

                    contagem_diaria = df_snapshot_final.groupby('Atribuir a um grupo').size().reset_index(name='Total Chamados')
                    contagem_diaria['Data'] = pd.to_datetime(file_date)
                    df_evolucao_list.append(contagem_diaria)
                except Exception as e:
                     st.warning(f"Erro processando snapshot {file_name}: {e}")
                     continue

        if not df_evolucao_list: 
             return pd.DataFrame()

        df_consolidado = pd.concat(df_evolucao_list, ignore_index=True)
        return df_consolidado.sort_values(by=['Data', 'Atribuir a um grupo'])

    except GithubException as e:
        if e.status == 404: 
             st.warning("Pasta 'snapshots' não encontrada.")
        else:
             st.warning(f"Erro GitHub ao carregar snapshots: {e.data.get('message', e)}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro inesperado em carregar_dados_evolucao: {e}")
        return pd.DataFrame()


# ... (código find_closest_snapshot_before) ...
@st.cache_data(ttl=300)
def find_closest_snapshot_before(_repo, current_report_date, target_date):
    if _repo is None: return None, None # Valida repo
    try:
        all_files_content = _repo.get_contents("snapshots")
        snapshots = []
        search_start_date = target_date - timedelta(days=10) 

        for file in all_files_content:
            match = re.search(r"backlog_(\d{4}-\d{2}-\d{2})\.csv", file.path)
            if match:
                try:
                    snapshot_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
                    if search_start_date <= snapshot_date <= target_date: 
                        snapshots.append((snapshot_date, file.path))
                except ValueError:
                    continue 

        if not snapshots:
            st.warning(f"Nenhum snapshot encontrado entre {search_start_date:%d/%m/%Y} e {target_date:%d/%m/%Y}.")
            return None, None

        snapshots.sort(key=lambda x: x[0], reverse=True) 
        return snapshots[0] 

    except GithubException as e:
         if e.status == 404:
              st.warning("Pasta 'snapshots' não encontrada para buscar data comparativa.")
         else:
              st.warning(f"Erro GitHub buscar snapshots: {e.data.get('message', e)}")
         return None, None
    except Exception as e:
        st.error(f"Erro inesperado em find_closest_snapshot_before: {e}")
        return None, None


# ... (código carregar_evolucao_aging) ...
@st.cache_data(ttl=3600)
def carregar_evolucao_aging(_repo, dias_para_analisar=90):
    global grupos_excluidos
    if _repo is None: return pd.DataFrame() # Valida repo
    try:
        all_files_content = _repo.get_contents("snapshots")
        all_files = [f.path for f in all_files_content]
        lista_historico = []
        end_date = date.today() - timedelta(days=1) 
        start_date = end_date - timedelta(days=max(dias_para_analisar + 10, 60)) 

        processed_files = []
        for file_name in all_files:
            if file_name.startswith("snapshots/backlog_") and file_name.endswith(".csv"):
                try:
                    date_str = file_name.replace("snapshots/backlog_", "").replace(".csv", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if start_date <= file_date <= end_date: 
                        processed_files.append((file_date, file_name))
                except Exception as e:
                    st.warning(f"Erro nome snapshot {file_name} para aging: {e}")
                    continue

        processed_files.sort(key=lambda x: x[0]) 

        for file_date, file_name in processed_files:
            try:
                # Passa _repo explicitamente
                df_snapshot = read_github_file(_repo, file_name) 
                if df_snapshot.empty or 'Atribuir a um grupo' not in df_snapshot.columns:
                    st.warning(f"Snapshot {file_name} para aging vazio ou sem coluna grupo. Pulando.")
                    continue

                df_filtrado = df_snapshot[~df_snapshot['Atribuir a um grupo'].isin(grupos_excluidos)]
                df_filtrado = df_filtrado[~df_filtrado['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]

                if df_filtrado.empty:
                    st.info(f"Nenhum chamado válido em {file_name} para aging após filtros.")
                    continue 

                # Usa analisar_aging (calcula idade relativa a HOJE)
                df_com_aging = analisar_aging(df_filtrado.copy())

                if df_com_aging.empty or 'Faixa de Antiguidade' not in df_com_aging.columns:
                     st.warning(f"analisar_aging retornou DF vazio/inválido para snapshot {file_name}.")
                     continue 

                contagem_faixas = df_com_aging['Faixa de Antiguidade'].value_counts().reset_index()
                contagem_faixas.columns = ['Faixa de Antiguidade', 'total']

                ordem_faixas_scaffold = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
                df_todas_faixas = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas_scaffold})

                contagem_completa = pd.merge(
                    df_todas_faixas, contagem_faixas,
                    on='Faixa de Antiguidade', how='left'
                ).fillna(0)

                contagem_completa['total'] = contagem_completa['total'].astype(int)
                contagem_completa['data'] = pd.to_datetime(file_date) # Data do snapshot

                lista_historico.append(contagem_completa)

            except Exception as e:
                 st.warning(f"Erro ao processar aging do snapshot {file_name}: {e}") 
                 continue 

        if not lista_historico:
            st.warning("Nenhum dado histórico de aging pôde ser carregado.")
            return pd.DataFrame()

        return pd.concat(lista_historico, ignore_index=True)

    except GithubException as e:
         if e.status == 404:
              st.warning("Pasta 'snapshots' não encontrada para carregar evolução aging.")
         else:
              st.warning(f"Erro GitHub carregar evolução aging: {e.data.get('message', e)}")
         return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro inesperado em carregar_evolucao_aging: {e}") 
        return pd.DataFrame()


# ... (código formatar_delta_card) ...
def formatar_delta_card(delta_abs, delta_perc, valor_comparacao, data_comparacao_str):
    delta_abs = int(delta_abs)
    if valor_comparacao > 0:
        delta_perc_str = f"({delta_perc * 100:+.1f}%)" 
        delta_text = f"{delta_abs:+} {delta_perc_str} vs. {data_comparacao_str}"
    elif valor_comparacao == 0 and delta_abs > 0:
        delta_text = f"+{delta_abs} (Novo) vs. {data_comparacao_str}" 
    elif valor_comparacao == 0 and delta_abs < 0: 
        delta_text = f"{delta_abs} vs. {data_comparacao_str}" 
    else: 
         delta_text = f"0 (=) vs. {data_comparacao_str}" 

    if delta_abs > 0: delta_class = "delta-positive"
    elif delta_abs < 0: delta_class = "delta-negative"
    else: delta_class = "delta-neutral"
    return delta_text, delta_class


# --- Código Principal Começa Aqui ---
# Display Logos
logo_copa_b64 = get_image_as_base64("logo_sidebar.png")
logo_belago_b64 = get_image_as_base64("logo_belago.png")
if logo_copa_b64 and logo_belago_b64:
    st.markdown(f"""<div style="display: flex; justify-content: space-between; align-items: center;"><img src="data:image/png;base64,{logo_copa_b64}" width="150"><h1 style='text-align: center; margin: 0;'>Backlog Copa Energia + Belago</h1><img src="data:image/png;base64,{logo_belago_b64}" width="150"></div>""", unsafe_allow_html=True)
else:
    st.warning("Arquivos de logo não encontrados.")
    st.markdown("<h1 style='text-align: center; margin: 0;'>Backlog Copa Energia + Belago</h1>", unsafe_allow_html=True)

# Inicializa conexão GitHub e armazena no state
try:
    if 'repo' not in st.session_state: # Conecta apenas na primeira vez
         st.session_state.repo = get_github_repo()
    # Verifica se a conexão foi bem sucedida (importante se get_github_repo falhou antes)
    if st.session_state.repo is None:
         st.error("Falha ao inicializar a conexão com o repositório GitHub.")
         st.stop()
    _repo = st.session_state.repo # Usa a variável local _repo para clareza
except Exception as e:
     st.error(f"Erro CRÍTICO durante a inicialização do repositório: {e}")
     st.stop()

# --- Sidebar do Admin ---
st.sidebar.header("Área do Administrador")
password = st.sidebar.text_input("Senha para atualizar dados:", type="password", key="admin_pass")
# Usa st.secrets com fallback para evitar erro se não definido
is_admin = password == st.secrets.get("ADMIN_PASSWORD", "") if password else False

if is_admin:
    # ... (Código da sidebar do admin, usando _repo nas chamadas) ...
    st.sidebar.success("Acesso de administrador liberado.")
    st.sidebar.subheader("Atualização Completa")
    uploaded_file_atual = st.sidebar.file_uploader("1. Backlog ATUAL", type=["csv", "xlsx"], key="uploader_atual")
    uploaded_file_15dias = st.sidebar.file_uploader("2. Backlog de 15 DIAS ATRÁS", type=["csv", "xlsx"], key="uploader_15dias")
    if st.sidebar.button("Salvar Novos Dados no Site"):
        if uploaded_file_atual and uploaded_file_15dias:
            with st.spinner("Processando e salvando..."):
                now_sao_paulo = datetime.now(ZoneInfo('America/Sao_Paulo'))
                commit_msg = f"Dados atualizados em {now_sao_paulo:%d/%m/%Y %H:%M}"
                content_atual = process_uploaded_file(uploaded_file_atual)
                content_15dias = process_uploaded_file(uploaded_file_15dias)
                if content_atual is not None and content_15dias is not None:
                    try:
                        update_github_file(_repo, "dados_atuais.csv", content_atual, commit_msg)
                        update_github_file(_repo, "dados_15_dias.csv", content_15dias, commit_msg)
                        today_str = now_sao_paulo.strftime('%Y-%m-%d')
                        snapshot_path = f"snapshots/backlog_{today_str}.csv"
                        update_github_file(_repo, snapshot_path, content_atual, f"Snapshot de {today_str}")
                        data_do_upload = now_sao_paulo.date()
                        data_arquivo_15dias = data_do_upload - timedelta(days=15)
                        hora_atualizacao = now_sao_paulo.strftime('%H:%M')
                        datas_referencia_content = (f"data_atual:{data_do_upload:%d/%m/%Y}\n"
                                                    f"data_15dias:{data_arquivo_15dias:%d/%m/%Y}\n"
                                                    f"hora_atualizacao:{hora_atualizacao}")
                        update_github_file(_repo, "datas_referencia.txt", datas_referencia_content.encode('utf-8'), commit_msg)
                        
                        st.cache_data.clear()
                        st.cache_resource.clear()
                        st.sidebar.success("Arquivos salvos! Recarregando...")
                        st.rerun()
                    except GithubException as ghe:
                         st.sidebar.error(f"Erro GitHub ({ghe.status}): {ghe.data.get('message', 'Erro')}")
                    except Exception as e:
                        st.sidebar.error(f"Erro atualização completa: {e}")
        else:
            st.sidebar.warning("Carregue os arquivos ATUAL e de 15 DIAS.")
            
    st.sidebar.markdown("---")
    st.sidebar.subheader("Atualização Rápida")
    uploaded_file_fechados = st.sidebar.file_uploader("Apenas Chamados FECHADOS no dia", type=["csv", "xlsx"], key="uploader_fechados")
    if st.sidebar.button("Salvar Apenas Chamados Fechados"):
        if uploaded_file_fechados:
            with st.spinner("Salvando fechados..."):
                now_sao_paulo = datetime.now(ZoneInfo('America/Sao_Paulo'))
                commit_msg = f"Atualizando fechados em {now_sao_paulo:%d/%m/%Y %H:%M}"
                content_fechados = process_uploaded_file(uploaded_file_fechados)
                if content_fechados is not None:
                    try:
                        update_github_file(_repo, "dados_fechados.csv", content_fechados, commit_msg)
                        datas_existentes = read_github_text_file(_repo, "datas_referencia.txt")
                        hora_atualizacao_nova = now_sao_paulo.strftime('%H:%M')
                        datas_referencia_content_novo = (f"data_atual:{datas_existentes.get('data_atual', 'N/A')}\n"
                                                       f"data_15dias:{datas_existentes.get('data_15dias', 'N/A')}\n"
                                                       f"hora_atualizacao:{hora_atualizacao_nova}")
                        update_github_file(_repo, "datas_referencia.txt", datas_referencia_content_novo.encode('utf-8'), commit_msg)
                        
                        st.cache_data.clear()
                        st.cache_resource.clear()
                        st.sidebar.success("Fechados salvos! Recarregando...")
                        st.rerun()
                    except GithubException as ghe:
                         st.sidebar.error(f"Erro GitHub ({ghe.status}): {ghe.data.get('message', 'Erro')}")
                    except Exception as e:
                        st.sidebar.error(f"Erro atualização rápida: {e}")
        else:
            st.sidebar.warning("Carregue o arquivo de fechados.")
elif password: # Apenas se a senha foi digitada E está errada
    st.sidebar.error("Senha incorreta.")


# --- Bloco Principal de Processamento de Dados ---
try:
    # Carrega estado inicial (contatos, observações) usando _repo
    if 'contacted_tickets' not in st.session_state:
        try:
            file_content_obj = _repo.get_contents("contacted_tickets.json")
            file_content_str = file_content_obj.decoded_content.decode("utf-8")
            st.session_state.contacted_tickets = set(json.loads(file_content_str)) if file_content_str.strip() else set()
        except GithubException as e:
            if e.status == 404: st.session_state.contacted_tickets = set()
            else: st.error(f"Erro GitHub ao carregar contatos ({e.status})"); st.session_state.contacted_tickets = set()
        except json.JSONDecodeError:
             st.warning("'contacted_tickets.json' inválido."); st.session_state.contacted_tickets = set()

    if 'observations' not in st.session_state:
        st.session_state.observations = read_github_json_dict(_repo, "ticket_observations.json")

    # Trata parâmetros da URL
    needs_scroll = "scroll" in st.query_params
    if "faixa" in st.query_params:
        faixa_from_url = st.query_params.get("faixa")
        ordem_faixas_validas = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
        if faixa_from_url in ordem_faixas_validas:
                st.session_state.faixa_selecionada = faixa_from_url
    if "scroll" in st.query_params or "faixa" in st.query_params:
        st.query_params.clear() 

    # --- Carrega Dados Base (usando _repo) ---
    df_atual = read_github_file(_repo, "dados_atuais.csv")
    df_15dias = read_github_file(_repo, "dados_15_dias.csv")
    df_fechados_raw = read_github_file(_repo, "dados_fechados.csv") 
    datas_referencia = read_github_text_file(_repo, "datas_referencia.txt")
    data_atual_str = datas_referencia.get('data_atual', 'N/A')
    data_15dias_str = datas_referencia.get('data_15dias', 'N/A')
    hora_atualizacao_str = datas_referencia.get('hora_atualizacao', '')
    
    if df_atual.empty:
        st.warning("Arquivo 'dados_atuais.csv' não encontrado ou vazio.")
        st.stop()

    # Aplica filtros de grupos ocultos
    if 'Atribuir a um grupo' in df_atual.columns:
        df_atual = df_atual[~df_atual['Atribuir a um grupo'].isin(grupos_excluidos)].copy()
    else:
        st.error("Coluna 'Atribuir a um grupo' não encontrada em dados_atuais.csv.")
        st.stop()

    if not df_15dias.empty and 'Atribuir a um grupo' in df_15dias.columns:
        df_15dias_filtrado_ocultos = df_15dias[~df_15dias['Atribuir a um grupo'].isin(grupos_excluidos)].copy()
    else:
        df_15dias_filtrado_ocultos = pd.DataFrame()

    # Padroniza coluna de ID atual
    id_col_atual = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_atual.columns), None)
    if id_col_atual:
        df_atual[id_col_atual] = df_atual[id_col_atual].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        if id_col_atual != 'ID do ticket': 
            df_atual.rename(columns={id_col_atual: 'ID do ticket'}, inplace=True)
        id_col_atual = 'ID do ticket' 
    else:
        st.error("Coluna de ID não encontrada em dados_atuais.csv.")
        st.stop() 

    # IDs Fechados
    closed_ticket_ids = np.array([]) 
    if not df_fechados_raw.empty:
        id_col_fechados = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_fechados_raw.columns), None)
        if id_col_fechados:
            ids_fechados_series = df_fechados_raw[id_col_fechados].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().dropna()
            closed_ticket_ids = ids_fechados_series.unique()
        else:
             st.warning("Arquivo 'dados_fechados.csv' sem coluna de ID.")

    # Filtra RH
    df_atual_filtrado_rh = df_atual[~df_atual['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
    if not df_15dias_filtrado_ocultos.empty:
        df_15dias_filtrado = df_15dias_filtrado_ocultos[~df_15dias_filtrado_ocultos['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
    else:
        df_15dias_filtrado = pd.DataFrame() 

    # Calcula Aging para dados atuais
    df_todos_com_aging = analisar_aging(df_atual_filtrado_rh.copy()) 
    if df_todos_com_aging.empty:
         st.error("Análise de aging falhou para dados atuais.")
         st.stop()

    # Separa abertos e fechados (usando id_col_atual padronizado)
    df_encerrados_filtrado = df_todos_com_aging[df_todos_com_aging[id_col_atual].isin(closed_ticket_ids)]
    df_aging = df_todos_com_aging[~df_todos_com_aging[id_col_atual].isin(closed_ticket_ids)]
    
    # --- Fim do Pré-processamento ---

    # Define as abas
    tab1, tab2, tab3, tab4 = st.tabs(["Dashboard Completo", "Report Visual", "Evolução Semanal", "Evolução Aging"])
    
    # --- Conteúdo das Tabs ---
    # (O código dentro de cada `with tabX:` permanece o mesmo das versões anteriores,
    #  mas agora eles usarão os dataframes `df_aging`, `df_encerrados_filtrado`, 
    #  `df_15dias_filtrado` que foram processados corretamente)

    with tab1:
        # ... (Código Tab 1 - Sem alterações lógicas, apenas usa os DFs corretos) ...
        info_messages = ["**Filtros Aplicados:**", 
                         f"- Grupos ocultos ({', '.join(grupos_excluidos)}) e grupos contendo 'RH' desconsiderados.", 
                         "- Contagem de dias desconsidera o dia da abertura."]
        if closed_ticket_ids.size > 0: 
            info_messages.append(f"- {len(df_encerrados_filtrado)} chamados fechados hoje deduzidos das contagens e movidos para tabela de encerrados.")
        st.info("\n".join(info_messages))
        
        st.subheader("Análise de Antiguidade do Backlog Atual")
        texto_hora = f" (atualizado às {hora_atualizacao_str})" if hora_atualizacao_str else ""
        st.markdown(f"<p style='font-size: 0.9em; color: #666;'><i>Ref: {data_atual_str}{texto_hora}</i></p>", unsafe_allow_html=True)
        
        if not df_aging.empty:
            total_chamados = len(df_aging)
            total_fechados = len(df_encerrados_filtrado)
            col_spacer1, col_total, col_fechados, col_spacer2 = st.columns([1, 1.5, 1.5, 1])
            with col_total: st.markdown(f'<div class="metric-box"><span class="label">Chamados Abertos</span><span class="value">{total_chamados}</span></div>', unsafe_allow_html=True)
            with col_fechados: st.markdown(f'<div class="metric-box"><span class="label">Fechados no Dia</span><span class="value">{total_fechados}</span></div>', unsafe_allow_html=True)

            st.markdown("---")
            # ... (código dos cards de faixa de antiguidade) ...
            aging_counts = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
            aging_counts.columns = ['Faixa de Antiguidade', 'Quantidade']
            ordem_faixas = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
            todas_as_faixas = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas})
            aging_counts = pd.merge(todas_as_faixas, aging_counts, on='Faixa de Antiguidade', how='left').fillna(0).astype({'Quantidade': int})
            aging_counts['Faixa de Antiguidade'] = pd.Categorical(aging_counts['Faixa de Antiguidade'], categories=ordem_faixas, ordered=True)
            aging_counts = aging_counts.sort_values('Faixa de Antiguidade')
            if 'faixa_selecionada' not in st.session_state or st.session_state.faixa_selecionada not in ordem_faixas:
                st.session_state.faixa_selecionada = "0-2 dias" 
            cols = st.columns(len(ordem_faixas))
            for i, row in aging_counts.iterrows():
                with cols[i]:
                    faixa_encoded = quote(row['Faixa de Antiguidade'])
                    card_html = f"""<a href="?faixa={faixa_encoded}&scroll=true" target="_self" class="metric-box"><span class="label">{row['Faixa de Antiguidade']}</span><span class="value">{row['Quantidade']}</span></a>"""
                    st.markdown(card_html, unsafe_allow_html=True)

        else: st.warning("Nenhum chamado aberto encontrado.")

        # Comparativo
        st.markdown(f"<h3>Comparativo: Atual vs. {data_15dias_str if not df_15dias_filtrado.empty else '15 Dias (Indisponível)'}</h3>", unsafe_allow_html=True)
        if not df_15dias_filtrado.empty:
            df_comparativo = processar_dados_comparativos(df_aging, df_15dias_filtrado) # Passa os DFs corretos
            if not df_comparativo.empty: 
                 # Renomeia ANTES de set_index
                 df_comparativo = df_comparativo.rename(columns={'Grupo': 'Grupo'}) 
                 st.dataframe(df_comparativo.set_index('Grupo').style.map(lambda val: 'background-color: #ffcccc' if val > 0 else ('background-color: #ccffcc' if val < 0 else ''), subset=['Diferença']), use_container_width=True)
            else: st.info("Nenhum dado comum para comparação.")
        else: st.warning("Dados de 15 dias atrás indisponíveis.")
        
        st.markdown("---")

        # Encerrados
        st.markdown(f"<h3>Chamados Encerrados ({data_atual_str})</h3>", unsafe_allow_html=True)
        if not closed_ticket_ids.size > 0: 
             st.info("Arquivo de encerrados não carregado.")
        elif not df_encerrados_filtrado.empty:
            colunas_fechados = ['ID do ticket', 'Descrição', 'Atribuir a um grupo', 'Dias em Aberto']
            colunas_existentes_fechados = [c for c in colunas_fechados if c in df_encerrados_filtrado.columns]
            st.data_editor(df_encerrados_filtrado[colunas_existentes_fechados], hide_index=True, disabled=True, use_container_width=True, key="editor_fechados")
        else: st.info("Nenhum chamado encerrado hoje nos grupos analisados.") 

        # Detalhar/Buscar Abertos
        if not df_aging.empty:
            st.markdown("---")
            st.subheader("Detalhar e Buscar Chamados Abertos", anchor="detalhar-e-buscar-chamados-abertos") 
            st.info('Marque "Contato" ou adicione "Observações". As alterações são salvas automaticamente.')

            # Scroll JS (código igual)
            if 'scroll_to_details' not in st.session_state: st.session_state.scroll_to_details = False
            if needs_scroll or st.session_state.get('scroll_to_details', False):
                js_code = """<script> setTimeout(() => { const element = window.parent.document.getElementById('detalhar-e-buscar-chamados-abertos'); if (element) { element.scrollIntoView({ behavior: 'smooth', block: 'start' }); } }, 250); </script>"""
                components.html(js_code, height=0)
                st.session_state.scroll_to_details = False 

            # Selectbox da Faixa (código igual)
            st.selectbox("Selecione faixa de idade:", options=ordem_faixas, key='faixa_selecionada') 
            faixa_atual = st.session_state.faixa_selecionada
            filtered_df = df_aging[df_aging['Faixa de Antiguidade'] == faixa_atual].copy()
            
            if not filtered_df.empty:
                # Highlight e adição de colunas (código igual)
                def highlight_row(row): return ['background-color: #fff8c4'] * len(row) if row.get('Contato', False) else [''] * len(row)
                filtered_df['Contato'] = filtered_df['ID do ticket'].apply(lambda id: str(id) in st.session_state.contacted_tickets)
                filtered_df['Observações'] = filtered_df['ID do ticket'].apply(lambda id: st.session_state.observations.get(str(id), ''))
                st.session_state.last_filtered_df = filtered_df.reset_index(drop=True) 

                # Definição de colunas (código igual)
                colunas_para_exibir_renomeadas = {
                    'Contato': 'Contato', 'ID do ticket': 'ID do ticket', 'Descrição': 'Descrição',
                    'Atribuir a um grupo': 'Grupo Atribuído', 'Dias em Aberto': 'Dias Aberto', # Abreviação
                    'Data de criação': 'Criação', 'Observações': 'Observações'
                }
                colunas_existentes = [c for c in colunas_para_exibir_renomeadas if c in filtered_df.columns]
                colunas_renomeadas_existentes = [colunas_para_exibir_renomeadas[c] for c in colunas_existentes]
                colunas_editaveis = ['Contato', 'Observações'] 
                colunas_desabilitadas = [colunas_para_exibir_renomeadas[c] for c in colunas_existentes if c not in colunas_editaveis]

                # Data Editor (código igual)
                st.data_editor(
                    st.session_state.last_filtered_df.rename(columns=colunas_para_exibir_renomeadas)[colunas_renomeadas_existentes].style.apply(highlight_row, axis=1),
                    use_container_width=True, hide_index=True, disabled=colunas_desabilitadas, 
                    key='ticket_editor', on_change=sync_ticket_data
                )
            else: st.info(f"Sem chamados abertos na faixa '{faixa_atual}'.")
            
            # Busca por Grupo (código igual)
            st.subheader("Buscar Chamados Abertos por Grupo")
            if 'Atribuir a um grupo' in df_aging.columns:
                 lista_grupos = sorted(df_aging['Atribuir a um grupo'].dropna().unique())
                 if lista_grupos:
                      grupo_selecionado = st.selectbox("Selecione grupo:", options=lista_grupos, key="busca_grupo")
                      if grupo_selecionado:
                           resultados_busca = df_aging[df_aging['Atribuir a um grupo'] == grupo_selecionado].copy()
                           date_col_name_busca = next((c for c in ['Data de criação', 'Data de Criacao'] if c in resultados_busca.columns), None)
                           if date_col_name_busca:
                                resultados_busca[date_col_name_busca] = pd.to_datetime(resultados_busca[date_col_name_busca]).dt.strftime('%d/%m/%Y')
                           st.write(f"{len(resultados_busca)} chamados abertos para '{grupo_selecionado}':")
                           colunas_para_exibir_busca = ['ID do ticket', 'Descrição', 'Dias em Aberto', date_col_name_busca]
                           colunas_existentes_busca = [c for c in colunas_para_exibir_busca if c in resultados_busca.columns and c is not None] 
                           st.data_editor(resultados_busca[colunas_existentes_busca], use_container_width=True, hide_index=True, disabled=True, key="editor_busca")
                 else: st.info("Nenhum grupo encontrado.")
            else: st.warning("Coluna 'Atribuir a um grupo' ausente.")

# --- Conteúdo da Tab 2 ---
    with tab2:
        st.subheader("Resumo do Backlog Atual")
        if not df_aging.empty:
            # ... (código dos cards de resumo - sem alterações) ...
            total_chamados = len(df_aging)
            _, col_total_tab2, _ = st.columns([2, 1.5, 2])
            with col_total_tab2: st.markdown( f"""<div class="metric-box"><span class="label">Total de Chamados</span><span class="value">{total_chamados}</span></div>""", unsafe_allow_html=True )
            st.markdown("---")
            aging_counts_tab2 = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
            aging_counts_tab2.columns = ['Faixa de Antiguidade', 'Quantidade']
            ordem_faixas = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
            todas_as_faixas_tab2 = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas})
            aging_counts_tab2 = pd.merge(todas_as_faixas_tab2, aging_counts_tab2, on='Faixa de Antiguidade', how='left').fillna(0).astype({'Quantidade': int})
            aging_counts_tab2['Faixa de Antiguidade'] = pd.Categorical(aging_counts_tab2['Faixa de Antiguidade'], categories=ordem_faixas, ordered=True)
            aging_counts_tab2 = aging_counts_tab2.sort_values('Faixa de Antiguidade')
            cols_tab2 = st.columns(len(ordem_faixas))
            for i, row in aging_counts_tab2.iterrows():
                with cols_tab2[i]: st.markdown( f"""<div class="metric-box"><span class="label">{row['Faixa de Antiguidade']}</span><span class="value">{row['Quantidade']}</span></div>""", unsafe_allow_html=True )
            st.markdown("---")
            
            st.subheader("Distribuição do Backlog por Grupo")
            orientation_choice = st.radio( "Orientação:", ["Vertical", "Horizontal"], index=0, horizontal=True, key="orient_tab2" )
            
            if 'Atribuir a um grupo' in df_aging.columns and 'Faixa de Antiguidade' in df_aging.columns:
                 chart_data = df_aging.groupby(['Atribuir a um grupo', 'Faixa de Antiguidade']).size().reset_index(name='Quantidade')
                 group_totals = chart_data.groupby('Atribuir a um grupo')['Quantidade'].sum().sort_values(ascending=False)
                 
                 if not group_totals.empty:
                      new_labels_map = {group: f"{group} ({total})" for group, total in group_totals.items()}
                      chart_data['Atribuir a um grupo'] = chart_data['Atribuir a um grupo'].map(new_labels_map)
                      sorted_new_labels = [new_labels_map[group] for group in group_totals.index]
                      
                      # Função lighten_color (sem alterações)
                      def lighten_color(hex_color, amount=0.2):
                          try:
                              hex_color = hex_color.lstrip('#')
                              h, l, s = colorsys.rgb_to_hls(*[int(hex_color[i:i+2], 16)/255.0 for i in (0, 2, 4)])
                              new_l = l + (1 - l) * amount; r, g, b = colorsys.hls_to_rgb(h, new_l, s)
                              return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
                          except Exception: return hex_color
                      base_color = "#375623"; palette = [lighten_color(base_color, v) for v in [0.85, 0.70, 0.55, 0.40, 0.20, 0]]; color_map = dict(zip(ordem_faixas, palette))
                      
                      # ==========================================================
                      # ||           CORREÇÃO DO TypeError AQUI                ||
                      # ==========================================================
                      plot_args = dict(
                          data_frame=chart_data, 
                          color='Faixa de Antiguidade', 
                          title="Composição da Idade do Backlog por Grupo",
                          # Define a ordem para AMBAS as categorias AQUI
                          category_orders={ 
                              'Faixa de Antiguidade': ordem_faixas,
                              'Atribuir a um grupo': sorted_new_labels 
                          }, 
                          color_discrete_map=color_map, 
                          text_auto=True
                      )
                      # ==========================================================

                      if orientation_choice == 'Horizontal':
                          dynamic_height = max(500, len(group_totals) * 30) 
                          # Remove category_orders daqui
                          fig = px.bar( **plot_args, x='Quantidade', y='Atribuir a um grupo', orientation='h', labels={'Quantidade': 'Qtd.', 'Atribuir a um grupo': ''}) 
                          fig.update_layout(height=dynamic_height, yaxis={'categoryorder':'array', 'categoryarray':sorted_new_labels[::-1]}) 
                      else: # Vertical
                          # Remove category_orders daqui
                          fig = px.bar( **plot_args, x='Atribuir a um grupo', y='Quantidade', labels={'Quantidade': 'Qtd.', 'Atribuir a um grupo': 'Grupo'}) 
                          fig.update_layout(height=600, xaxis_title=None, xaxis_tickangle=-45)
                      
                      fig.update_traces(textangle=0, textfont_size=12); fig.update_layout(legend_title_text='Antiguidade')
                      st.plotly_chart(fig, use_container_width=True)
                 else: st.info("Nenhum grupo encontrado.")
            else: st.warning("Colunas necessárias ausentes.")
        else: st.warning("Dados de aging indisponíveis.")

    # ... (Restante do código das tabs 3 e 4) ...


    # --- Tab 3 ---
    with tab3:
        # ... (Código Tab 3 - Usa _repo na chamada) ...
        st.subheader("Evolução do Backlog")
        dias_evolucao = st.slider("Ver evolução (dias):", 7, 30, 7, key="slider_evolucao")
        df_evolucao_tab3 = carregar_dados_evolucao(_repo, dias_para_analisar=dias_evolucao) # Passa _repo

        if not df_evolucao_tab3.empty:
            df_evolucao_tab3['Data'] = pd.to_datetime(df_evolucao_tab3['Data'])
            df_evolucao_semana = df_evolucao_tab3[df_evolucao_tab3['Data'].dt.dayofweek < 5].copy()

            if not df_evolucao_semana.empty:
                st.info("Considera apenas snapshots de dias úteis. Filtros de grupos ocultos e RH aplicados.")
                df_total_diario = df_evolucao_semana.groupby('Data')['Total Chamados'].sum().reset_index().sort_values('Data')
                df_total_diario['Data (Eixo)'] = df_total_diario['Data'].dt.strftime('%d/%m')
                ordem_datas_total = df_total_diario['Data (Eixo)'].tolist()
                fig_total = px.area(df_total_diario, x='Data (Eixo)', y='Total Chamados', title='Evolução Total (Dias Úteis)', markers=True, labels={"Data (Eixo)": "Data", "Total Chamados": "Total"}, category_orders={'Data (Eixo)': ordem_datas_total})
                fig_total.update_layout(height=400); st.plotly_chart(fig_total, use_container_width=True)
                st.markdown("---")
                st.info("Clique na legenda para filtrar grupos.")
                df_evolucao_semana_sorted = df_evolucao_semana.sort_values('Data')
                df_evolucao_semana_sorted['Data (Eixo)'] = df_evolucao_semana_sorted['Data'].dt.strftime('%d/%m')
                ordem_datas_grupo = df_evolucao_semana_sorted['Data (Eixo)'].unique().tolist()
                df_display = df_evolucao_semana_sorted.rename(columns={'Atribuir a um grupo': 'Grupo'})
                fig_grupo = px.line(df_display, x='Data (Eixo)', y='Total Chamados', color='Grupo', title='Evolução por Grupo (Dias Úteis)', markers=True, labels={ "Data (Eixo)": "Data", "Total Chamados": "Nº Chamados"}, category_orders={'Data (Eixo)': ordem_datas_grupo})
                fig_grupo.update_layout(height=600); st.plotly_chart(fig_grupo, use_container_width=True)
            else: st.info("Sem dados históricos suficientes em dias úteis.")
        else: st.info("Não foi possível carregar dados históricos.")


    # --- Tab 4 ---
    with tab4:
        # ... (Código Tab 4 - Usa _repo nas chamadas) ...
        st.subheader("Evolução do Aging do Backlog")
        st.info("Compara o aging de hoje com dias anteriores (idade calculada sempre em relação a hoje).")

        try:
            df_hist = carregar_evolucao_aging(_repo, dias_para_analisar=90) # Passa _repo

            ordem_faixas_scaffold = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
            hoje_data = None
            hoje_counts_df = pd.DataFrame() 

            if 'df_aging' in locals() and not df_aging.empty and data_atual_str != 'N/A':
                try:
                    hoje_data = pd.to_datetime(datetime.strptime(data_atual_str, "%d/%m/%Y").date())
                    hoje_counts_raw = df_aging['Faixa de Antiguidade'].value_counts().reset_index(name='total')
                    #hoje_counts_raw.columns = ['Faixa de Antiguidade', 'total'] # Redundante com name=
                    df_todas_faixas_hoje = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas_scaffold})
                    hoje_counts_df = pd.merge(df_todas_faixas_hoje, hoje_counts_raw, on='Faixa de Antiguidade', how='left').fillna(0)
                    hoje_counts_df['total'] = hoje_counts_df['total'].astype(int)
                    hoje_counts_df['data'] = hoje_data 
                except ValueError:
                    st.warning(f"Data atual inválida: '{data_atual_str}'.")
                    hoje_data = None 
            else: st.warning("Dados de 'hoje' (df_aging) indisponíveis.")

            # Combina histórico e hoje
            if not df_hist.empty and not hoje_counts_df.empty:
                 df_combinado = pd.concat([df_hist, hoje_counts_df], ignore_index=True).drop_duplicates(subset=['data', 'Faixa de Antiguidade'], keep='last') 
            elif not df_hist.empty: df_combinado = df_hist.copy(); st.warning("Dados de 'hoje' indisponíveis.")
            elif not hoje_counts_df.empty: df_combinado = hoje_counts_df.copy(); st.warning("Dados históricos indisponíveis.")
            else: st.error("Sem dados históricos ou de hoje para aging."); st.stop() 

            df_combinado['data'] = pd.to_datetime(df_combinado['data'])
            df_combinado = df_combinado.sort_values(by=['data', 'Faixa de Antiguidade'])

            # Comparativo Cards
            st.markdown("##### Comparativo")
            periodo_comp_opts = { "Ontem": 1, "7 dias atrás": 7, "15 dias atrás": 15, "30 dias atrás": 30 }
            periodo_comp_selecionado = st.radio("Comparar 'Hoje' com:", periodo_comp_opts.keys(), horizontal=True, key="radio_comp_periodo")
            data_comparacao_final, df_comparacao_dados, data_comparacao_str = None, pd.DataFrame(), "N/A"

            if hoje_data:
                target_comp_date = hoje_data.date() - timedelta(days=periodo_comp_opts[periodo_comp_selecionado])
                # Passa _repo
                data_comparacao_encontrada, _ = find_closest_snapshot_before(_repo, hoje_data.date(), target_comp_date) 
                if data_comparacao_encontrada:
                    data_comparacao_final = pd.to_datetime(data_comparacao_encontrada)
                    data_comparacao_str = data_comparacao_final.strftime('%d/%m')
                    df_comparacao_dados = df_combinado[df_combinado['data'] == data_comparacao_final].copy() 
                    if df_comparacao_dados.empty: data_comparacao_final = None # Invalida se sem dados processados
                # else: Aviso já é dado por find_closest_snapshot_before
            
            # Exibe Cards (código igual)
            cols_map = {i: col for i, col in enumerate(st.columns(3) + st.columns(3))}
            for i, faixa in enumerate(ordem_faixas_scaffold):
                with cols_map[i]:
                    valor_hoje, delta_text, delta_class = 'N/A', "N/A", "delta-neutral"
                    if not hoje_counts_df.empty:
                        valor_hoje_series = hoje_counts_df.loc[hoje_counts_df['Faixa de Antiguidade'] == faixa, 'total']
                        if not valor_hoje_series.empty:
                            valor_hoje = int(valor_hoje_series.iloc[0])
                            if data_comparacao_final and not df_comparacao_dados.empty:
                                valor_comp_series = df_comparacao_dados.loc[df_comparacao_dados['Faixa de Antiguidade'] == faixa, 'total']
                                valor_comparacao = int(valor_comp_series.iloc[0]) if not valor_comp_series.empty else 0
                                delta_abs = valor_hoje - valor_comparacao
                                delta_perc = (delta_abs / valor_comparacao) if valor_comparacao > 0 else 0
                                delta_text, delta_class = formatar_delta_card(delta_abs, delta_perc, valor_comparacao, data_comparacao_str)
                            elif hoje_data: delta_text = "Sem dados para comparar"
                        else: valor_hoje = 0; delta_text = "N/A"
                    elif not hoje_data: delta_text = "Dados de hoje indisponíveis"
                    st.markdown(f'<div class="metric-box"><span class="label">{faixa}</span><span class="value">{valor_hoje}</span><span class="delta {delta_class}">{delta_text}</span></div>', unsafe_allow_html=True)

            st.divider()

            # Gráfico Evolução 7 dias (código igual)
            st.markdown(f"##### Gráfico de Evolução (Últimos 7 dias)")
            hoje_filtro_grafico = datetime.now().date(); data_inicio_filtro_grafico = hoje_filtro_grafico - timedelta(days=6) 
            df_filtrado_grafico = df_combinado[df_combinado['data'].dt.date >= data_inicio_filtro_grafico].copy()

            if df_filtrado_grafico.empty: st.warning("Sem dados de aging para os últimos 7 dias.")
            else:
                df_grafico = df_filtrado_grafico.sort_values(by='data')
                df_grafico['Data (Eixo)'] = df_grafico['data'].dt.strftime('%d/%m')
                ordem_datas_grafico = df_grafico['Data (Eixo)'].unique().tolist() 
                def lighten_color(hex_color, amount=0.2):
                    try: h,l,s=colorsys.rgb_to_hls(*[int(hex_color.lstrip('#')[i:i+2],16)/255. for i in (0,2,4)]); r,g,b=colorsys.hls_to_rgb(h,l+(1-l)*amount,s); return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
                    except: return hex_color
                base="#375623"; palette=[lighten_color(base,v) for v in [0.85,0.7,0.55,0.4,0.2,0]]; color_map=dict(zip(ordem_faixas_scaffold,palette))
                tipo_grafico = st.radio("Tipo de gráfico:", ("Linha", "Área"), horizontal=True, key="radio_tipo_grafico_aging")
                plot_func = px.line if tipo_grafico == "Linha" else px.area
                title_suf = "(Comparativo)" if tipo_grafico == "Linha" else "(Composição)"
                fig = plot_func(df_grafico, x='Data (Eixo)', y='total', color='Faixa de Antiguidade', title=f'Evolução Aging {title_suf} - 7 dias', markers=True, labels={"Data (Eixo)": "Data", "total": "Chamados", "Faixa de Antiguidade": "Faixa"}, category_orders={'Data (Eixo)': ordem_datas_grafico, 'Faixa de Antiguidade': ordem_faixas_scaffold}, color_discrete_map=color_map)
                fig.update_layout(height=500, legend_title_text='Faixa'); st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"Erro na Tab Evolução Aging: {e}")
            st.exception(e) 

# --- Tratamento Final de Erros ---
except Exception as e:
    st.error(f"Erro GERAL: {e}") 
    import traceback
    st.exception(e) 
    # st.stop() # Descomente se quiser parar em caso de erro geral

# --- Rodapé ---
st.markdown("---")
st.markdown(""" 
<p style='text-align: center; color: #666; font-size: 0.9em; margin-bottom: 0;'>v0.9.35 | Em desenvolvimento.</p>
<p style='text-align: center; color: #666; font-size: 0.9em; margin-top: 0;'>Desenvolvido por Leonir Scatolin Junior</p>
""", unsafe_allow_html=True)
