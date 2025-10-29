# VERSÃO v0.9.30-740 (Corrigida - Cálculo Aging Histórico Relativo)

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
# from PIL import Image # Não usado
from urllib.parse import quote
import json
import colorsys
import re

# ==========================================================
# ||           FUNÇÃO MOVIDA PARA O TOPO                 ||
# ==========================================================
@st.cache_data
def get_image_as_base64(path):
    """Lê um arquivo de imagem e retorna como string base64."""
    try:
        # Usa caminhos relativos assumindo que as imagens estão na mesma pasta do script
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
    page_icon="minilogo.png", # Garanta que minilogo.png existe
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
.metric-box{border:1px solid #CCC;padding:10px;border-radius:5px;text-align:center;box-shadow:0 2px 4px rgba(0,0,0,.1);margin-bottom:10px;height:120px;display:flex;flex-direction:column;justify-content:center}
a.metric-box{display:block;color:inherit;text-decoration:none!important}
a.metric-box:hover{background-color:#f0f2f6;text-decoration:none!important}
.metric-box span{display:block;width:100%;text-decoration:none!important}
.metric-box .label{font-size:1em;color:#666;margin-bottom:5px}
.metric-box .value{font-size:2.5em;font-weight:700;color:#375623}
.metric-box .delta{font-size:.9em;margin-top:5px}
.delta-positive{color:#d9534f}
.delta-negative{color:#5cb85c}
.delta-neutral{color:#666}
</style>
""")

# --- Definições de Funções ---

@st.cache_resource(show_spinner="Conectando ao GitHub...")
def get_github_repo():
    """Conecta ao repositório GitHub usando segredos."""
    try:
        expected_repo_name = st.secrets.get("EXPECTED_REPO")
        if not expected_repo_name: raise ValueError("Segredo EXPECTED_REPO não configurado.")
        github_token = st.secrets.get("GITHUB_TOKEN")
        if not github_token: raise ValueError("Segredo GITHUB_TOKEN não configurado.")
        
        auth = Auth.Token(github_token)
        g = Github(auth=auth)
        
        try: _ = g.get_user().login # Valida token
        except GithubException as auth_err:
             if auth_err.status == 401: raise ConnectionError("Erro GitHub (401): Token inválido ou expirado.")
             raise # Re-levanta outros erros de autenticação
        
        repo = g.get_repo(expected_repo_name)
        # st.sidebar.caption(f"Conectado a: {repo.full_name}") # Removido para evitar chamar antes do sidebar
        return repo
        
    except ValueError as ve: # Erro nos segredos
         st.error(f"Configuração incompleta: {ve}")
         st.stop()
    except ConnectionError as ce: # Erro de autenticação
         st.error(str(ce))
         st.stop()
    except GithubException as e: # Outros erros GitHub
        msg = e.data.get('message', 'Erro desconhecido')
        if e.status == 404: st.error(f"Erro GitHub (404): Repositório '{expected_repo_name}' não encontrado ou token sem permissão.")
        else: st.error(f"Erro GitHub ({e.status}): {msg}")
        st.stop()
    except Exception as e: # Erros inesperados
        st.error(f"Erro inesperado ao conectar ao GitHub: {e}")
        st.stop()

# ...(Funções update_github_file, read_github_file, read_github_text_file, read_github_json_dict, process_uploaded_file permanecem iguais)...
def update_github_file(_repo, file_path, file_content, commit_message):
    """Cria ou atualiza um arquivo no GitHub, tratando conflitos."""
    if _repo is None:
         st.sidebar.error(f"Erro interno: Tentativa de salvar '{file_path}' sem repo.")
         return 

    try:
        contents = _repo.get_contents(file_path)
        sha = contents.sha
        file_content_bytes = file_content.encode('utf-8') if isinstance(file_content, str) else file_content

        if contents.decoded_content == file_content_bytes:
             if file_path not in ["contacted_tickets.json", "ticket_observations.json", "datas_referencia.txt"]:
                  # st.sidebar.info(f"'{file_path}' já atualizado.") # Reduzir verbosidade
                  pass
             return 

        _repo.update_file(contents.path, commit_message, file_content_bytes, sha)
        if file_path not in ["contacted_tickets.json", "ticket_observations.json", "datas_referencia.txt"]: 
            st.sidebar.info(f"'{file_path}' atualizado.")
            
    except GithubException as e:
        if e.status == 404: 
            file_content_bytes = file_content.encode('utf-8') if isinstance(file_content, str) else file_content
            _repo.create_file(file_path, commit_message, file_content_bytes)
            if file_path not in ["contacted_tickets.json", "ticket_observations.json", "datas_referencia.txt"]: 
                st.sidebar.info(f"'{file_path}' criado.")
        elif e.status == 409: 
             st.sidebar.error(f"Conflito ao salvar '{file_path}'. Recarregue e tente novamente.")
        else:
            msg = e.data.get('message', f'Status {e.status}')
            st.sidebar.error(f"Erro GitHub ao salvar '{file_path}': {msg}")
            raise # Re-levanta para possível tratamento superior

@st.cache_data(ttl=300) 
def read_github_file(_repo, file_path):
    """Lê um arquivo CSV do GitHub, tratando encoding e erros."""
    if _repo is None: return pd.DataFrame() # Retorna vazio se repo inválido

    try:
        content_file = _repo.get_contents(file_path)
        content_bytes = content_file.decoded_content

        try: content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try: 
                content = content_bytes.decode("latin-1")
                if "dados_fechados" in file_path: st.sidebar.warning(f"'{file_path}' lido como Latin-1.")
            except Exception as decode_err: raise ValueError(f"Decode Error: {decode_err}")

        if not content.strip(): return pd.DataFrame()

        try:
            dtype_map = {col: str for col in ['ID do ticket', 'ID do Ticket', 'ID'] }
            # Tenta ler com ; primeiro, depois , como fallback
            try:
                df = pd.read_csv(StringIO(content), delimiter=';', dtype=dtype_map, low_memory=False, on_bad_lines='warn') 
            except pd.errors.ParserError:
                 st.warning(f"Falha ao ler '{file_path}' com ';'. Tentando com ','.")
                 content_io = StringIO(content) # Reinicia o buffer
                 df = pd.read_csv(content_io, delimiter=',', dtype=dtype_map, low_memory=False, on_bad_lines='warn')
                 
        except Exception as read_err: raise ValueError(f"Read Error: {read_err}")

        df.columns = df.columns.str.strip() 
        df.dropna(how='all', inplace=True) 
        return df

    except GithubException as e:
        if e.status != 404: st.error(f"Erro GitHub ({e.status}) ao ler '{file_path}': {e.data.get('message', 'Erro')}")
        return pd.DataFrame() # Retorna vazio se 404 ou outro erro
    except ValueError as ve: # Captura erros de decode ou read
         st.error(f"Erro ao processar '{file_path}': {ve}")
         return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro inesperado ao ler '{file_path}': {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def read_github_text_file(_repo, file_path):
    # ... (código inalterado) ...
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
        if e.status != 404: st.warning(f"Erro GitHub ao ler {file_path}: {e.data.get('message', e)}")
        return {}
    except Exception as e:
        st.warning(f"Erro inesperado ao ler {file_path}: {e}")
        return {}

@st.cache_data(ttl=300)
def read_github_json_dict(_repo, file_path):
    # ... (código inalterado) ...
    if _repo is None: return {}
    try:
        file_content_obj = _repo.get_contents(file_path)
        file_content_str = file_content_obj.decoded_content.decode("utf-8")
        return json.loads(file_content_str) if file_content_str.strip() else {} 
    except GithubException as e:
        if e.status != 404: st.error(f"Erro GitHub JSON '{file_path}': {e.data.get('message', e)}")
        return {}
    except json.JSONDecodeError:
        st.warning(f"JSON '{file_path}' vazio ou inválido.")
        return {}
    except Exception as e:
        st.error(f"Erro inesperado JSON '{file_path}': {e}")
        return {}

def process_uploaded_file(uploaded_file):
    # ... (código inalterado) ...
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
    # ... (código inalterado) ...
    if df_atual is None or df_atual.empty or 'Atribuir a um grupo' not in df_atual.columns:
         st.warning("Dados atuais inválidos para comparação.")
         return pd.DataFrame(columns=['Grupo', '15 Dias Atrás', 'Atual', 'Diferença', 'Status'])

    contagem_atual = df_atual.groupby('Atribuir a um grupo').size().reset_index(name='Atual')

    if df_15dias is None or df_15dias.empty or 'Atribuir a um grupo' not in df_15dias.columns:
         st.warning("Dados de 15 dias atrás inválidos para comparação.")
         df_comparativo = contagem_atual.copy()
         df_comparativo['15 Dias Atrás'] = 0
         df_comparativo['Diferença'] = df_comparativo['Atual']
    else:
         contagem_15dias = df_15dias.groupby('Atribuir a um grupo').size().reset_index(name='15 Dias Atrás')
         df_comparativo = pd.merge(contagem_atual, contagem_15dias, on='Atribuir a um grupo', how='outer').fillna(0)
         df_comparativo['Diferença'] = df_comparativo['Atual'] - df_comparativo['15 Dias Atrás']
    
    df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']] = df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']].astype(int)
    df_comparativo['Status'] = df_comparativo.apply(get_status, axis=1)
    df_comparativo.rename(columns={'Atribuir a um grupo': 'Grupo'}, inplace=True)
    
    return df_comparativo[['Grupo', '15 Dias Atrás', 'Atual', 'Diferença', 'Status']]


@st.cache_data
def categorizar_idade_vetorizado(dias_series):
    # ... (código inalterado) ...
    condicoes = [
        dias_series >= 30, (dias_series >= 21) & (dias_series <= 29),
        (dias_series >= 11) & (dias_series <= 20), (dias_series >= 6) & (dias_series <= 10),
        (dias_series >= 3) & (dias_series <= 5), (dias_series >= 0) & (dias_series <= 2)
    ]
    opcoes = ["30+ dias", "21-29 dias", "11-20 dias", "6-10 dias", "3-5 dias", "0-2 dias"]
    return np.select(condicoes, opcoes, default="Inválido") 

@st.cache_data
def analisar_aging(_df_atual):
    # ... (código inalterado) ...
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
         
    if 'Dias em Aberto' not in df.columns: df['Dias em Aberto'] = -1 
    if 'Faixa de Antiguidade' not in df.columns: df['Faixa de Antiguidade'] = 'Erro'

    # Retorna APENAS as colunas que existiam + as duas novas
    cols_to_return = [col for col in _df_atual.columns if col in df.columns] + ['Dias em Aberto', 'Faixa de Antiguidade']
    return df[cols_to_return]


def get_status(row):
    # ... (código inalterado) ...
    diferenca = row.get('Diferença', 0) 
    if diferenca > 0: return "Alta Demanda"
    elif diferenca == 0: return "Estável / Atenção"
    else: return "Redução de Backlog"

# ... (código sync_ticket_data inalterado) ...
def sync_ticket_data():
    if 'ticket_editor' not in st.session_state or not st.session_state.ticket_editor.get('edited_rows'):
        return
    edited_rows = st.session_state.ticket_editor['edited_rows']
    contact_changed, observation_changed = False, False
    original_contacts = st.session_state.contacted_tickets.copy()
    original_observations = st.session_state.observations.copy()

    try:
        for row_index, changes in edited_rows.items():
            try:
                ticket_id = str(st.session_state.last_filtered_df.iloc[row_index].get('ID do ticket', None))
                if ticket_id is None: continue 
                if 'Contato' in changes:
                    current = ticket_id in st.session_state.contacted_tickets; new = changes['Contato']
                    if current != new: (st.session_state.contacted_tickets.add(ticket_id) if new else st.session_state.contacted_tickets.discard(ticket_id)); contact_changed = True
                if 'Observações' in changes:
                    current = st.session_state.observations.get(ticket_id, ''); new = str(changes['Observações'] or '')
                    if current != new: st.session_state.observations[ticket_id] = new; observation_changed = True
            except IndexError: st.warning(f"Erro índice linha {row_index}."); continue 
            except Exception as e: st.warning(f"Erro processando linha {row_index}: {e}."); continue 

        if contact_changed or observation_changed:
            now_str = datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M')
            repo_to_use = st.session_state.get('repo') # Pega da sessão
            if repo_to_use is None: raise ConnectionError("Repositório não inicializado para salvar.")

            if contact_changed:
                data = list(st.session_state.contacted_tickets); content = json.dumps(data, indent=4).encode('utf-8')
                update_github_file(repo_to_use, "contacted_tickets.json", content, f"Atualizando contatos em {now_str}")
            if observation_changed:
                content = json.dumps(st.session_state.observations, indent=4, ensure_ascii=False).encode('utf-8')
                update_github_file(repo_to_use, "ticket_observations.json", content, f"Atualizando observações em {now_str}")
        
        st.session_state.ticket_editor['edited_rows'] = {} # Limpa se sucesso

    except ConnectionError as ce: # Erro específico de repo não encontrado
         st.error(str(ce))
         # Não reverte, pois o erro foi ANTES de tentar salvar
    except Exception as e: 
         st.error(f"Falha CRÍTICA ao salvar: {e}")
         st.warning("Revertendo alterações locais.")
         st.session_state.contacted_tickets = original_contacts
         st.session_state.observations = original_observations
         st.session_state.ticket_editor['edited_rows'] = {} # Limpa mesmo no erro

    st.session_state.scroll_to_details = True
    st.rerun() 


# ... (código carregar_dados_evolucao inalterado) ...
@st.cache_data(ttl=3600)
def carregar_dados_evolucao(_repo, dias_para_analisar=7):
    global grupos_excluidos
    if _repo is None: return pd.DataFrame() 
    try:
        # ... (listagem de snapshots) ...
        all_files_content = _repo.get_contents("snapshots")
        all_files = [f.path for f in all_files_content]
        df_evolucao_list = []
        end_date = date.today(); start_date = end_date - timedelta(days=max(dias_para_analisar + 5, 10)) 
        processed_dates = []
        for file_name in all_files:
            if file_name.startswith("snapshots/backlog_") and file_name.endswith(".csv"):
                try:
                    date_str = file_name.split('_')[-1].split('.')[0]
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if start_date <= file_date <= end_date: processed_dates.append((file_date, file_name))
                except (ValueError, IndexError): continue 
                except Exception as e: st.warning(f"Erro nome {file_name}: {e}"); continue
        processed_dates.sort(key=lambda x: x[0]); files_to_process = processed_dates[-dias_para_analisar:] 

        for file_date, file_name in files_to_process:
                try:
                    df_snapshot = read_github_file(_repo, file_name) 
                    if df_snapshot.empty or 'Atribuir a um grupo' not in df_snapshot.columns: continue
                    df_final = df_snapshot[~df_snapshot['Atribuir a um grupo'].isin(grupos_excluidos)]
                    df_final = df_final[~df_final['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
                    if df_final.empty: continue 
                    contagem = df_final.groupby('Atribuir a um grupo').size().reset_index(name='Total Chamados')
                    contagem['Data'] = pd.to_datetime(file_date)
                    df_evolucao_list.append(contagem)
                except Exception as e: st.warning(f"Erro snapshot {file_name}: {e}"); continue

        if not df_evolucao_list: return pd.DataFrame()
        return pd.concat(df_evolucao_list, ignore_index=True).sort_values(by=['Data', 'Atribuir a um grupo'])
    except GithubException as e:
        if e.status != 404: st.warning(f"Erro GitHub snapshots: {e.data.get('message', e)}")
        return pd.DataFrame()
    except Exception as e: st.error(f"Erro carregar_dados_evolucao: {e}"); return pd.DataFrame()

# ... (código find_closest_snapshot_before inalterado) ...
@st.cache_data(ttl=300)
def find_closest_snapshot_before(_repo, current_report_date, target_date):
    if _repo is None: return None, None 
    try:
        all_files_content = _repo.get_contents("snapshots")
        snapshots = []
        search_start_date = target_date - timedelta(days=10) 
        for file in all_files_content:
            match = re.search(r"backlog_(\d{4}-\d{2}-\d{2})\.csv", file.path)
            if match:
                try:
                    snapshot_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
                    if search_start_date <= snapshot_date <= target_date: snapshots.append((snapshot_date, file.path))
                except ValueError: continue 
        if not snapshots:
            st.warning(f"Nenhum snapshot entre {search_start_date:%d/%m/%Y} e {target_date:%d/%m/%Y}.")
            return None, None
        snapshots.sort(key=lambda x: x[0], reverse=True) 
        return snapshots[0] 
    except GithubException as e:
         if e.status != 404: st.warning(f"Erro GitHub buscar snapshots: {e.data.get('message', e)}")
         return None, None
    except Exception as e: st.error(f"Erro find_closest_snapshot_before: {e}"); return None, None


# ==========================================================
# ||           FUNÇÃO carregar_evolucao_aging CORRIGIDA   ||
# ==========================================================
@st.cache_data(ttl=3600, show_spinner="Carregando histórico de aging...") # Adiciona spinner
def carregar_evolucao_aging(_repo, dias_para_analisar=90):
    """Carrega snapshots, filtra, calcula aging RELATIVO AO DIA DO SNAPSHOT."""
    global grupos_excluidos
    if _repo is None: return pd.DataFrame() 

    try:
        all_files_content = _repo.get_contents("snapshots")
        all_files = [f.path for f in all_files_content]
        lista_historico = []
        # Processa snapshots ATÉ ONTEM
        end_date = date.today() - timedelta(days=1) 
        start_date = end_date - timedelta(days=max(dias_para_analisar + 10, 60)) 

        processed_files = []
        for file_name in all_files:
            if file_name.startswith("snapshots/backlog_") and file_name.endswith(".csv"):
                try:
                    # Extrai data do nome do arquivo
                    date_str = file_name.split('_')[-1].split('.')[0] 
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if start_date <= file_date <= end_date: 
                        processed_files.append((file_date, file_name))
                except (ValueError, IndexError): # Ignora nomes mal formatados
                    st.warning(f"Ignorando snapshot com nome inválido: {file_name}")
                    continue
                except Exception as e: # Outros erros inesperados
                    st.warning(f"Erro ao processar nome do snapshot {file_name}: {e}")
                    continue
        
        # Ordena por data (mais antigo primeiro) para processamento
        processed_files.sort(key=lambda x: x[0]) 

        # Itera sobre os arquivos selecionados
        for file_date, file_name in processed_files:
            try:
                # Lê o snapshot (já tratado por read_github_file)
                df_snapshot = read_github_file(_repo, file_name) 
                
                # Pula se vazio ou sem coluna essencial
                if df_snapshot.empty or 'Atribuir a um grupo' not in df_snapshot.columns:
                    st.info(f"Snapshot {file_name} vazio ou sem coluna 'Atribuir a um grupo'. Pulando.")
                    continue

                # Aplica filtros de grupo (ocultos e RH)
                df_filtrado = df_snapshot[~df_snapshot['Atribuir a um grupo'].isin(grupos_excluidos)]
                df_filtrado = df_filtrado[~df_filtrado['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]

                # Pula se não sobrou nada após filtros
                if df_filtrado.empty:
                    st.info(f"Nenhum chamado válido em {file_name} para aging após filtros.")
                    continue 

                # --- CALCULA AGING RELATIVO À DATA DO SNAPSHOT ---
                df_calc_aging = df_filtrado.copy()
                date_col_name_hist = next((col for col in ['Data de criação', 'Data de Criacao'] if col in df_calc_aging.columns), None)

                if not date_col_name_hist:
                    st.warning(f"Coluna de data não encontrada no snapshot {file_name}. Pulando cálculo de aging.")
                    continue 

                # Converte data de criação para datetime, tratando erros
                df_calc_aging[date_col_name_hist] = pd.to_datetime(df_calc_aging[date_col_name_hist], errors='coerce')
                
                # Remove linhas onde a data de criação é inválida
                df_calc_aging = df_calc_aging.dropna(subset=[date_col_name_hist])
                if df_calc_aging.empty:
                     st.warning(f"Nenhum chamado com data válida no snapshot {file_name} após limpeza.")
                     continue

                # Define a data de referência como a data do snapshot
                snapshot_date_dt = pd.to_datetime(file_date) 
                data_criacao_normalizada_hist = df_calc_aging[date_col_name_hist].dt.normalize()
                
                # Calcula dias entre snapshot e criação
                dias_calculados_hist = (snapshot_date_dt - data_criacao_normalizada_hist).dt.days
                
                # Aplica regra de negócio (-1 dia, mínimo 0)
                df_calc_aging['Dias em Aberto'] = (dias_calculados_hist - 1).clip(lower=0) 
                
                # Categoriza usando a idade calculada relativa ao snapshot
                df_calc_aging['Faixa de Antiguidade'] = categorizar_idade_vetorizado(df_calc_aging['Dias em Aberto'])
                
                # Verifica se alguma categoria ficou 'Inválido'
                invalid_hist = df_calc_aging[df_calc_aging['Faixa de Antiguidade'] == 'Inválido']
                if not invalid_hist.empty:
                     st.warning(f"{len(invalid_hist)} chamados com idade inválida (cat: Inválido) no snapshot {file_name}.")
                
                # Usa o dataframe com o aging recém calculado
                df_com_aging = df_calc_aging 
                # --- FIM DO CÁLCULO RELATIVO ---

                # Pula se o cálculo de aging falhou ou resultou em DF vazio
                if df_com_aging.empty or 'Faixa de Antiguidade' not in df_com_aging.columns:
                     st.warning(f"Cálculo de aging relativo falhou para snapshot {file_name}.")
                     continue 
                
                # Conta as faixas para este snapshot
                contagem_faixas = df_com_aging['Faixa de Antiguidade'].value_counts().reset_index(name='total')
                #contagem_faixas.columns = ['Faixa de Antiguidade', 'total'] # Redundante com name='total'

                ordem_faixas_scaffold = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
                df_todas_faixas = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas_scaffold})

                # Garante que todas as faixas estão presentes (com contagem 0 se necessário)
                contagem_completa = pd.merge(df_todas_faixas, contagem_faixas, on='Faixa de Antiguidade', how='left').fillna(0)

                contagem_completa['total'] = contagem_completa['total'].astype(int)
                contagem_completa['data'] = pd.to_datetime(file_date) # Associa à data do snapshot

                lista_historico.append(contagem_completa)

            except Exception as e:
                 # Captura erro específico do processamento deste snapshot
                 st.warning(f"Erro ao processar aging do snapshot {file_name}: {e}") 
                 continue # Pula para o próximo snapshot

        # Após o loop, verifica se algum dado foi coletado
        if not lista_historico:
            st.warning("Nenhum dado histórico de aging pôde ser carregado após processar snapshots.")
            return pd.DataFrame()

        # Concatena todos os dataframes diários em um só
        return pd.concat(lista_historico, ignore_index=True)

    except GithubException as e: # Erros de acesso ao GitHub
         if e.status == 404: st.warning("Pasta 'snapshots' não encontrada.")
         else: st.warning(f"Erro GitHub carregar evolução aging: {e.data.get('message', e)}")
         return pd.DataFrame()
    except Exception as e: # Outros erros inesperados
        st.error(f"Erro inesperado em carregar_evolucao_aging: {e}") 
        return pd.DataFrame()
# ==========================================================

# ... (código formatar_delta_card inalterado) ...
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

# --- Código Principal (Início) ---
# Display Logos
logo_copa_b64 = get_image_as_base64("logo_sidebar.png")
logo_belago_b64 = get_image_as_base64("logo_belago.png")
if logo_copa_b64 and logo_belago_b64:
    st.markdown(f"""<div style="display: flex; justify-content: space-between; align-items: center;"><img src="data:image/png;base64,{logo_copa_b64}" width="150"><h1 style='text-align: center; margin: 0;'>Backlog Copa Energia + Belago</h1><img src="data:image/png;base64,{logo_belago_b64}" width="150"></div>""", unsafe_allow_html=True)
else:
    # st.warning("Arquivos de logo não encontrados.") # Já avisado na função
    st.markdown("<h1 style='text-align: center; margin: 0;'>Backlog Copa Energia + Belago</h1>", unsafe_allow_html=True)

# Inicializa conexão GitHub
try:
    # Conecta apenas uma vez por sessão
    if 'repo' not in st.session_state: 
         st.session_state.repo = get_github_repo()
         
    # Verifica se a conexão foi bem sucedida na primeira vez ou se falhou antes
    if st.session_state.repo is None:
         # get_github_repo já deve ter chamado st.error e st.stop()
         # Apenas uma segurança extra
         st.error("Falha ao inicializar conexão GitHub.") 
         st.stop()
         
    _repo = st.session_state.repo # Usa variável local para clareza
except Exception as e:
     # Captura erros que possam ocorrer *antes* do get_github_repo ser chamado (improvável)
     st.error(f"Erro CRÍTICO na inicialização: {e}")
     st.stop()

# --- Sidebar do Admin ---
# ... (código da sidebar permanece o mesmo, usando _repo) ...
st.sidebar.header("Área do Administrador")
password = st.sidebar.text_input("Senha:", type="password", key="admin_pass")
admin_pass_secret = st.secrets.get("ADMIN_PASSWORD", "") # Pega a senha dos segredos
# Verifica se a senha foi digitada E se corresponde ao segredo
is_admin = bool(password and password == admin_pass_secret) if admin_pass_secret else False
if password and not is_admin and admin_pass_secret: # Avisa apenas se digitou errado E a senha existe nos segredos
     st.sidebar.error("Senha incorreta.")
elif not admin_pass_secret:
     st.sidebar.warning("Senha de admin não configurada nos segredos.")

if is_admin:
    st.sidebar.success("Acesso Admin OK.")
    st.sidebar.subheader("Atualização Completa")
    uploaded_file_atual = st.sidebar.file_uploader("1. Backlog ATUAL", type=["csv", "xlsx"], key="uploader_atual")
    uploaded_file_15dias = st.sidebar.file_uploader("2. Backlog 15 DIAS ATRÁS", type=["csv", "xlsx"], key="uploader_15dias")
    if st.sidebar.button("Salvar Novos Dados (Completo)"): # Texto mais claro
        if uploaded_file_atual and uploaded_file_15dias:
            with st.spinner("Processando e salvando..."):
                now = datetime.now(ZoneInfo('America/Sao_Paulo'))
                commit_msg = f"Dados atualizados em {now:%d/%m/%Y %H:%M}"
                content_atual = process_uploaded_file(uploaded_file_atual)
                content_15dias = process_uploaded_file(uploaded_file_15dias)
                if content_atual and content_15dias:
                    try:
                        update_github_file(_repo, "dados_atuais.csv", content_atual, commit_msg)
                        update_github_file(_repo, "dados_15_dias.csv", content_15dias, commit_msg)
                        snap_path = f"snapshots/backlog_{now:%Y-%m-%d}.csv"
                        update_github_file(_repo, snap_path, content_atual, f"Snapshot de {now:%Y-%m-%d}")
                        dref_content = (f"data_atual:{now.date():%d/%m/%Y}\n"
                                        f"data_15dias:{(now.date() - timedelta(days=15)):%d/%m/%Y}\n"
                                        f"hora_atualizacao:{now:%H:%M}")
                        update_github_file(_repo, "datas_referencia.txt", dref_content.encode('utf-8'), commit_msg)
                        st.cache_data.clear(); st.cache_resource.clear()
                        st.sidebar.success("Salvo! Recarregando...")
                        st.rerun()
                    except Exception as e: st.sidebar.error(f"Erro ao salvar: {e}")
                else: st.sidebar.error("Falha ao processar um dos arquivos.")
        else: st.sidebar.warning("Carregue AMBOS os arquivos.")
            
    st.sidebar.markdown("---")
    st.sidebar.subheader("Atualização Rápida (Fechados)")
    uploaded_file_fechados = st.sidebar.file_uploader("Apenas Chamados FECHADOS no dia", type=["csv", "xlsx"], key="uploader_fechados")
    if st.sidebar.button("Salvar Apenas Fechados"):
        if uploaded_file_fechados:
            with st.spinner("Salvando fechados..."):
                now = datetime.now(ZoneInfo('America/Sao_Paulo'))
                commit_msg = f"Atualizando fechados em {now:%d/%m/%Y %H:%M}"
                content_fechados = process_uploaded_file(uploaded_file_fechados)
                if content_fechados:
                    try:
                        update_github_file(_repo, "dados_fechados.csv", content_fechados, commit_msg)
                        d_exist = read_github_text_file(_repo, "datas_referencia.txt")
                        dref_content_novo = (f"data_atual:{d_exist.get('data_atual', 'N/A')}\n"
                                               f"data_15dias:{d_exist.get('data_15dias', 'N/A')}\n"
                                               f"hora_atualizacao:{now:%H:%M}") # Atualiza só a hora
                        update_github_file(_repo, "datas_referencia.txt", dref_content_novo.encode('utf-8'), commit_msg)
                        st.cache_data.clear(); st.cache_resource.clear()
                        st.sidebar.success("Fechados salvos! Recarregando...")
                        st.rerun()
                    except Exception as e: st.sidebar.error(f"Erro ao salvar fechados: {e}")
                else: st.sidebar.error("Falha ao processar arquivo de fechados.")
        else: st.sidebar.warning("Carregue o arquivo de fechados.")

# --- Bloco Principal de Processamento de Dados ---
try:
    # Carrega estado (contatos, observações)
    if 'contacted_tickets' not in st.session_state:
        try:
            # Tenta ler e decodificar
            c_file = _repo.get_contents("contacted_tickets.json")
            c_str = c_file.decoded_content.decode("utf-8")
            st.session_state.contacted_tickets = set(json.loads(c_str)) if c_str.strip() else set()
        except GithubException as e:
             # Silencioso se 404, erro se outro status
             if e.status != 404: st.error(f"Erro GitHub contatos({e.status})")
             st.session_state.contacted_tickets = set() # Garante que existe
        except json.JSONDecodeError: st.warning("'contacted_tickets.json' inválido."); st.session_state.contacted_tickets = set()
        except Exception as e: st.error(f"Erro lendo contatos: {e}"); st.session_state.contacted_tickets = set()

    if 'observations' not in st.session_state:
        st.session_state.observations = read_github_json_dict(_repo, "ticket_observations.json")

    # Trata URL params
    needs_scroll = "scroll" in st.query_params
    ordem_faixas_validas = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
    if "faixa" in st.query_params:
        faixa_from_url = st.query_params.get("faixa")
        if faixa_from_url in ordem_faixas_validas: st.session_state.faixa_selecionada = faixa_from_url
    if "scroll" in st.query_params or "faixa" in st.query_params: st.query_params.clear() 

    # --- Carrega Dados Base ---
    df_atual = read_github_file(_repo, "dados_atuais.csv")
    df_15dias = read_github_file(_repo, "dados_15_dias.csv")
    df_fechados_raw = read_github_file(_repo, "dados_fechados.csv") 
    datas_ref = read_github_text_file(_repo, "datas_referencia.txt")
    data_atual_str = datas_ref.get('data_atual', 'N/A')
    data_15dias_str = datas_ref.get('data_15dias', 'N/A')
    hora_atual_str = datas_ref.get('hora_atualizacao', '')
    
    if df_atual.empty: st.warning("Dados atuais ('dados_atuais.csv') não encontrados ou vazios."); st.stop()

    # Aplica filtros e padroniza IDs
    id_col_atual = next((c for c in ['ID do ticket', 'ID do Ticket', 'ID'] if c in df_atual.columns), None)
    if not id_col_atual: st.error("Coluna de ID não encontrada nos dados atuais."); st.stop()
    df_atual[id_col_atual] = df_atual[id_col_atual].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    if id_col_atual != 'ID do ticket': df_atual.rename(columns={id_col_atual: 'ID do ticket'}, inplace=True); id_col_atual = 'ID do ticket'
    
    df_atual = df_atual[~df_atual['Atribuir a um grupo'].isin(grupos_excluidos, na=False)].copy() # na=False importante
    df_atual = df_atual[~df_atual['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]

    if df_atual.empty: st.warning("Nenhum chamado restante após filtros iniciais (ocultos, RH)."); st.stop()

    # Processa df_15dias (para comparação)
    df_15dias_filtrado = pd.DataFrame() # Inicializa vazio
    if not df_15dias.empty and 'Atribuir a um grupo' in df_15dias.columns:
        df_15dias_f = df_15dias[~df_15dias['Atribuir a um grupo'].isin(grupos_excluidos, na=False)].copy()
        df_15dias_filtrado = df_15dias_f[~df_15dias_f['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
    elif not df_15dias.empty:
         st.warning("Dados de 15 dias carregados, mas sem coluna 'Atribuir a um grupo'.")


    # Processa Fechados
    closed_ticket_ids = np.array([]) 
    if not df_fechados_raw.empty:
        id_col_fechados = next((c for c in ['ID do ticket', 'ID do Ticket', 'ID'] if c in df_fechados_raw.columns), None)
        if id_col_fechados:
            ids_series = df_fechados_raw[id_col_fechados].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().dropna()
            closed_ticket_ids = ids_series.unique()
        else: st.warning("Arquivo de fechados sem coluna de ID.")

    # Calcula Aging para dados atuais (já filtrados)
    df_todos_com_aging = analisar_aging(df_atual.copy()) # Passa df_atual já filtrado
    if df_todos_com_aging.empty: st.error("Análise de aging falhou."); st.stop()

    # Separa abertos e fechados
    df_encerrados_filtrado = df_todos_com_aging[df_todos_com_aging[id_col_atual].isin(closed_ticket_ids)]
    df_aging = df_todos_com_aging[~df_todos_com_aging[id_col_atual].isin(closed_ticket_ids)]
    
    # --- Fim do Pré-processamento ---

    # Define as abas
    tab_titles = ["Dashboard Completo", "Report Visual", "Evolução Semanal", "Evolução Aging"]
    tab1, tab2, tab3, tab4 = st.tabs(tab_titles)
    
    # --- Conteúdo das Tabs ---
    with tab1: 
         # ... (código da tab 1 usando df_aging, df_encerrados_filtrado, df_15dias_filtrado) ...
        info_msg = ["**Filtros Aplicados:**", f"- Grupos ocultos ({', '.join(grupos_excluidos)}) e 'RH' desconsiderados.", "- Contagem dias: ignora dia da abertura."]
        if closed_ticket_ids.size > 0: info_msg.append(f"- {len(df_encerrados_filtrado)} fechados hoje movidos para tabela própria.")
        st.info("\n".join(info_msg))
        st.subheader("Backlog Atual - Análise de Antiguidade")
        hora_txt = f" (atualizado {hora_atualizacao_str})" if hora_atual_str else ""
        st.markdown(f"*Referência: {data_atual_str}{hora_txt}*", unsafe_allow_html=True)
        
        if not df_aging.empty:
            total_abertos = len(df_aging); total_fechados = len(df_encerrados_filtrado)
            cols_totais = st.columns([1, 1.5, 1.5, 1])
            with cols_totais[1]: st.markdown(f'<div class="metric-box"><span class="label">Chamados Abertos</span><span class="value">{total_abertos}</span></div>', unsafe_allow_html=True)
            with cols_totais[2]: st.markdown(f'<div class="metric-box"><span class="label">Fechados no Dia</span><span class="value">{total_fechados}</span></div>', unsafe_allow_html=True)
            st.markdown("---")
            # Cards de Faixas
            counts = df_aging['Faixa de Antiguidade'].value_counts()
            ordem = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
            cols_faixas = st.columns(len(ordem))
            if 'faixa_selecionada' not in st.session_state or st.session_state.faixa_selecionada not in ordem: st.session_state.faixa_selecionada = ordem[0]
            for i, faixa in enumerate(ordem):
                 qtd = counts.get(faixa, 0)
                 with cols_faixas[i]:
                      faixa_enc = quote(faixa)
                      st.markdown(f'<a href="?faixa={faixa_enc}&scroll=true" target="_self" class="metric-box"><span class="label">{faixa}</span><span class="value">{qtd}</span></a>', unsafe_allow_html=True)
        else: st.warning("Nenhum chamado aberto.")

        # Comparativo
        st.markdown(f"<h3>Comparativo vs. {data_15dias_str if not df_15dias_filtrado.empty else '15 Dias (Indisp.)'}</h3>", unsafe_allow_html=True)
        if not df_15dias_filtrado.empty:
            df_comp = processar_dados_comparativos(df_aging, df_15dias_filtrado) 
            if not df_comp.empty: 
                 st.dataframe(df_comp.set_index('Grupo').style.map(lambda v:'background-color:#ffcccc' if v>0 else ('background-color:#ccffcc' if v<0 else ''), subset=['Diferença']), use_container_width=True)
            else: st.info("Sem dados para comparação.")
        else: st.warning("Dados de 15 dias indisponíveis.")
        st.markdown("---")

        # Encerrados
        st.markdown(f"<h3>Chamados Encerrados ({data_atual_str})</h3>", unsafe_allow_html=True)
        if not closed_ticket_ids.size > 0: st.info("Arquivo de encerrados não carregado.")
        elif not df_encerrados_filtrado.empty:
            cols_f = [c for c in ['ID do ticket', 'Descrição', 'Atribuir a um grupo', 'Dias em Aberto'] if c in df_encerrados_filtrado.columns]
            st.data_editor(df_encerrados_filtrado[cols_f], hide_index=True, disabled=True, use_container_width=True, key="ed_fechados")
        else: st.info("Nenhum encerrado hoje nos grupos analisados.") 

        # Detalhar/Buscar Abertos
        if not df_aging.empty:
            st.markdown("---")
            st.subheader("Detalhar e Buscar Abertos", anchor="detalhar-e-buscar-chamados-abertos") 
            st.info('Marque Contato/Observações (salva automaticamente).')
            # Scroll JS
            if 'scroll_to_details' not in st.session_state: st.session_state.scroll_to_details = False
            if needs_scroll or st.session_state.get('scroll_to_details', False):
                 js="""<script>setTimeout(()=>{const e=window.parent.document.getElementById('detalhar-e-buscar-chamados-abertos');e&&e.scrollIntoView({behavior:'smooth',block:'start'})},250)</script>"""; components.html(js,height=0)
                 st.session_state.scroll_to_details=False 
            # Selectbox Faixa
            st.selectbox("Selecionar faixa:", options=ordem, key='faixa_selecionada') 
            faixa_sel = st.session_state.faixa_selecionada
            df_filt = df_aging[df_aging['Faixa de Antiguidade'] == faixa_sel].copy()
            if not df_filt.empty:
                def hl_row(r): return ['background-color:#fff8c4']*len(r) if r.get('Contato',False) else ['']*len(r)
                df_filt['Contato'] = df_filt['ID do ticket'].apply(lambda i: str(i) in st.session_state.contacted_tickets)
                df_filt['Observações'] = df_filt['ID do ticket'].apply(lambda i: st.session_state.observations.get(str(i), ''))
                st.session_state.last_filtered_df = df_filt.reset_index(drop=True) 
                cols_rename = {'Contato':'Contato','ID do ticket':'ID','Descrição':'Descrição','Atribuir a um grupo':'Grupo','Dias em Aberto':'Dias','Data de criação':'Criação','Observações':'Obs.'}
                cols_ex = [c for c in cols_rename if c in df_filt.columns]; cols_ren = [cols_rename[c] for c in cols_ex]
                cols_dis = [cols_rename[c] for c in cols_ex if c not in ['Contato','Observações']]
                st.data_editor(st.session_state.last_filtered_df.rename(columns=cols_rename)[cols_ren].style.apply(hl_row,axis=1), use_container_width=True,hide_index=True,disabled=cols_dis,key='ticket_editor',on_change=sync_ticket_data)
            else: st.info(f"Sem chamados em '{faixa_sel}'.")
            # Busca Grupo
            st.subheader("Buscar Abertos por Grupo")
            if 'Atribuir a um grupo' in df_aging.columns:
                 grupos = sorted(df_aging['Atribuir a um grupo'].dropna().unique())
                 if grupos:
                      grupo_sel = st.selectbox("Selecionar grupo:", options=grupos, key="busca_grupo")
                      if grupo_sel:
                           df_busca = df_aging[df_aging['Atribuir a um grupo']==grupo_sel].copy()
                           d_col_b = next((c for c in ['Data de criação','Data de Criacao'] if c in df_busca.columns),None)
                           if d_col_b: df_busca[d_col_b]=pd.to_datetime(df_busca[d_col_b]).dt.strftime('%d/%m/%Y')
                           st.write(f"{len(df_busca)} para '{grupo_sel}':")
                           cols_b = ['ID do ticket','Descrição','Dias em Aberto',d_col_b]; cols_ex_b = [c for c in cols_b if c in df_busca.columns and c] 
                           st.data_editor(df_busca[cols_ex_b],use_container_width=True,hide_index=True,disabled=True,key="ed_busca")
                 else: st.info("Nenhum grupo.")
            else: st.warning("Coluna 'Atribuir a um grupo' ausente.")

    with tab2:
        # ... (Código Tab 2 corrigido para o TypeError) ...
        st.subheader("Resumo do Backlog Atual")
        if not df_aging.empty:
            total_chamados = len(df_aging)
            _, col_total_tab2, _ = st.columns([2, 1.5, 2])
            with col_total_tab2: st.markdown( f"""<div class="metric-box"><span class="label">Total de Chamados</span><span class="value">{total_chamados}</span></div>""", unsafe_allow_html=True )
            st.markdown("---")
            # Cards de faixas (igual Tab 1)
            aging_counts_tab2 = df_aging['Faixa de Antiguidade'].value_counts()
            ordem_faixas = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
            cols_tab2 = st.columns(len(ordem_faixas))
            for i, faixa in enumerate(ordem_faixas):
                qtd = aging_counts_tab2.get(faixa, 0)
                with cols_tab2[i]: st.markdown( f"""<div class="metric-box"><span class="label">{faixa}</span><span class="value">{qtd}</span></div>""", unsafe_allow_html=True )
            st.markdown("---")
            
            st.subheader("Distribuição do Backlog por Grupo")
            orientation_choice = st.radio( "Orientação:", ["Vertical", "Horizontal"], index=0, horizontal=True, key="orient_tab2" )
            
            if 'Atribuir a um grupo' in df_aging.columns and 'Faixa de Antiguidade' in df_aging.columns:
                 chart_data = df_aging.groupby(['Atribuir a um grupo', 'Faixa de Antiguidade'], observed=False).size().reset_index(name='Quantidade') # observed=False é importante
                 group_totals = chart_data.groupby('Atribuir a um grupo')['Quantidade'].sum().sort_values(ascending=False)
                 
                 if not group_totals.empty:
                      new_labels_map = {group: f"{group} ({total})" for group, total in group_totals.items()}
                      chart_data['Grupo (Total)'] = chart_data['Atribuir a um grupo'].map(new_labels_map) # Nova coluna para o eixo
                      sorted_new_labels = [new_labels_map[group] for group in group_totals.index] # Ordem para category_orders
                      
                      def lighten_color(hex_color, amount=0.2):
                          try: h,l,s=colorsys.rgb_to_hls(*[int(hex_color.lstrip('#')[i:i+2],16)/255. for i in (0,2,4)]); r,g,b=colorsys.hls_to_rgb(h,l+(1-l)*amount,s); return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
                          except: return hex_color
                      base="#375623"; palette=[lighten_color(base,v) for v in [0.85,0.7,0.55,0.4,0.2,0]]; color_map=dict(zip(ordem_faixas,palette))
                      
                      # Define category_orders uma vez
                      category_orders_map = { 
                          'Faixa de Antiguidade': ordem_faixas,
                          'Grupo (Total)': sorted_new_labels # Usa a nova coluna aqui
                      }
                      
                      plot_args = dict(data_frame=chart_data, color='Faixa de Antiguidade', title="Composição da Idade por Grupo",
                                       category_orders=category_orders_map, color_discrete_map=color_map, text_auto=True)
                      
                      if orientation_choice == 'Horizontal':
                          fig = px.bar( **plot_args, x='Quantidade', y='Grupo (Total)', orientation='h', labels={'Quantidade': 'Qtd.', 'Grupo (Total)': ''}) 
                          fig.update_layout(height=max(500, len(group_totals) * 30), yaxis={'categoryorder':'array', 'categoryarray':sorted_new_labels[::-1]}) 
                      else: # Vertical
                          fig = px.bar( **plot_args, x='Grupo (Total)', y='Quantidade', labels={'Quantidade': 'Qtd.', 'Grupo (Total)': 'Grupo'}) 
                          fig.update_layout(height=600, xaxis_title=None, xaxis_tickangle=-45)
                      
                      fig.update_traces(textangle=0, textfont_size=12); fig.update_layout(legend_title_text='Antiguidade')
                      st.plotly_chart(fig, use_container_width=True)
                 else: st.info("Nenhum grupo encontrado.")
            else: st.warning("Colunas 'Atribuir a um grupo' ou 'Faixa de Antiguidade' ausentes.")
        else: st.warning("Dados de aging indisponíveis.")


    with tab3:
        # ... (Código Tab 3 - Usa _repo na chamada) ...
        st.subheader("Evolução Semanal do Backlog") # Título mais específico
        dias_evolucao = st.slider("Ver evolução (dias úteis):", 7, 30, 7, key="slider_evolucao")
        df_evolucao_tab3 = carregar_dados_evolucao(_repo, dias_para_analisar=dias_evolucao) # Passa _repo

        if not df_evolucao_tab3.empty:
            df_evolucao_tab3['Data'] = pd.to_datetime(df_evolucao_tab3['Data'])
            df_evolucao_semana = df_evolucao_tab3[df_evolucao_tab3['Data'].dt.dayofweek < 5].copy()

            if not df_evolucao_semana.empty:
                st.info("Considera snapshots de dias úteis. Filtros ocultos/RH aplicados.")
                df_total_diario = df_evolucao_semana.groupby('Data')['Total Chamados'].sum().reset_index().sort_values('Data')
                df_total_diario['Data (Eixo)'] = df_total_diario['Data'].dt.strftime('%d/%m')
                ordem_datas_total = df_total_diario['Data (Eixo)'].tolist()
                fig_total = px.area(df_total_diario, x='Data (Eixo)', y='Total Chamados', title='Evolução Total (Dias Úteis)', markers=True, labels={"Data (Eixo)": "Data", "Total Chamados": "Total"}, category_orders={'Data (Eixo)': ordem_datas_total})
                fig_total.update_layout(height=400); st.plotly_chart(fig_total, use_container_width=True)
                st.markdown("---")
                st.info("Clique na legenda para filtrar grupos.")
                df_evo_sem_sort = df_evolucao_semana.sort_values('Data')
                df_evo_sem_sort['Data (Eixo)'] = df_evo_sem_sort['Data'].dt.strftime('%d/%m')
                ordem_dt_grp = df_evo_sem_sort['Data (Eixo)'].unique().tolist()
                df_disp = df_evo_sem_sort.rename(columns={'Atribuir a um grupo': 'Grupo'})
                fig_grupo = px.line(df_disp, x='Data (Eixo)', y='Total Chamados', color='Grupo', title='Evolução por Grupo (Dias Úteis)', markers=True, labels={ "Data (Eixo)": "Data", "Total Chamados": "Nº Chamados"}, category_orders={'Data (Eixo)': ordem_dt_grp})
                fig_grupo.update_layout(height=600); st.plotly_chart(fig_grupo, use_container_width=True)
            else: st.info("Sem dados históricos suficientes em dias úteis.")
        else: st.info("Não foi possível carregar dados históricos.")


    with tab4:
        # ... (Código Tab 4 - Usa _repo nas chamadas, cálculo relativo já corrigido) ...
        st.subheader("Evolução do Aging do Backlog")
        st.info("Compara o aging de hoje com dias anteriores (idade calculada sempre relativa ao dia do snapshot).") # Mudei aqui

        try:
            # Chama a função que agora calcula aging relativo ao snapshot
            df_hist = carregar_evolucao_aging(_repo, dias_para_analisar=90) # Passa _repo

            ordem_faixas_scaffold = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
            hoje_data = None
            hoje_counts_df = pd.DataFrame() 

            # Calcula contagem de HOJE (igual antes)
            if 'df_aging' in locals() and not df_aging.empty and data_atual_str != 'N/A':
                try:
                    hoje_data = pd.to_datetime(datetime.strptime(data_atual_str, "%d/%m/%Y").date())
                    hoje_counts_raw = df_aging['Faixa de Antiguidade'].value_counts().reset_index(name='total')
                    df_todas_faixas_hoje = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas_scaffold})
                    hoje_counts_df = pd.merge(df_todas_faixas_hoje, hoje_counts_raw, on='Faixa de Antiguidade', how='left').fillna(0)
                    hoje_counts_df['total'] = hoje_counts_df['total'].astype(int)
                    hoje_counts_df['data'] = hoje_data 
                except ValueError: st.warning(f"Data atual inválida: '{data_atual_str}'."); hoje_data = None 
            else: st.warning("Dados de 'hoje' (df_aging) indisponíveis.")

            # Combina histórico e hoje (igual antes)
            if not df_hist.empty and not hoje_counts_df.empty:
                 df_combinado = pd.concat([df_hist, hoje_counts_df], ignore_index=True).drop_duplicates(subset=['data', 'Faixa de Antiguidade'], keep='last') 
            elif not df_hist.empty: df_combinado = df_hist.copy(); st.warning("Dados de 'hoje' indisponíveis.")
            elif not hoje_counts_df.empty: df_combinado = hoje_counts_df.copy(); st.warning("Dados históricos indisponíveis.")
            else: st.error("Sem dados históricos ou de hoje para aging."); st.stop() 

            df_combinado['data'] = pd.to_datetime(df_combinado['data'])
            df_combinado = df_combinado.sort_values(by=['data', 'Faixa de Antiguidade'])

            # Comparativo Cards (igual antes)
            st.markdown("##### Comparativo")
            periodo_opts = { "Ontem": 1, "7 dias atrás": 7, "15 dias atrás": 15, "30 dias atrás": 30 }
            periodo_sel = st.radio("Comparar 'Hoje' com:", periodo_opts.keys(), horizontal=True, key="radio_comp")
            data_comp_final, df_comp_dados, data_comp_str = None, pd.DataFrame(), "N/A"

            if hoje_data:
                target_date = hoje_data.date() - timedelta(days=periodo_opts[periodo_sel])
                data_comp_encontrada, _ = find_closest_snapshot_before(_repo, hoje_data.date(), target_date) # Passa _repo
                if data_comp_encontrada:
                    data_comp_final = pd.to_datetime(data_comp_encontrada)
                    data_comp_str = data_comp_final.strftime('%d/%m')
                    df_comp_dados = df_combinado[df_combinado['data'] == data_comp_final].copy() 
                    if df_comp_dados.empty: data_comp_final = None 
            
            # Exibe Cards (igual antes)
            cols_map = {i: col for i, col in enumerate(st.columns(3) + st.columns(3))}
            for i, faixa in enumerate(ordem_faixas_scaffold):
                with cols_map[i]:
                    valor_hj, delta_txt, delta_cls = 'N/A', "N/A", "delta-neutral"
                    if not hoje_counts_df.empty:
                        val_hj_s = hoje_counts_df.loc[hoje_counts_df['Faixa de Antiguidade'] == faixa, 'total']
                        if not val_hj_s.empty:
                            valor_hj = int(val_hj_s.iloc[0])
                            if data_comp_final and not df_comp_dados.empty:
                                val_comp_s = df_comp_dados.loc[df_comp_dados['Faixa de Antiguidade'] == faixa, 'total']
                                val_comp = int(val_comp_s.iloc[0]) if not val_comp_s.empty else 0
                                delta_a = valor_hj - val_comp; delta_p = (delta_a/val_comp) if val_comp > 0 else 0
                                delta_txt, delta_cls = formatar_delta_card(delta_a, delta_p, val_comp, data_comp_str)
                            elif hoje_data: delta_txt = "Sem dados para comparar"
                        else: valor_hj = 0; delta_txt = "N/A"
                    elif not hoje_data: delta_txt = "Dados de hoje indisponíveis"
                    st.markdown(f'<div class="metric-box"><span class="label">{faixa}</span><span class="value">{valor_hj}</span><span class="delta {delta_cls}">{delta_txt}</span></div>', unsafe_allow_html=True)

            st.divider()

            # Gráfico Evolução 7 dias (igual antes)
            st.markdown(f"##### Gráfico de Evolução (Últimos 7 dias)")
            hoje_f_g = date.today(); dt_ini_f_g = hoje_f_g - timedelta(days=6) 
            df_f_g = df_combinado[df_combinado['data'].dt.date >= dt_ini_f_g].copy()

            if df_f_g.empty: st.warning("Sem dados de aging para os últimos 7 dias.")
            else:
                df_g = df_f_g.sort_values(by='data')
                df_g['Data (Eixo)'] = df_g['data'].dt.strftime('%d/%m')
                ordem_dt_g = df_g['Data (Eixo)'].unique().tolist() 
                def l_c(h, a=0.2):
                    try: h=h.lstrip('#'); H,L,S=colorsys.rgb_to_hls(*[int(h[i:i+2],16)/255. for i in(0,2,4)]); r,g,b=colorsys.hls_to_rgb(H,L+(1-L)*a,S); return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
                    except: return h
                b="#375623"; pal=[l_c(b,v) for v in [0.85,0.7,0.55,0.4,0.2,0]]; cmap=dict(zip(ordem_faixas_scaffold,pal))
                t_g = st.radio("Tipo:", ("Linha", "Área"), index=1, horizontal=True, key="radio_tipo_g") # Default para Área
                p_f = px.line if t_g == "Linha" else px.area
                t_suf = "(Comparativo)" if t_g == "Linha" else "(Composição)"
                fig = p_f(df_g, x='Data (Eixo)', y='total', color='Faixa de Antiguidade', title=f'Evolução Aging {t_suf} - 7 dias', markers=True, labels={"Data (Eixo)": "Data", "total": "Chamados", "Faixa de Antiguidade": "Faixa"}, category_orders={'Data (Eixo)': ordem_dt_g, 'Faixa de Antiguidade': ordem_faixas_scaffold}, color_discrete_map=cmap)
                fig.update_layout(height=500, legend_title_text='Faixa'); st.plotly_chart(fig, use_container_width=True)

        except Exception as e: st.error(f"Erro Tab Evolução Aging: {e}"); st.exception(e) 

# --- Tratamento Final de Erros ---
except Exception as e:
    st.error(f"Erro GERAL: {e}") 
    import traceback
    st.exception(e) 
    
# --- Rodapé ---
st.markdown("---")
st.markdown(""" 
<p style='text-align: center; color: #666; font-size: 0.9em; margin-bottom: 0;'>v0.9.36 | Em desenvolvimento.</p>
<p style='text-align: center; color: #666; font-size: 0.9em; margin-top: 0;'>Desenvolvido por Leonir Scatolin Junior</p>
""", unsafe_allow_html=True)
