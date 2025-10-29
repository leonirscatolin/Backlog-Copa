# VERSÃO v0.9.30-740 (Corrigida - TypeError isin 'na')

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
             raise 
        
        repo = g.get_repo(expected_repo_name)
        # st.sidebar.caption(f"Conectado a: {repo.full_name}") 
        return repo
        
    except ValueError as ve: 
         st.error(f"Configuração incompleta: {ve}")
         st.stop()
    except ConnectionError as ce: 
         st.error(str(ce))
         st.stop()
    except GithubException as e: 
        msg = e.data.get('message', 'Erro desconhecido')
        if e.status == 404: st.error(f"Erro GitHub (404): Repositório '{expected_repo_name}' não encontrado ou token sem permissão.")
        else: st.error(f"Erro GitHub ({e.status}): {msg}")
        st.stop()
    except Exception as e: 
        st.error(f"Erro inesperado ao conectar ao GitHub: {e}")
        st.stop()

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
             if file_path not in ["contacted_tickets.json", "ticket_observations.json", "datas_referencia.txt"]: pass
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
            raise 

@st.cache_data(ttl=300) 
def read_github_file(_repo, file_path):
    """Lê um arquivo CSV do GitHub, tratando encoding e erros."""
    if _repo is None: return pd.DataFrame() 

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
            try:
                df = pd.read_csv(StringIO(content), delimiter=';', dtype=dtype_map, low_memory=False, on_bad_lines='warn') 
            except (pd.errors.ParserError, ValueError): # Adicionado ValueError para pegar mais erros de parsing
                 st.warning(f"Falha ao ler '{file_path}' com ';'. Tentando com ','.")
                 content_io = StringIO(content) 
                 df = pd.read_csv(content_io, delimiter=',', dtype=dtype_map, low_memory=False, on_bad_lines='warn')
                 
        except Exception as read_err: raise ValueError(f"Read Error: {read_err}")

        df.columns = df.columns.str.strip() 
        df.dropna(how='all', inplace=True) 
        return df

    except GithubException as e:
        if e.status != 404: st.error(f"Erro GitHub ({e.status}) ao ler '{file_path}': {e.data.get('message', 'Erro')}")
        return pd.DataFrame() 
    except ValueError as ve: 
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
    condicoes=[dias_series>=30,(dias_series>=21)&(dias_series<=29),(dias_series>=11)&(dias_series<=20),(dias_series>=6)&(dias_series<=10),(dias_series>=3)&(dias_series<=5),(dias_series>=0)&(dias_series<=2)]
    opcoes=["30+ dias","21-29 dias","11-20 dias","6-10 dias","3-5 dias","0-2 dias"];return np.select(condicoes,opcoes,default="Inválido")

@st.cache_data
def analisar_aging(_df_atual):
    # ... (código inalterado, com debug) ...
    if _df_atual is None or _df_atual.empty: st.warning("analisar_aging: DF vazio."); return pd.DataFrame()
    df = _df_atual.copy(); date_col=next((c for c in ['Data de criação','Data de Criacao'] if c in df.columns),None)
    if not date_col: st.warning(f"analisar_aging: Col data não encontrada. Cols: {df.columns.tolist()}"); return pd.DataFrame(columns=list(df.columns)+['Dias em Aberto','Faixa de Antiguidade'])
    orig_dtype=df[date_col].dtype; df[date_col]=pd.to_datetime(df[date_col],errors='coerce')
    inv_linhas=df[df[date_col].isna()&_df_atual[date_col].notna()]
    if not inv_linhas.empty:
        with st.expander(f"⚠️ analisar_aging: {len(inv_linhas)} datas inválidas ('{date_col}', tipo: {orig_dtype})."):
             cols_dbg=[c for c in ['ID do ticket',date_col,'Atribuir a um grupo'] if c in inv_linhas.columns]
             st.dataframe(inv_linhas[cols_dbg].head().assign(**{date_col:_df_atual.loc[inv_linhas.index,date_col].head()}))
    df=df.dropna(subset=[date_col])
    if df.empty: st.warning(f"analisar_aging: Sem datas válidas ('{date_col}') após limpeza."); return pd.DataFrame(columns=list(df.columns)+['Dias em Aberto','Faixa de Antiguidade'])
    hoje=pd.to_datetime('today').normalize(); dt_cria=df[date_col].dt.normalize(); dias=(hoje-dt_cria).dt.days
    df['Dias em Aberto']=(dias-1).clip(lower=0); df['Faixa de Antiguidade']=categorizar_idade_vetorizado(df['Dias em Aberto'])
    inv_cat=df[df['Faixa de Antiguidade']=='Inválido']
    if not inv_cat.empty: st.warning(f"analisar_aging: {len(inv_cat)} idades inválidas (cat: Inválido).")
    if 'Dias em Aberto' not in df.columns: df['Dias em Aberto']=-1
    if 'Faixa de Antiguidade' not in df.columns: df['Faixa de Antiguidade']='Erro'
    cols_ret=[c for c in _df_atual.columns if c in df.columns]+['Dias em Aberto','Faixa de Antiguidade']; return df[cols_ret]

def get_status(row):
    # ... (código inalterado) ...
    diferenca=row.get('Diferença',0);return "Alta Demanda" if diferenca>0 else ("Redução de Backlog" if diferenca<0 else "Estável / Atenção")

# ... (código sync_ticket_data inalterado) ...
def sync_ticket_data():
    if 'ticket_editor' not in st.session_state or not st.session_state.ticket_editor.get('edited_rows'): return
    edited=st.session_state.ticket_editor['edited_rows']; contact_ch,obs_ch=False,False
    orig_cont=st.session_state.contacted_tickets.copy(); orig_obs=st.session_state.observations.copy()
    try:
        for idx,changes in edited.items():
            try:
                tid=str(st.session_state.last_filtered_df.iloc[idx].get('ID do ticket',None))
                if tid is None: continue
                if 'Contato' in changes:
                    curr=tid in st.session_state.contacted_tickets; new=changes['Contato']
                    if curr!=new:(st.session_state.contacted_tickets.add(tid) if new else st.session_state.contacted_tickets.discard(tid)); contact_ch=True
                if 'Observações' in changes:
                    curr=st.session_state.observations.get(tid,''); new=str(changes['Observações'] or '')
                    if curr!=new: st.session_state.observations[tid]=new; obs_ch=True
            except IndexError: st.warning(f"Erro índice {idx}."); continue
            except Exception as e: st.warning(f"Erro linha {idx}: {e}."); continue
        if contact_ch or obs_ch:
            now=datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M'); repo=st.session_state.get('repo')
            if repo is None: raise ConnectionError("Repo não iniciado.")
            if contact_ch: data=list(st.session_state.contacted_tickets); cont=json.dumps(data,indent=4).encode('utf-8'); update_github_file(repo,"contacted_tickets.json",cont,f"Atualizando contatos em {now}")
            if obs_ch: cont=json.dumps(st.session_state.observations,indent=4,ensure_ascii=False).encode('utf-8'); update_github_file(repo,"ticket_observations.json",cont,f"Atualizando obs em {now}")
        st.session_state.ticket_editor['edited_rows']={}
    except ConnectionError as ce: st.error(str(ce))
    except Exception as e:
        st.error(f"Falha CRÍTICA salvar: {e}"); st.warning("Revertendo locais.");
        st.session_state.contacted_tickets=orig_cont; st.session_state.observations=orig_obs
        st.session_state.ticket_editor['edited_rows']={}
    st.session_state.scroll_to_details=True; st.rerun()

@st.cache_data(ttl=3600, show_spinner="Carregando evolução semanal...")
def carregar_dados_evolucao(_repo, dias_para_analisar=7):
    # ... (código carregar_dados_evolucao com correção isin) ...
    global grupos_excluidos
    if _repo is None: return pd.DataFrame() 
    try:
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
                    # CORREÇÃO isin: Remover na=False
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

@st.cache_data(ttl=300)
def find_closest_snapshot_before(_repo, current_report_date, target_date):
    # ... (código inalterado) ...
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

@st.cache_data(ttl=3600, show_spinner="Carregando histórico de aging...") 
def carregar_evolucao_aging(_repo, dias_para_analisar=90):
    # ... (código carregar_evolucao_aging com correção isin e cálculo relativo) ...
    global grupos_excluidos
    if _repo is None: return pd.DataFrame() 

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
                    date_str = file_name.split('_')[-1].split('.')[0] 
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if start_date <= file_date <= end_date: 
                        processed_files.append((file_date, file_name))
                except (ValueError, IndexError): continue
                except Exception as e: st.warning(f"Erro nome snapshot {file_name} aging: {e}"); continue
        
        processed_files.sort(key=lambda x: x[0]) 

        for file_date, file_name in processed_files:
            try:
                df_snapshot = read_github_file(_repo, file_name) 
                if df_snapshot.empty or 'Atribuir a um grupo' not in df_snapshot.columns: continue

                # CORREÇÃO isin: Remover na=False
                df_filtrado = df_snapshot[~df_snapshot['Atribuir a um grupo'].isin(grupos_excluidos)] 
                df_filtrado = df_filtrado[~df_filtrado['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]

                if df_filtrado.empty: continue 

                df_calc_aging = df_filtrado.copy()
                date_col_hist = next((c for c in ['Data de criação','Data de Criacao'] if c in df_calc_aging.columns),None)
                if not date_col_hist: continue 

                df_calc_aging[date_col_hist] = pd.to_datetime(df_calc_aging[date_col_hist], errors='coerce')
                df_calc_aging = df_calc_aging.dropna(subset=[date_col_hist])
                if df_calc_aging.empty: continue

                snap_dt = pd.to_datetime(file_date) 
                cria_norm = df_calc_aging[date_col_hist].dt.normalize()
                dias_hist = (snap_dt - cria_norm).dt.days
                df_calc_aging['Dias em Aberto'] = (dias_hist - 1).clip(lower=0) 
                df_calc_aging['Faixa de Antiguidade'] = categorizar_idade_vetorizado(df_calc_aging['Dias em Aberto'])
                
                inv_hist = df_calc_aging[df_calc_aging['Faixa de Antiguidade'] == 'Inválido']
                if not inv_hist.empty: st.warning(f"{len(inv_hist)} idades inválidas snapshot {file_name}.")
                
                df_com_aging = df_calc_aging 
                if df_com_aging.empty or 'Faixa de Antiguidade' not in df_com_aging.columns: continue 
                
                cont_faixas = df_com_aging['Faixa de Antiguidade'].value_counts().reset_index(name='total')
                ordem_scaff = ["0-2 dias","3-5 dias","6-10 dias","11-20 dias","21-29 dias","30+ dias"]
                df_scaff = pd.DataFrame({'Faixa de Antiguidade': ordem_scaff})
                cont_compl = pd.merge(df_scaff, cont_faixas, on='Faixa de Antiguidade', how='left').fillna(0)
                cont_compl['total'] = cont_compl['total'].astype(int)
                cont_compl['data'] = pd.to_datetime(file_date) 
                lista_historico.append(cont_compl)
            except Exception as e: st.warning(f"Erro aging snapshot {file_name}: {e}"); continue 

        if not lista_historico: st.warning("Nenhum dado histórico de aging carregado."); return pd.DataFrame()
        return pd.concat(lista_historico, ignore_index=True)
    except GithubException as e:
         if e.status != 404: st.warning(f"Erro GitHub carregar aging: {e.data.get('message', e)}")
         return pd.DataFrame()
    except Exception as e: st.error(f"Erro carregar_evolucao_aging: {e}"); return pd.DataFrame()

# ... (código formatar_delta_card inalterado) ...
def formatar_delta_card(delta_abs, delta_perc, valor_comparacao, data_comparacao_str):
    delta_abs = int(delta_abs)
    if valor_comparacao > 0: delta_perc_str = f"({delta_perc * 100:+.1f}%)"; delta_text = f"{delta_abs:+} {delta_perc_str} vs. {data_comparacao_str}"
    elif valor_comparacao == 0 and delta_abs > 0: delta_text = f"+{delta_abs} (Novo) vs. {data_comparacao_str}" 
    elif valor_comparacao == 0 and delta_abs < 0: delta_text = f"{delta_abs} vs. {data_comparacao_str}" 
    else: delta_text = f"0 (=) vs. {data_comparacao_str}" 
    if delta_abs > 0: delta_class = "delta-positive"
    elif delta_abs < 0: delta_class = "delta-negative"
    else: delta_class = "delta-neutral"
    return delta_text, delta_class


# --- Código Principal (Início) ---
# Display Logos
logo_copa_b64 = get_image_as_base64("logo_sidebar.png")
logo_belago_b64 = get_image_as_base64("logo_belago.png")
# ... (código display logos inalterado) ...
if logo_copa_b64 and logo_belago_b64:
    st.markdown(f"""<div style="display: flex; justify-content: space-between; align-items: center;"><img src="data:image/png;base64,{logo_copa_b64}" width="150"><h1 style='text-align: center; margin: 0;'>Backlog Copa Energia + Belago</h1><img src="data:image/png;base64,{logo_belago_b64}" width="150"></div>""", unsafe_allow_html=True)
else:
    st.markdown("<h1 style='text-align: center; margin: 0;'>Backlog Copa Energia + Belago</h1>", unsafe_allow_html=True)


# Inicializa conexão GitHub
try:
    if 'repo' not in st.session_state: st.session_state.repo = get_github_repo()
    if st.session_state.repo is None: st.error("Falha ao inicializar conexão GitHub."); st.stop()
    _repo = st.session_state.repo 
except Exception as e: st.error(f"Erro CRÍTICO inicialização: {e}"); st.stop()

# --- Sidebar do Admin ---
# ... (código sidebar inalterado) ...
st.sidebar.header("Área do Administrador")
password = st.sidebar.text_input("Senha:", type="password", key="admin_pass")
admin_pass_secret = st.secrets.get("ADMIN_PASSWORD", "") 
is_admin = bool(password and password == admin_pass_secret) if admin_pass_secret else False
if password and not is_admin and admin_pass_secret: st.sidebar.error("Senha incorreta.")
elif not admin_pass_secret: st.sidebar.warning("Senha admin não configurada.")

if is_admin:
    st.sidebar.success("Acesso Admin OK.")
    st.sidebar.subheader("Atualização Completa")
    up_atual = st.sidebar.file_uploader("1. Backlog ATUAL", ["csv","xlsx"], key="up_atual")
    up_15d = st.sidebar.file_uploader("2. Backlog 15 DIAS", ["csv","xlsx"], key="up_15d")
    if st.sidebar.button("Salvar Novos Dados (Completo)"): 
        if up_atual and up_15d:
            with st.spinner("Processando e salvando..."):
                now=datetime.now(ZoneInfo('America/Sao_Paulo')); msg=f"Dados atualizados em {now:%d/%m/%Y %H:%M}"
                cont_at=process_uploaded_file(up_atual); cont_15=process_uploaded_file(up_15d)
                if cont_at and cont_15:
                    try:
                        update_github_file(_repo,"dados_atuais.csv",cont_at,msg); update_github_file(_repo,"dados_15_dias.csv",cont_15,msg)
                        snap_p=f"snapshots/backlog_{now:%Y-%m-%d}.csv"; update_github_file(_repo,snap_p,cont_at,f"Snapshot {now:%Y-%m-%d}")
                        dref=(f"data_atual:{now.date():%d/%m/%Y}\n"
                              f"data_15dias:{(now.date()-timedelta(days=15)):%d/%m/%Y}\n"
                              f"hora_atualizacao:{now:%H:%M}")
                        update_github_file(_repo,"datas_referencia.txt",dref.encode('utf-8'),msg)
                        st.cache_data.clear(); st.cache_resource.clear(); st.sidebar.success("Salvo! Recarregando..."); st.rerun()
                    except Exception as e: st.sidebar.error(f"Erro ao salvar: {e}")
                else: st.sidebar.error("Falha ao processar arquivos.")
        else: st.sidebar.warning("Carregue AMBOS os arquivos.")
            
    st.sidebar.markdown("---"); st.sidebar.subheader("Atualização Rápida (Fechados)")
    up_fec = st.sidebar.file_uploader("Apenas FECHADOS no dia", ["csv","xlsx"], key="up_fec")
    if st.sidebar.button("Salvar Apenas Fechados"):
        if up_fec:
            with st.spinner("Salvando fechados..."):
                now=datetime.now(ZoneInfo('America/Sao_Paulo')); msg=f"Atualizando fechados em {now:%d/%m/%Y %H:%M}"
                cont_fec=process_uploaded_file(up_fec)
                if cont_fec:
                    try:
                        update_github_file(_repo,"dados_fechados.csv",cont_fec,msg)
                        d_ex=read_github_text_file(_repo,"datas_referencia.txt")
                        dref_n=(f"data_atual:{d_ex.get('data_atual','N/A')}\n"
                                f"data_15dias:{d_ex.get('data_15dias','N/A')}\n"
                                f"hora_atualizacao:{now:%H:%M}") 
                        update_github_file(_repo,"datas_referencia.txt",dref_n.encode('utf-8'),msg)
                        st.cache_data.clear(); st.cache_resource.clear(); st.sidebar.success("Fechados salvos! Recarregando..."); st.rerun()
                    except Exception as e: st.sidebar.error(f"Erro ao salvar fechados: {e}")
                else: st.sidebar.error("Falha ao processar arquivo.")
        else: st.sidebar.warning("Carregue o arquivo.")


# --- Bloco Principal de Processamento ---
try:
    # Carrega estado (contatos, observações)
    if 'contacted_tickets' not in st.session_state:
        try:
            c_file=_repo.get_contents("contacted_tickets.json"); c_str=c_file.decoded_content.decode("utf-8")
            st.session_state.contacted_tickets=set(json.loads(c_str)) if c_str.strip() else set()
        except GithubException as e:
             if e.status!=404: st.error(f"Erro GitHub contatos({e.status})")
             st.session_state.contacted_tickets=set() 
        except json.JSONDecodeError: st.warning("'contacted_tickets.json' inválido."); st.session_state.contacted_tickets=set()
        except Exception as e: st.error(f"Erro lendo contatos: {e}"); st.session_state.contacted_tickets=set()

    if 'observations' not in st.session_state: st.session_state.observations = read_github_json_dict(_repo, "ticket_observations.json")

    # Trata URL params
    needs_scroll="scroll" in st.query_params; ordem_faixas=["0-2 dias","3-5 dias","6-10 dias","11-20 dias","21-29 dias","30+ dias"]
    if "faixa" in st.query_params: f_url=st.query_params.get("faixa"); st.session_state.faixa_selecionada=(f_url if f_url in ordem_faixas else ordem_faixas[0])
    if "scroll" in st.query_params or "faixa" in st.query_params: st.query_params.clear() 

    # --- Carrega Dados Base ---
    df_atual=read_github_file(_repo,"dados_atuais.csv"); df_15dias=read_github_file(_repo,"dados_15_dias.csv"); df_fechados_raw=read_github_file(_repo,"dados_fechados.csv") 
    datas_ref=read_github_text_file(_repo,"datas_referencia.txt"); data_atual_str=datas_ref.get('data_atual','N/A'); data_15dias_str=datas_ref.get('data_15dias','N/A'); hora_atual_str=datas_ref.get('hora_atualizacao','')
    if df_atual.empty: st.warning("'dados_atuais.csv' vazio/não encontrado."); st.stop()

    # --- Aplica Filtros e Padroniza IDs ---
    id_col='ID do ticket'; grupo_col='Atribuir a um grupo' # Nomes padrão
    # Encontra nome real da coluna de grupo
    grupo_col_real=next((c for c in [grupo_col,'grupo','Grupo'] if c in df_atual.columns), None) 
    if not grupo_col_real: st.error("Coluna de Grupo não encontrada."); st.stop()
    # Encontra nome real da coluna de ID
    id_col_real=next((c for c in [id_col,'ID do Ticket','ID'] if c in df_atual.columns),None)
    if not id_col_real: st.error("Coluna de ID não encontrada."); st.stop()
    # Renomeia se necessário e limpa ID
    if grupo_col_real!=grupo_col: df_atual.rename(columns={grupo_col_real:grupo_col},inplace=True)
    if id_col_real!=id_col: df_atual.rename(columns={id_col_real:id_col},inplace=True)
    df_atual[id_col]=df_atual[id_col].astype(str).str.replace(r'\.0$','',regex=True).str.strip()
    
    # Filtra grupos ocultos e RH
    # CORREÇÃO isin: Remover na=False
    df_atual=df_atual[~df_atual[grupo_col].isin(grupos_excluidos)].copy() 
    df_atual=df_atual[~df_atual[grupo_col].str.contains('RH',case=False,na=False)]
    if df_atual.empty: st.warning("Nenhum chamado após filtros (ocultos, RH)."); st.stop()

    # Processa df_15dias (para comparação)
    df_15dias_filtrado=pd.DataFrame() 
    if not df_15dias.empty:
        g_col_15=next((c for c in [grupo_col,'grupo','Grupo'] if c in df_15dias.columns),None)
        if g_col_15:
             if g_col_15!=grupo_col: df_15dias.rename(columns={g_col_15:grupo_col},inplace=True)
             # CORREÇÃO isin: Remover na=False
             df_15_f=df_15dias[~df_15dias[grupo_col].isin(grupos_excluidos)].copy() 
             df_15dias_filtrado=df_15_f[~df_15_f[grupo_col].str.contains('RH',case=False,na=False)]
        else: st.warning("Dados 15 dias sem coluna de Grupo.")
        
    # Processa Fechados
    closed_ids=np.array([]) 
    if not df_fechados_raw.empty:
        id_col_fec=next((c for c in [id_col,'ID do Ticket','ID'] if c in df_fechados_raw.columns),None)
        if id_col_fec: ids_s=df_fechados_raw[id_col_fec].astype(str).str.replace(r'\.0$','',regex=True).str.strip().dropna(); closed_ids=ids_s.unique()
        else: st.warning("Fechados sem coluna de ID.")

    # Calcula Aging (df_atual já está filtrado)
    df_todos_ag=analisar_aging(df_atual.copy()) 
    if df_todos_ag.empty: st.error("Análise de aging falhou."); st.stop()

    # Separa abertos/fechados
    df_enc_filt=df_todos_ag[df_todos_ag[id_col].isin(closed_ids)]
    df_aging=df_todos_ag[~df_todos_ag[id_col].isin(closed_ids)]
    
    # --- Fim Pré-processamento ---

    tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Visual", "Evolução", "Aging"]) # Nomes curtos
    
    with tab1: 
         # ... (código tab 1 usando df_aging, df_enc_filt, df_15dias_filtrado) ...
        info_msg = ["**Filtros:**", f"- Ocultos ({len(grupos_excluidos)}), RH.", "- Dias: ignora dia abertura."]
        if closed_ids.size>0: info_msg.append(f"- {len(df_enc_filt)} fechados hoje.")
        st.info(" ".join(info_msg)) # Mais compacto
        st.subheader("Backlog Atual - Antiguidade")
        hora_txt = f" ({hora_atual_str})" if hora_atual_str else ""; st.caption(f"Ref: {data_atual_str}{hora_txt}")
        if not df_aging.empty:
            tot_ab=len(df_aging); tot_fec=len(df_enc_filt)
            c1,c2,c3,c4=st.columns([1,1.5,1.5,1]); c2.metric("Abertos",tot_ab); c3.metric("Fechados Dia",tot_fec)
            st.divider() # Usar divider em vez de markdown("---")
            # Cards Faixas
            counts=df_aging['Faixa de Antiguidade'].value_counts(); ordem=ordem_faixas # Reusa ordem_faixas
            cols_fx=st.columns(len(ordem))
            if 'faixa_selecionada' not in st.session_state or st.session_state.faixa_selecionada not in ordem: st.session_state.faixa_selecionada=ordem[0]
            for i,fx in enumerate(ordem):
                 qtd=counts.get(fx,0); fx_enc=quote(fx)
                 with cols_fx[i]: st.markdown(f'<a href="?faixa={fx_enc}&scroll=true" target="_self" class="metric-box"><span class="label">{fx}</span><span class="value">{qtd}</span></a>', unsafe_allow_html=True)
        else: st.warning("Nenhum chamado aberto.")
        # Comparativo
        st.markdown(f"<h5>Comparativo vs. {data_15dias_str if not df_15dias_filtrado.empty else '15 Dias (Indisp.)'}</h5>", unsafe_allow_html=True)
        if not df_15dias_filtrado.empty:
            df_comp=processar_dados_comparativos(df_aging,df_15dias_filtrado)
            if not df_comp.empty: st.dataframe(df_comp.set_index('Grupo').style.map(lambda v:'background-color:#ffcccc' if v>0 else ('background-color:#ccffcc' if v<0 else ''), subset=['Diferença']), use_container_width=True)
            else: st.info("Sem dados comuns para comparar.")
        else: st.warning("Dados de 15 dias indisponíveis.")
        st.divider()
        # Encerrados
        st.markdown(f"<h5>Chamados Encerrados ({data_atual_str})</h5>", unsafe_allow_html=True)
        if not closed_ids.size>0: st.info("Arquivo de encerrados não carregado.")
        elif not df_enc_filt.empty:
            cols_f=[c for c in ['ID do ticket','Descrição','Atribuir a um grupo','Dias em Aberto'] if c in df_enc_filt.columns]
            st.data_editor(df_enc_filt[cols_f],hide_index=True,disabled=True,use_container_width=True,key="ed_fechados")
        else: st.info("Nenhum encerrado hoje nos grupos analisados.")
        # Detalhar/Buscar Abertos
        if not df_aging.empty:
            st.divider()
            st.subheader("Detalhar e Buscar Abertos", anchor="detalhar-buscar-abertos") # Anchor mais curto
            st.caption('Marque Contato/Obs. (salva auto).') # Caption mais curto
            if 'scroll_to_details' not in st.session_state: st.session_state.scroll_to_details=False
            if needs_scroll or st.session_state.get('scroll_to_details',False):
                 js="""<script>setTimeout(()=>{const e=window.parent.document.getElementById('detalhar-buscar-abertos');e&&e.scrollIntoView({behavior:'smooth',block:'start'})},250)</script>"""; components.html(js,height=0)
                 st.session_state.scroll_to_details=False
            st.selectbox("Selecionar faixa:",options=ordem,key='faixa_selecionada')
            fx_sel=st.session_state.faixa_selecionada; df_filt=df_aging[df_aging['Faixa de Antiguidade']==fx_sel].copy()
            if not df_filt.empty:
                def hl_row(r):return ['background-color:#fff8c4']*len(r) if r.get('Contato',False) else ['']*len(r)
                df_filt['Contato']=df_filt['ID do ticket'].apply(lambda i: str(i) in st.session_state.contacted_tickets)
                df_filt['Observações']=df_filt['ID do ticket'].apply(lambda i: st.session_state.observations.get(str(i),''))
                st.session_state.last_filtered_df=df_filt.reset_index(drop=True)
                cols_rn={'Contato':'Contato','ID do ticket':'ID','Descrição':'Descrição','Atribuir a um grupo':'Grupo','Dias em Aberto':'Dias','Data de criação':'Criação','Observações':'Obs.'}
                cols_ex=[c for c in cols_rn if c in df_filt.columns]; cols_r=[cols_rn[c] for c in cols_ex]
                cols_ed=['Contato','Observações']; cols_dis=[cols_rn[c] for c in cols_ex if c not in cols_ed]
                st.data_editor(st.session_state.last_filtered_df.rename(columns=cols_rn)[cols_r].style.apply(hl_row,axis=1),use_container_width=True,hide_index=True,disabled=cols_dis,key='ticket_editor',on_change=sync_ticket_data)
            else: st.info(f"Sem chamados em '{fx_sel}'.")
            st.subheader("Buscar Abertos por Grupo")
            if 'Atribuir a um grupo' in df_aging.columns:
                 grupos=sorted(df_aging['Atribuir a um grupo'].dropna().unique())
                 if grupos:
                      g_sel=st.selectbox("Grupo:",options=grupos,key="busca_g")
                      if g_sel:
                           df_b=df_aging[df_aging['Atribuir a um grupo']==g_sel].copy()
                           dc_b=next((c for c in ['Data de criação','Data de Criacao'] if c in df_b.columns),None)
                           if dc_b: df_b[dc_b]=pd.to_datetime(df_b[dc_b]).dt.strftime('%d/%m/%Y')
                           st.write(f"{len(df_b)} para '{g_sel}':")
                           cols_b=['ID do ticket','Descrição','Dias em Aberto',dc_b]; cols_ex_b=[c for c in cols_b if c in df_b.columns and c]
                           st.data_editor(df_b[cols_ex_b],use_container_width=True,hide_index=True,disabled=True,key="ed_busca")
                 else: st.info("Nenhum grupo.")
            else: st.warning("Coluna de Grupo ausente.")

    with tab2:
        # ... (Código Tab 2 corrigido para TypeError) ...
        st.subheader("Visualização Gráfica") # Título mais genérico
        if not df_aging.empty:
            tot_ch = len(df_aging); _, c_tot, _ = st.columns([2,1.5,2]); c_tot.metric("Total Chamados", tot_ch)
            st.divider()
            # Cards (igual Tab 1)
            cnts_t2=df_aging['Faixa de Antiguidade'].value_counts(); ord_fx=ordem_faixas
            cols_t2=st.columns(len(ord_fx))
            for i,fx in enumerate(ord_fx): qtd=cnts_t2.get(fx,0); with cols_t2[i]: st.markdown(f'<div class="metric-box"><span class="label">{fx}</span><span class="value">{qtd}</span></div>',unsafe_allow_html=True)
            st.divider()
            st.subheader("Distribuição por Grupo")
            orient=st.radio("Orientação:",["Vertical","Horizontal"],index=0,horizontal=True,key="orient_t2")
            if 'Atribuir a um grupo' in df_aging.columns and 'Faixa de Antiguidade' in df_aging.columns:
                 cht_data=df_aging.groupby(['Atribuir a um grupo','Faixa de Antiguidade'],observed=False).size().reset_index(name='Quantidade')
                 grp_tots=cht_data.groupby('Atribuir a um grupo')['Quantidade'].sum().sort_values(ascending=False)
                 if not grp_tots.empty:
                      lbl_map={g:f"{g} ({t})" for g,t in grp_tots.items()}; cht_data['Grupo (Total)']=cht_data['Atribuir a um grupo'].map(lbl_map); sort_lbls=[lbl_map[g] for g in grp_tots.index]
                      def l_c(h,a=0.2): try: h=h.lstrip('#'); H,L,S=colorsys.rgb_to_hls(*[int(h[i:i+2],16)/255. for i in(0,2,4)]); r,g,b=colorsys.hls_to_rgb(H,L+(1-L)*a,S); return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}" except: return h
                      b="#375623"; pal=[l_c(b,v) for v in [0.85,0.7,0.55,0.4,0.2,0]]; cmap=dict(zip(ord_fx,pal))
                      cat_ord={'Faixa de Antiguidade':ord_fx,'Grupo (Total)':sort_lbls}
                      p_args=dict(data_frame=cht_data,color='Faixa de Antiguidade',title="Composição Idade/Grupo",category_orders=cat_ord,color_discrete_map=cmap,text_auto=True)
                      if orient=='Horizontal': fig=px.bar(**p_args,x='Quantidade',y='Grupo (Total)',orientation='h',labels={'Quantidade':'Qtd.','Grupo (Total)':''}); fig.update_layout(height=max(500,len(grp_tots)*30),yaxis={'categoryorder':'array','categoryarray':sort_lbls[::-1]})
                      else: fig=px.bar(**p_args,x='Grupo (Total)',y='Quantidade',labels={'Quantidade':'Qtd.','Grupo (Total)':'Grupo'}); fig.update_layout(height=600,xaxis_title=None,xaxis_tickangle=-45)
                      fig.update_traces(textangle=0,textfont_size=12); fig.update_layout(legend_title_text='Faixa'); st.plotly_chart(fig,use_container_width=True)
                 else: st.info("Nenhum grupo encontrado.")
            else: st.warning("Colunas necessárias ausentes.")
        else: st.warning("Dados de aging indisponíveis.")

    with tab3:
        # ... (Código Tab 3 - usa _repo) ...
        st.subheader("Evolução Semanal Backlog") 
        dias_evo=st.slider("Dias úteis:",7,30,7,key="slid_evo")
        df_evo=carregar_dados_evolucao(_repo,dias_para_analisar=dias_evo) 
        if not df_evo.empty:
            df_evo['Data']=pd.to_datetime(df_evo['Data']); df_evo_sem=df_evo[df_evo['Data'].dt.dayofweek<5].copy()
            if not df_evo_sem.empty:
                st.info("Snapshots dias úteis. Filtros ocultos/RH aplicados.")
                df_tot_d=df_evo_sem.groupby('Data')['Total Chamados'].sum().reset_index().sort_values('Data')
                df_tot_d['Eixo']=df_tot_d['Data'].dt.strftime('%d/%m'); ord_tot=df_tot_d['Eixo'].tolist()
                fig_t=px.area(df_tot_d,x='Eixo',y='Total Chamados',title='Total (Dias Úteis)',markers=True,labels={"Eixo":"Data","Total Chamados":"Total"},category_orders={'Eixo':ord_tot})
                fig_t.update_layout(height=400); st.plotly_chart(fig_t,use_container_width=True); st.divider()
                st.info("Clique legenda para filtrar.")
                df_evo_s=df_evo_sem.sort_values('Data'); df_evo_s['Eixo']=df_evo_s['Data'].dt.strftime('%d/%m')
                ord_g=df_evo_s['Eixo'].unique().tolist(); df_d=df_evo_s.rename(columns={'Atribuir a um grupo':'Grupo'})
                fig_g=px.line(df_d,x='Eixo',y='Total Chamados',color='Grupo',title='Por Grupo (Dias Úteis)',markers=True,labels={"Eixo":"Data","Total Chamados":"Nº Chamados"},category_orders={'Eixo':ord_g})
                fig_g.update_layout(height=600); st.plotly_chart(fig_g,use_container_width=True)
            else: st.info("Sem dados históricos suficientes (dias úteis).")
        else: st.info("Não foi possível carregar histórico.")

    with tab4:
        # ... (Código Tab 4 - usa _repo, cálculo relativo OK) ...
        st.subheader("Evolução Aging")
        st.info("Compara aging hoje vs. dias anteriores (idade calculada relativa ao dia do snapshot).")
        try:
            df_hist=carregar_evolucao_aging(_repo,dias_para_analisar=90) # Passa _repo
            ord_fx_scaff=ordem_faixas # Reusa
            hj_data,hj_counts=None,pd.DataFrame() 
            if 'df_aging' in locals() and not df_aging.empty and data_atual_str!='N/A':
                try:
                    hj_data=pd.to_datetime(datetime.strptime(data_atual_str,"%d/%m/%Y").date())
                    hj_raw=df_aging['Faixa de Antiguidade'].value_counts().reset_index(name='total')
                    df_scaff_hj=pd.DataFrame({'Faixa de Antiguidade':ord_fx_scaff})
                    hj_counts=pd.merge(df_scaff_hj,hj_raw,on='Faixa de Antiguidade',how='left').fillna(0)
                    hj_counts['total']=hj_counts['total'].astype(int); hj_counts['data']=hj_data 
                except ValueError: st.warning(f"Data atual inválida: '{data_atual_str}'."); hj_data=None 
            else: st.warning("Dados de 'hoje' (df_aging) indisponíveis.")
            
            if not df_hist.empty and not hj_counts.empty: df_comb=pd.concat([df_hist,hj_counts],ignore_index=True).drop_duplicates(subset=['data','Faixa de Antiguidade'],keep='last') 
            elif not df_hist.empty: df_comb=df_hist.copy(); st.warning("Dados 'hoje' indisponíveis.")
            elif not hj_counts.empty: df_comb=hj_counts.copy(); st.warning("Histórico indisponível.")
            else: st.error("Sem dados históricos ou de hoje para aging."); st.stop() 
            df_comb['data']=pd.to_datetime(df_comb['data']); df_comb=df_comb.sort_values(by=['data','Faixa de Antiguidade'])
            
            st.markdown("##### Comparativo")
            p_opts={"Ontem":1,"7d":7,"15d":15,"30d":30}; p_sel=st.radio("Comparar Hoje com:",p_opts.keys(),horizontal=True,key="rad_comp")
            dt_comp_f,df_comp_d,dt_comp_s=None,pd.DataFrame(),"N/A"
            if hj_data:
                t_dt=hj_data.date()-timedelta(days=p_opts[p_sel])
                dt_comp_enc,_=find_closest_snapshot_before(_repo,hj_data.date(),t_dt) # Passa _repo
                if dt_comp_enc:
                    dt_comp_f=pd.to_datetime(dt_comp_enc); dt_comp_s=dt_comp_f.strftime('%d/%m')
                    df_comp_d=df_comb[df_comb['data']==dt_comp_f].copy() 
                    if df_comp_d.empty: dt_comp_f=None 
            
            cols_map={i:c for i,c in enumerate(st.columns(3)+st.columns(3))}
            for i,fx in enumerate(ord_fx_scaff):
                with cols_map[i]:
                    v_hj,d_txt,d_cls='N/A',"N/A","delta-neutral"
                    if not hj_counts.empty:
                        v_hj_s=hj_counts.loc[hj_counts['Faixa de Antiguidade']==fx,'total']
                        if not v_hj_s.empty:
                            v_hj=int(v_hj_s.iloc[0])
                            if dt_comp_f and not df_comp_d.empty:
                                v_cmp_s=df_comp_d.loc[df_comp_d['Faixa de Antiguidade']==fx,'total']
                                v_cmp=int(v_cmp_s.iloc[0]) if not v_cmp_s.empty else 0
                                d_a=v_hj-v_cmp; d_p=(d_a/v_cmp) if v_cmp>0 else 0
                                d_txt,d_cls=formatar_delta_card(d_a,d_p,v_cmp,dt_comp_s)
                            elif hj_data: d_txt="Sem dados para comparar"
                        else: v_hj=0; d_txt="N/A"
                    elif not hj_data: d_txt="Dados hoje indisponíveis"
                    st.markdown(f'<div class="metric-box"><span class="label">{fx}</span><span class="value">{v_hj}</span><span class="delta {d_cls}">{d_txt}</span></div>',unsafe_allow_html=True)

            st.divider()
            st.markdown(f"##### Gráfico Evolução (7 dias)")
            hj_f_g=date.today(); dt_i_f_g=hj_f_g-timedelta(days=6) 
            df_f_g=df_comb[df_comb['data'].dt.date>=dt_i_f_g].copy()
            if df_f_g.empty: st.warning("Sem dados aging 7 dias.")
            else:
                df_g=df_f_g.sort_values(by='data'); df_g['Eixo']=df_g['data'].dt.strftime('%d/%m'); ord_dt_g=df_g['Eixo'].unique().tolist() 
                def l_c(h,a=0.2): try: h=h.lstrip('#'); H,L,S=colorsys.rgb_to_hls(*[int(h[i:i+2],16)/255. for i in(0,2,4)]); r,g,b=colorsys.hls_to_rgb(H,L+(1-L)*a,S); return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}" except: return h
                b="#375623"; pal=[l_c(b,v) for v in [0.85,0.7,0.55,0.4,0.2,0]]; cmap=dict(zip(ord_fx_scaff,pal))
                t_g=st.radio("Tipo:",("Linha","Área"),index=1,horizontal=True,key="rad_tipo_g") 
                p_f=px.line if t_g=="Linha" else px.area; t_suf="(Comparativo)" if t_g=="Linha" else "(Composição)"
                fig=p_f(df_g,x='Eixo',y='total',color='Faixa de Antiguidade',title=f'Evolução Aging {t_suf} - 7 dias',markers=True,labels={"Eixo":"Data","total":"Chamados","Faixa de Antiguidade":"Faixa"},category_orders={'Eixo':ord_dt_g,'Faixa de Antiguidade':ord_fx_scaff},color_discrete_map=cmap)
                fig.update_layout(height=500,legend_title_text='Faixa'); st.plotly_chart(fig,use_container_width=True)
        except Exception as e: st.error(f"Erro Tab Evolução Aging: {e}"); st.exception(e) 

except Exception as e:
    st.error(f"Erro GERAL: {e}") 
    import traceback
    st.exception(e) 
    
# --- Rodapé ---
st.markdown("---")
# Atualiza versão no rodapé
st.markdown(""" 
<p style='text-align: center; color: #666; font-size: 0.9em; margin-bottom: 0;'>v0.9.37 | Em desenvolvimento.</p>
<p style='text-align: center; color: #666; font-size: 0.9em; margin-top: 0;'>Desenvolvido por Leonir Scatolin Junior</p>
""", unsafe_allow_html=True)
