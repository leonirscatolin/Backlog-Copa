import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import base64
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from io import StringIO, BytesIO
import streamlit.components.v1 as components
from PIL import Image
from urllib.parse import quote
import json
import colorsys
import re
import os

# --- CONFIGURAÇÕES E CONSTANTES ---
GRUPOS_EXCLUSAO_PERMANENTE_REGEX = r'RH|Aprovadores GGM|RDM'
GRUPOS_EXCLUSAO_PERMANENTE_TEXTO = "'RH', 'Aprovadores GGM' ou 'RDM'"

GRUPOS_DE_AVISO_REGEX = r'Service Desk \(L1\)|LIQ-SUTEL'
GRUPOS_DE_AVISO_TEXTO = "'Service Desk (L1)' ou 'LIQ-SUTEL'"

GRUPOS_EXCLUSAO_TOTAL_REGEX = f"{GRUPOS_EXCLUSAO_PERMANENTE_REGEX}|{GRUPOS_DE_AVISO_REGEX}"

DATA_DIR = "data/"
STATE_FILE_CONTACTS = "contacted_tickets.json"
STATE_FILE_OBSERVATIONS = "ticket_observations.json"
STATE_FILE_REF_DATES = "datas_referencia.txt"
STATE_FILE_MASTER_CLOSED_CSV = f"{DATA_DIR}historico_fechados_master.csv"
STATE_FILE_PREV_CLOSED = "previous_closed_ids.json"

# --- SETUP DA PÁGINA ---
st.set_page_config(
    layout="wide",
    page_title="Backlog Copa Energia + Belago",
    page_icon=f"{DATA_DIR}minilogo.png" if os.path.exists(f"{DATA_DIR}minilogo.png") else None,
    initial_sidebar_state="collapsed"
)

# --- CSS PERSONALIZADO ---
st.html("""
<style>
#GithubIcon { visibility: hidden; }
.metric-box {
    border: 1px solid #CCCCCC;
    padding: 10px;
    border-radius: 5px;
    text-align: center;
    box-shadow: 0px 2px 4px rgba(0,0,0,0.1);
    margin-bottom: 10px;
    height: 120px; 
    display: flex; 
    flex-direction: column; 
    justify-content: center; 
    background-color: white;
    transition: transform 0.2s;
}
a.metric-box { 
    display: block;
    color: inherit;
    text-decoration: none !important;
}
a.metric-box:hover {
    background-color: #f0f2f6;
    text-decoration: none !important;
    transform: scale(1.02);
    border-color: #375623;
}
.metric-box span { 
    display: block;
    width: 100%;
    text-decoration: none !important;
}
.metric-box .label { 
    font-size: 1em;
    color: #666666;
    margin-bottom: 5px; 
}
.metric-box .value { 
    font-size: 2.5em;
    font-weight: bold;
    color: #375623; 
}
.metric-box .delta { 
    font-size: 0.9em;
    margin-top: 5px; 
}
.delta-positive { color: #d9534f; } 
.delta-negative { color: #5cb85c; } 
.delta-neutral { color: #666666; } 

[data-testid="stSidebar"] [data-testid="stButton"] button {
    background-color: #f28801;
    color: white;
    border: 1px solid #f28801;
}
[data-testid="stSidebar"] [data-testid="stButton"] button:hover {
    background-color: #d97900; 
    color: white;
    border-color: #d97900;
}
</style>
""")

# --- FUNÇÕES UTILITÁRIAS ---

def get_file_mtime(file_path):
    if os.path.exists(file_path):
        return os.path.getmtime(file_path)
    return 0

def save_local_file(file_path, file_content, is_binary=False):
    try:
        directory = os.path.dirname(file_path)
        if directory: 
            os.makedirs(directory, exist_ok=True)
            
        mode = 'wb' if is_binary else 'w'
        encoding = None if is_binary else 'utf-8'
        
        with open(file_path, mode, encoding=encoding) as f:
            f.write(file_content)
            
        if file_path not in [STATE_FILE_CONTACTS, STATE_FILE_OBSERVATIONS, STATE_FILE_REF_DATES, STATE_FILE_MASTER_CLOSED_CSV, STATE_FILE_PREV_CLOSED]:
            st.sidebar.info(f"Arquivo '{file_path}' salvo localmente.")
            
    except Exception as e:
        st.sidebar.error(f"Falha ao salvar '{file_path}' localmente: {e}")
        raise

@st.cache_data
def read_local_csv(file_path, file_mtime):
    if not os.path.exists(file_path):
        return pd.DataFrame() 
    
    separators = [';', ',']
    encodings = ['utf-8', 'latin1']
    
    for sep in separators:
        for enc in encodings:
            try:
                df = pd.read_csv(file_path, sep=sep, encoding=enc,
                                 dtype={'ID do ticket': str, 'ID do Ticket': str, 'ID': str}, 
                                 low_memory=False, on_bad_lines='warn')
                
                if df.shape[1] > 1:
                    df.columns = df.columns.str.strip()
                    df = df.loc[:, ~df.columns.duplicated()]
                    df.dropna(how='all', inplace=True)
                    return df
            except:
                continue
                
    st.error(f"Não foi possível ler o arquivo '{file_path}'. Verifique se é um CSV válido.")
    return pd.DataFrame()

@st.cache_data
def read_local_text_file(file_path):
    if not os.path.exists(file_path):
        return {} 

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        dates = {}
        for line in content.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                dates[key.strip()] = value.strip()
        return dates
    except Exception as e:
        return {}

@st.cache_data
def read_local_json_file(file_path, default_return_type='dict'): 
    default_return = (default_return_type == 'dict' and {} or [])
    if not os.path.exists(file_path):
        return default_return 
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            return json.loads(content) if content else default_return
    except Exception:
        return default_return

def process_uploaded_file(uploaded_file):
    if uploaded_file is None:
        return None
    try:
        dtype_spec = {'ID do ticket': str, 'ID do Ticket': str, 'ID': str}
        if uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file, dtype=dtype_spec)
        else:
            try:
                content = uploaded_file.getvalue().decode('utf-8')
            except UnicodeDecodeError:
                content = uploaded_file.getvalue().decode('latin1')
            
            try:
                df = pd.read_csv(StringIO(content), sep=None, engine='python', dtype=dtype_spec)
            except:
                if ';' in content.split('\n')[0]:
                    df = pd.read_csv(StringIO(content), sep=';', dtype=dtype_spec)
                else:
                    df = pd.read_csv(StringIO(content), sep=',', dtype=dtype_spec)

        df.columns = df.columns.str.strip()
        df.dropna(how='all', inplace=True)

        output = StringIO()
        df.to_csv(output, index=False, sep=';', encoding='utf-8')
        return output.getvalue().encode('utf-8') 
    except Exception as e:
        st.sidebar.error(f"Erro ao ler o arquivo {uploaded_file.name}: {e}")
        return None

def processar_dados_comparativos(df_atual, df_15dias):
    contagem_atual = df_atual.groupby('Atribuir a um grupo').size().reset_index(name='Atual')
    contagem_15dias = df_15dias.groupby('Atribuir a um grupo').size().reset_index(name='15 Dias Atrás')
    df_comparativo = pd.merge(contagem_atual, contagem_15dias, on='Atribuir a um grupo', how='outer').fillna(0)
    df_comparativo['Diferença'] = df_comparativo['Atual'] - df_comparativo['15 Dias Atrás']
    df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']] = df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']].astype(int)
    return df_comparativo

@st.cache_data
def categorizar_idade_vetorizado(dias_series):
    condicoes = [
        dias_series >= 30, (dias_series >= 21) & (dias_series <= 29),
        (dias_series >= 11) & (dias_series <= 20), (dias_series >= 6) & (dias_series <= 10),
        (dias_series >= 3) & (dias_series <= 5), (dias_series >= 0) & (dias_series <= 2)
    ]
    opcoes = ["30+ dias", "21-29 dias", "11-20 dias", "6-10 dias", "3-5 dias", "0-2 dias"]
    return np.select(condicoes, opcoes, default="Erro de Categoria")

@st.cache_data
def analisar_aging(_df_atual, reference_date=None):
    df = _df_atual.copy()
    date_col_name = None
    possible_date_cols = ['Data de criação', 'Data de criaÃ§Ã£o', 'Data de Criacao', 'Created', 'Aberto em', 'Criado em', 'Criação']
    for col in possible_date_cols:
        if col in df.columns:
            date_col_name = col
            break
            
    if not date_col_name:
        return pd.DataFrame()
    
    df['temp_date'] = pd.to_datetime(df[date_col_name], dayfirst=True, errors='coerce')
    mask_nat = df['temp_date'].isna()
    if mask_nat.any():
        df.loc[mask_nat, 'temp_date'] = pd.to_datetime(df.loc[mask_nat, date_col_name], errors='coerce')

    df[date_col_name] = df['temp_date']
    df.drop(columns=['temp_date'], inplace=True)
    
    df = df.dropna(subset=[date_col_name])
    
    if reference_date:
        data_referencia = pd.to_datetime(reference_date).normalize()
    else:
        data_referencia = pd.to_datetime('today').normalize()
        
    data_criacao_normalizada = df[date_col_name].dt.normalize()
    
    dias_calculados = (data_referencia - data_criacao_normalizada).dt.days - 1
    
    df['Dias em Aberto'] = dias_calculados.clip(lower=0)
    df['Faixa de Antiguidade'] = categorizar_idade_vetorizado(df['Dias em Aberto'])
    return df

def get_status(row):
    diferenca = row['Diferença']
    if diferenca > 0: return "Alta Demanda"
    elif diferenca == 0: return "Estável / Atenção"
    else: return "Redução de Backlog"

def get_image_as_base64(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode()
    except Exception:
        return None

def lighten_color(hex_color, amount=0.2):
    try:
        hex_color = hex_color.lstrip('#')
        h, l, s = colorsys.rgb_to_hls(*[int(hex_color[i:i+2], 16)/255.0 for i in (0, 2, 4)])
        new_l = l + (1 - l) * amount
        r, g, b = colorsys.hls_to_rgb(h, new_l, s)
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
    except Exception: return hex_color

def normalize_ids(series):
    if series.empty:
        return series
    return series.astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

def sync_ticket_data():
    editor_key = f'ticket_editor_{st.session_state.editor_key_counter}'
    
    if editor_key not in st.session_state or not st.session_state[editor_key].get('edited_rows'):
        return
        
    edited_rows = st.session_state[editor_key]['edited_rows']
    contact_changed = False
    observation_changed = False
    
    if 'last_filtered_df' not in st.session_state:
        return

    df_ref = st.session_state.last_filtered_df

    for row_index, changes in edited_rows.items():
        try:
            ticket_id = str(df_ref.iloc[row_index]['ID do ticket'])
            
            if 'Contato' in changes:
                current_contact_status = ticket_id in st.session_state.contacted_tickets
                new_contact_status = changes['Contato']
                if current_contact_status != new_contact_status:
                    if new_contact_status: st.session_state.contacted_tickets.add(ticket_id)
                    else: st.session_state.contacted_tickets.discard(ticket_id)
                    contact_changed = True
            
            if 'Observações' in changes:
                current_observation = st.session_state.observations.get(ticket_id, '')
                new_observation = changes['Observações']
                if current_observation != new_observation:
                    st.session_state.observations[ticket_id] = new_observation
                    observation_changed = True
        except IndexError:
            continue
        except KeyError:
            continue

    if contact_changed or observation_changed:
        try:
            if contact_changed:
                data_to_save = list(st.session_state.contacted_tickets)
                json_content = json.dumps(data_to_save, indent=4)
                save_local_file(STATE_FILE_CONTACTS, json_content)
            if observation_changed:
                json_content = json.dumps(st.session_state.observations, indent=4, ensure_ascii=False)
                save_local_file(STATE_FILE_OBSERVATIONS, json_content)
            
            st.toast("Alterações salvas com sucesso!")
            
        except Exception as e:
            st.error(f"Erro ao salvar alterações: {e}")
            st.session_state.scroll_to_details = True
            return
    
    st.session_state.editor_key_counter += 1
    st.session_state.scroll_to_details = True

@st.cache_data
def carregar_dados_evolucao(dias_para_analisar, df_historico_fechados): 
    try:
        snapshot_dir = f"{DATA_DIR}snapshots"
        try:
            local_files = [os.path.join(snapshot_dir, f) for f in os.listdir(snapshot_dir) if f.endswith('.csv')]
            if not local_files: raise FileNotFoundError
        except FileNotFoundError: return pd.DataFrame() 

        df_evolucao_list = []
        end_date = date.today()
        start_date = end_date - timedelta(days=max(dias_para_analisar, 10))

        processed_dates = []
        for file_name in local_files:
            if "backlog_" in file_name:
                try:
                    date_str = file_name.split("backlog_")[1].replace(".csv", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if start_date <= file_date <= end_date:
                        processed_dates.append((file_date, file_name))
                except: continue

        processed_dates.sort(key=lambda x: x[0], reverse=True)
        files_to_process = [f[1] for f in processed_dates[:dias_para_analisar]]

        df_hist = df_historico_fechados.copy()
        id_col_hist = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_hist.columns), None)
        
        if id_col_hist and not df_hist.empty:
            df_hist['Data de Fechamento_dt'] = pd.to_datetime(df_hist['Data de Fechamento'], dayfirst=True, errors='coerce').dt.normalize()
            df_hist = df_hist.dropna(subset=['Data de Fechamento_dt', id_col_hist])
            df_hist['Ticket ID'] = normalize_ids(df_hist[id_col_hist])
            df_hist = df_hist[['Ticket ID', 'Data de Fechamento_dt']]
        else:
            df_hist = pd.DataFrame()

        for file_name in files_to_process:
                try:
                    date_str = file_name.split("backlog_")[1].replace(".csv", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    
                    df_snapshot = read_local_csv(file_name, get_file_mtime(file_name)) 
                    
                    if not df_snapshot.empty and 'Atribuir a um grupo' in df_snapshot.columns:
                        
                        df_snapshot_filtrado = df_snapshot[~df_snapshot['Atribuir a um grupo'].str.contains(GRUPOS_EXCLUSAO_TOTAL_REGEX, case=False, na=False, regex=True)].copy()
                        
                        snap_id_col = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_snapshot_filtrado.columns), None)

                        if snap_id_col and not df_hist.empty:
                            df_snapshot_filtrado['Clean ID'] = normalize_ids(df_snapshot_filtrado[snap_id_col])
                            closed_up_to_date = df_hist[df_hist['Data de Fechamento_dt'].dt.date <= file_date]['Ticket ID'].unique()
                            df_snapshot_filtrado = df_snapshot_filtrado[
                                ~df_snapshot_filtrado['Clean ID'].isin(closed_up_to_date)
                            ]
                            df_snapshot_filtrado = df_snapshot_filtrado.drop(columns=['Clean ID'])

                        contagem_diaria = df_snapshot_filtrado.groupby('Atribuir a um grupo').size().reset_index(name='Total Chamados')
                        contagem_diaria['Data'] = pd.to_datetime(file_date)
                        df_evolucao_list.append(contagem_diaria)
                except Exception: continue

        if not df_evolucao_list: return pd.DataFrame()
        df_consolidado = pd.concat(df_evolucao_list, ignore_index=True)
        return df_consolidado.sort_values(by=['Data', 'Atribuir a um grupo'])
    except Exception as e:
        st.error(f"Erro ao carregar evolução: {e}")
        return pd.DataFrame()

@st.cache_data
def find_closest_snapshot_before(current_report_date, target_date):
    try:
        snapshot_dir = f"{DATA_DIR}snapshots"
        try:
            local_files = [os.path.join(snapshot_dir, f) for f in os.listdir(snapshot_dir) if f.endswith('.csv')]
            if not local_files: raise FileNotFoundError
        except FileNotFoundError: return None, None 

        snapshots = []
        search_start_date = target_date - timedelta(days=10)

        for file_path in local_files:
            match = re.search(r"backlog_(\d{4}-\d{2}-\d{2})\.csv", file_
