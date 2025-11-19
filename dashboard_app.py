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
# 'RDM' filtra qualquer grupo que contenha essa sigla no nome
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
    
    # Tenta ler com diferentes separadores e encodings
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
    possible_date_cols = ['Data de criação', 'Data de criaÃ§Ã£o', 'Data de Criacao', 'Created', 'Aberto em']
    for col in possible_date_cols:
        if col in df.columns:
            date_col_name = col
            break
            
    if not date_col_name:
        return pd.DataFrame()
    
    df['temp_date'] = pd.to_datetime(df[date_col_name], errors='coerce')
    mask_nat = df['temp_date'].isna()
    if mask_nat.any():
        df.loc[mask_nat, 'temp_date'] = pd.to_datetime(df.loc[mask_nat, date_col_name], dayfirst=True, errors='coerce')
    df[date_col_name] = df['temp_date']
    df.drop(columns=['temp_date'], inplace=True)
    
    linhas_sem_data = df[df[date_col_name].isna()]
    if not linhas_sem_data.empty:
        pass

    df = df.dropna(subset=[date_col_name])
    
    if reference_date:
        data_referencia = pd.to_datetime(reference_date).normalize()
    else:
        data_referencia = pd.to_datetime('today').normalize()
        
    data_criacao_normalizada = df[date_col_name].dt.normalize()
    
    # Subtrair 1 dia para alinhar com a lógica do Excel (D-1)
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
    """Limpa e padroniza IDs para garantir cruzamento correto."""
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
            match = re.search(r"backlog_(\d{4}-\d{2}-\d{2})\.csv", file_path.split('/')[-1])
            if match:
                snapshot_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
                if search_start_date <= snapshot_date <= target_date:
                    snapshots.append((snapshot_date, file_path))

        if not snapshots: return None, None
        snapshots.sort(key=lambda x: x[0], reverse=True)
        return snapshots[0]
    except Exception: return None, None

@st.cache_data
def carregar_evolucao_aging(dias_para_analisar=90): 
    try:
        snapshot_dir = f"{DATA_DIR}snapshots"
        try:
            local_files = [os.path.join(snapshot_dir, f) for f in os.listdir(snapshot_dir) if f.endswith('.csv')]
            if not local_files: raise FileNotFoundError
        except FileNotFoundError: return pd.DataFrame() 

        lista_historico = []
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=max(dias_para_analisar, 60))

        processed_files = []
        for file_name in local_files:
            if "backlog_" in file_name:
                try:
                    date_str = file_name.split("backlog_")[1].replace(".csv", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if start_date <= file_date <= end_date:
                        processed_files.append((file_date, file_name))
                except: continue

        processed_files.sort(key=lambda x: x[0])

        for file_date, file_name in processed_files:
            try:
                df_snapshot = read_local_csv(file_name, get_file_mtime(file_name)) 
                if df_snapshot.empty: continue

                df_filtrado = df_snapshot[~df_snapshot['Atribuir a um grupo'].str.contains(GRUPOS_EXCLUSAO_TOTAL_REGEX, case=False, na=False, regex=True)]
                df_final = df_filtrado.copy() 

                date_col_name = next((col for col in ['Data de criação', 'Data de criaÃ§Ã£o', 'Data de Criacao'] if col in df_final.columns), None)
                if not date_col_name: continue

                df_final['temp_date'] = pd.to_datetime(df_final[date_col_name], errors='coerce')
                mask_nat = df_final['temp_date'].isna()
                if mask_nat.any():
                    df_final.loc[mask_nat, 'temp_date'] = pd.to_datetime(df_final.loc[mask_nat, date_col_name], dayfirst=True, errors='coerce')
                df_final[date_col_name] = df_final['temp_date']
                
                df_final = df_final.dropna(subset=[date_col_name])

                snapshot_date_dt = pd.to_datetime(file_date)
                data_criacao_normalizada = df_final[date_col_name].dt.normalize()
                
                # Subtrair 1 dia para alinhar com a lógica do Excel (D-1)
                dias_calculados = (snapshot_date_dt - data_criacao_normalizada).dt.days - 1
                dias_em_aberto_corrigido = (dias_calculados).clip(lower=0)

                faixas_antiguidade = categorizar_idade_vetorizado(dias_em_aberto_corrigido)
                contagem_faixas = pd.Series(faixas_antiguidade).value_counts().reset_index()
                contagem_faixas.columns = ['Faixa de Antiguidade', 'total']

                ordem_faixas_scaffold = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
                df_todas_faixas = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas_scaffold})

                contagem_completa = pd.merge(df_todas_faixas, contagem_faixas, on='Faixa de Antiguidade', how='left').fillna(0)
                contagem_completa['total'] = contagem_completa['total'].astype(int)
                contagem_completa['data'] = snapshot_date_dt
                lista_historico.append(contagem_completa)
            except Exception: continue

        if not lista_historico: return pd.DataFrame()
        return pd.concat(lista_historico, ignore_index=True)
    except Exception as e:
        st.error(f"Erro ao carregar evolução de aging: {e}")
        return pd.DataFrame()

def formatar_delta_card(delta_abs, delta_perc, valor_comparacao, data_comparacao_str):
    delta_abs = int(delta_abs)
    if valor_comparacao > 0:
        delta_perc_str = f"{delta_perc * 100:.1f}%"
        delta_text = f"{delta_abs:+} ({delta_perc_str}) vs. {data_comparacao_str}"
    elif valor_comparacao == 0 and delta_abs > 0:
        delta_text = f"+{delta_abs} (Novo) vs. {data_comparacao_str}"
    elif valor_comparacao == 0 and delta_abs < 0:
        delta_text = f"{delta_abs} vs. {data_comparacao_str}"
    else:
        delta_text = f"{delta_abs} (0.0%) vs. {data_comparacao_str}"

    if delta_abs > 0: delta_class = "delta-positive"
    elif delta_abs < 0: delta_class = "delta-negative"
    else: delta_class = "delta-neutral"

    return delta_text, delta_class

logo_copa_b64 = get_image_as_base64(f"{DATA_DIR}logo_sidebar.png") 
logo_belago_b64 = get_image_as_base64(f"{DATA_DIR}logo_belago.png") 
if logo_copa_b64 and logo_belago_b64:
    st.markdown(f"""<div style="display: flex; justify-content: space-between; align-items: center;"><img src="data:image/png;base64,{logo_copa_b64}" width="150"><h1 style='text-align: center; margin: 0;'>Backlog Copa Energia + Belago</h1><img src="data:image/png;base64,{logo_belago_b64}" width="150"></div>""", unsafe_allow_html=True)
else:
    st.error("Arquivos de logo não encontrados.")

st.sidebar.header("Área do Administrador")
password = st.sidebar.text_input("Senha para atualizar dados:", type="password")
is_admin = password == st.secrets.get("ADMIN_PASSWORD", "") 

if is_admin:
    st.sidebar.success("Acesso de administrador liberado.")
    st.sidebar.subheader("Atualização Completa")
    uploaded_file_atual = st.sidebar.file_uploader("1. Backlog ATUAL", type=["csv", "xlsx"], key="uploader_atual")
    uploaded_file_15dias = st.sidebar.file_uploader("2. Backlog de 15 DIAS ATRÁS", type=["csv", "xlsx"], key="uploader_15dias")
    if st.sidebar.button("Salvar Novos Dados no Site"):
        if uploaded_file_atual and uploaded_file_15dias:
            with st.spinner("Processando e salvando atualização completa..."):
                if os.path.exists(STATE_FILE_MASTER_CLOSED_CSV):
                    try: os.remove(STATE_FILE_MASTER_CLOSED_CSV)
                    except Exception: pass
                if os.path.exists(STATE_FILE_PREV_CLOSED):
                    try: os.remove(STATE_FILE_PREV_CLOSED)
                    except Exception: pass

                now_sao_paulo = datetime.now(ZoneInfo('America/Sao_Paulo'))
                
                content_atual_raw = process_uploaded_file(uploaded_file_atual)
                content_15dias = process_uploaded_file(uploaded_file_15dias)
                
                if content_atual_raw is not None and content_15dias is not None:
                    try:
                        df_novo_atual_raw = pd.read_csv(BytesIO(content_atual_raw), sep=';', dtype={'ID do ticket': str, 'ID do Ticket': str, 'ID': str})
                        
                        df_hist_fechados = read_local_csv(STATE_FILE_MASTER_CLOSED_CSV, get_file_mtime(STATE_FILE_MASTER_CLOSED_CSV))
                        
                        all_closed_ids_historico = set()
                        id_col_hist = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_hist_fechados.columns), None)
                        
                        if id_col_hist and not df_hist_fechados.empty:
                            all_closed_ids_historico = set(normalize_ids(df_hist_fechados[id_col_hist]).unique())

                        id_col_atual = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_novo_atual_raw.columns), None)
                        
                        df_novo_atual_filtrado = df_novo_atual_raw 
                        
                        if id_col_atual and all_closed_ids_historico: 
                            df_novo_atual_raw[id_col_atual] = normalize_ids(df_novo_atual_raw[id_col_atual])
                            df_novo_atual_filtrado = df_novo_atual_raw[~df_novo_atual_raw[id_col_atual].isin(all_closed_ids_historico)]
                            st.sidebar.info(f"{len(df_novo_atual_raw) - len(df_novo_atual_filtrado)} chamados fechados (do histórico) foram removidos do novo arquivo 'Atual'.")
                        
                        output_atual_filtrado = StringIO()
                        df_novo_atual_filtrado.to_csv(output_atual_filtrado, index=False, sep=';', encoding='utf-8')
                        content_atual = output_atual_filtrado.getvalue().encode('utf-8') 
                        
                        save_local_file(f"{DATA_DIR}dados_atuais.csv", content_atual, is_binary=True)
                        save_local_file(f"{DATA_DIR}dados_15_dias.csv", content_15dias, is_binary=True)
                        
                        today_str = now_sao_paulo.strftime('%Y-%m-%d')
                        snapshot_path = f"{DATA_DIR}snapshots/backlog_{today_str}.csv"
                        save_local_file(snapshot_path, content_atual, is_binary=True)
                        
                        data_do_upload = now_sao_paulo.date()
                        data_arquivo_15dias = data_do_upload - timedelta(days=15)
                        date_15_str = data_arquivo_15dias.strftime('%Y-%m-%d')
                        
                        snapshot_path_15 = f"{DATA_DIR}snapshots/backlog_{date_15_str}.csv"
                        save_local_file(snapshot_path_15, content_15dias, is_binary=True)
                        
                        hora_atualizacao = now_sao_paulo.strftime('%H:%M')
                        datas_referencia_content = (f"data_atual:{data_do_upload.strftime('%d/%m/%Y')}\n"
                                                    f"data_15dias:{data_arquivo_15dias.strftime('%d/%m/%Y')}\n"
                                                    f"hora_atualizacao:{hora_atualizacao}")
                        save_local_file(STATE_FILE_REF_DATES, datas_referencia_content)
                        
                        st.sidebar.success("Arquivos salvos e histórico zerado! Recarregando...")
                        st.cache_data.clear()
                        st.rerun() 
                    except Exception as e:
                        st.sidebar.error(f"Erro durante a atualização completa: {e}")

        else:
            st.sidebar.warning("Para a atualização completa, carregue os arquivos ATUAL e de 15 DIAS.")
            
    st.sidebar.markdown("---")
    st.sidebar.subheader("Atualização Rápida (Manual)")
    uploaded_file_fechados = st.sidebar.file_uploader("Apenas Chamados FECHADOS no dia", type=["csv", "xlsx"], key="uploader_fechados")
    if st.sidebar.button("Salvar Apenas Chamados Fechados"):
        if uploaded_file_fechados:
            with st.spinner("Salvando arquivo de fechados e atualizando snapshot diário..."):
                now_sao_paulo = datetime.now(ZoneInfo('America/Sao_Paulo'))
                
                content_fechados = process_uploaded_file(uploaded_file_fechados)
                if content_fechados is None:
                    st.sidebar.error("Falha ao processar o arquivo de fechados.")
                    st.stop() 

                try:
                    # --- LÓGICA DE MENSAGEM DE IMPACTO (MANTIDA PARA TOAST, AGORA TAMBÉM NA ABA 1) ---
                    df_backlog_check = read_local_csv(f"{DATA_DIR}dados_atuais.csv", get_file_mtime(f"{DATA_DIR}dados_atuais.csv"))
                    
                    df_fechados_novo_check = pd.read_csv(BytesIO(content_fechados), sep=';', dtype={'ID do ticket': str, 'ID do Ticket': str, 'ID': str})
                    
                    if not df_backlog_check.empty:
                        id_col_bk = next((c for c in ['ID do ticket', 'ID do Ticket', 'ID'] if c in df_backlog_check.columns), None)
                        id_col_fc = next((c for c in ['ID do ticket', 'ID do Ticket', 'ID'] if c in df_fechados_novo_check.columns), None)
                        
                        # Tenta identificar coluna de data para filtrar
                        col_data_fechamento_check = next((c for c in ['Data de Fechamento', 'Data de Resolução'] if c in df_fechados_novo_check.columns), None)
                        
                        if id_col_bk and id_col_fc:
                            # Prepara dataframe de fechados filtrado por HOJE
                            if col_data_fechamento_check:
                                df_fechados_novo_check['dt_temp_check'] = pd.to_datetime(df_fechados_novo_check[col_data_fechamento_check], dayfirst=True, errors='coerce')
                                df_fechados_hoje_check = df_fechados_novo_check[df_fechados_novo_check['dt_temp_check'].dt.date == now_sao_paulo.date()]
                            else:
                                # Se não achar coluna de data, assume que tudo é de hoje (comportamento padrão, mas arriscado)
                                df_fechados_hoje_check = df_fechados_novo_check

                            ids_bk = set(normalize_ids(df_backlog_check[id_col_bk]))
                            ids_fc_hoje = set(normalize_ids(df_fechados_hoje_check[id_col_fc]))
                            
                            total_lidos_hoje = len(ids_fc_hoje)
                            total_abatidos = len(ids_bk.intersection(ids_fc_hoje))
                            
                            st.toast(f"Processado! {total_lidos_hoje} chamados de HOJE lidos. {total_abatidos} impactaram o backlog.")
                    # ---------------------------------------

                    save_local_file(f"{DATA_DIR}dados_fechados.csv", content_fechados, is_binary=True)

                    datas_existentes = read_local_text_file(STATE_FILE_REF_DATES)
                    data_atual_existente = datas_existentes.get('data_atual', 'N/A')
                    data_15dias_existente = datas_existentes.get('data_15dias', 'N/A')
                    hora_atualizacao_nova = now_sao_paulo.strftime('%H:%M')

                    datas_referencia_content_novo = (f"data_atual:{data_atual_existente}\n"
                                                       f"data_15dias:{data_15dias_existente}\n"
                                                       f"hora_atualizacao:{hora_atualizacao_nova}")
                    save_local_file(STATE_FILE_REF_DATES, datas_referencia_content_novo)
                    
                    df_fechados_novo_upload = pd.read_csv(BytesIO(content_fechados), delimiter=';', dtype={'ID do ticket': str, 'ID do Ticket': str, 'ID': str})
                    
                    id_col_upload = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_fechados_novo_upload.columns), "ID do Ticket")
                    if id_col_upload not in df_fechados_novo_upload.columns:
                        raise Exception("Coluna de ID não encontrada no arquivo de fechados.")
                    
                    col_fechamento_upload = "Data de Fechamento" 
                    analista_col_name_origem = "Analista atribuído"
                    
                    df_fechados_novo_upload[id_col_upload] = normalize_ids(df_fechados_novo_upload[id_col_upload])
                    
                    if col_fechamento_upload in df_fechados_novo_upload.columns:
                        st.sidebar.info("Usando 'Data de Fechamento' do arquivo de upload.")
                        df_fechados_novo_upload['Data de Fechamento_dt'] = pd.to_datetime(df_fechados_novo_upload[col_fechamento_upload], errors='coerce')
                    else:
                        st.sidebar.warning(f"Coluna '{col_fechamento_upload}' não encontrada. Usando data de referência: {data_atual_existente}")
                        df_fechados_novo_upload['Data de Fechamento_dt'] = pd.to_datetime(data_atual_existente, format='%d/%m/%Y', errors='coerce')
                    
                    df_fechados_novo_upload['Data de Fechamento_str'] = df_fechados_novo_upload['Data de Fechamento_dt'].dt.strftime('%Y-%m-%d')
                    
                    df_historico_base = read_local_csv(STATE_FILE_MASTER_CLOSED_CSV, get_file_mtime(STATE_FILE_MASTER_CLOSED_CSV))
                    
                    id_col_hist = "ID do ticket"
                    if not df_historico_base.empty:
                        id_col_hist = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_historico_base.columns), "ID do ticket")
                        df_historico_base[id_col_hist] = normalize_ids(df_historico_base[id_col_hist])
                      
                    previous_closed_ids = set()
                    if not df_historico_base.empty:
                        previous_closed_ids = set(df_historico_base[id_col_hist].dropna().unique())

                    try:
                        with open(STATE_FILE_PREV_CLOSED, 'w') as f:
                            json.dump(list(previous_closed_ids), f)
                    except Exception: pass

                    cols_para_merge = [id_col_upload, 'Data de Fechamento_str']
                    if analista_col_name_origem in df_fechados_novo_upload.columns:
                        cols_para_merge.append(analista_col_name_origem)
                      
                    group_col_name_upload = next((col for col in ['Atribuir a um grupo', 'Grupo Atribuído', 'Grupo'] if col in df_fechados_novo_upload.columns), None)
                    if group_col_name_upload:
                         cols_para_merge.append(group_col_name_upload)

                    df_lookup = df_fechados_novo_upload[cols_para_merge].drop_duplicates(subset=[id_col_upload])
                    
                    if analista_col_name_origem in df_lookup.columns:
                         df_lookup[analista_col_name_origem] = df_lookup[analista_col_name_origem].astype(str).replace(r'\s+', ' ', regex=True).str.strip()

                    rename_dict = {
                        id_col_upload: id_col_hist, 
                        'Data de Fechamento_str': 'Data de Fechamento'
                    }
                    if group_col_name_upload:
                         rename_dict[group_col_name_upload] = 'Atribuir a um grupo'
                         
                    df_lookup = df_lookup.rename(columns=rename_dict)
                    
                    df_lookup = df_lookup.loc[:, ~df_lookup.columns.duplicated()]
                    if not df_historico_base.empty:
                        df_historico_base = df_historico_base.loc[:, ~df_historico_base.columns.duplicated()]

                    df_historico_final = pd.concat([df_historico_base, df_lookup], ignore_index=True)
                    
                    if id_col_hist in df_historico_final.columns:
                        df_historico_final = df_historico_final.drop_duplicates(subset=[id_col_hist], keep='last')

                    output_hist = StringIO()
                    df_historico_final.to_csv(output_hist, index=False, sep=';', encoding='utf-8')
                    
                    save_local_file(STATE_FILE_MASTER_CLOSED_CSV, output_hist.getvalue().encode('utf-8'), is_binary=True)
                    
                    st.sidebar.success("Arquivo de fechados adicionado ao histórico com sucesso! Recarregando...")
                    st.cache_data.clear()
                    st.rerun() 

                except Exception as e:
                    st.sidebar.error(f"Erro durante a atualização rápida: {e}")
        else:
            st.sidebar.warning("Por favor, carregue o arquivo de chamados fechados para salvar.")
elif password:
    st.sidebar.error("Senha incorreta.")

try:
    if 'contacted_tickets' not in st.session_state:
        st.session_state.contacted_tickets = set(read_local_json_file(STATE_FILE_CONTACTS, default_return_type='list'))

    if 'observations' not in st.session_state:
        st.session_state.observations = read_local_json_file(STATE_FILE_OBSERVATIONS, default_return_type='dict')

    if 'editor_key_counter' not in st.session_state:
        st.session_state.editor_key_counter = 0
        
    needs_scroll = "scroll" in st.query_params
    if "faixa" in st.query_params:
        faixa_from_url = st.query_params.get("faixa")
        ordem_faixas_validas = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
        if faixa_from_url in ordem_faixas_validas:
                st.session_state.faixa_selecionada = faixa_from_url
    if "scroll" in st.query_params or "faixa" in st.query_params:
        st.query_params.clear()

    mtime_atual = get_file_mtime(f"{DATA_DIR}dados_atuais.csv")
    df_atual = read_local_csv(f"{DATA_DIR}dados_atuais.csv", mtime_atual) 
    
    mtime_15dias = get_file_mtime(f"{DATA_DIR}dados_15_dias.csv")
    df_15dias = read_local_csv(f"{DATA_DIR}dados_15_dias.csv", mtime_15dias) 
    
    mtime_hist = get_file_mtime(STATE_FILE_MASTER_CLOSED_CSV)
    df_historico_fechados = read_local_csv(STATE_FILE_MASTER_CLOSED_CSV, mtime_hist)
    
    datas_referencia = read_local_text_file(STATE_FILE_REF_DATES) 
    
    data_atual_str = datas_referencia.get('data_atual', 'N/A')
    data_15dias_str = datas_referencia.get('data_15dias', 'N/A')
    hora_atualizacao_str = datas_referencia.get('hora_atualizacao', '')
    if df_atual.empty or df_15dias.empty: 
        st.warning("Ainda não há dados para exibir. Por favor, carregue os arquivos na área do administrador.")
        st.stop()

    if 'ID do ticket' in df_atual.columns:
        df_atual['ID do ticket'] = normalize_ids(df_atual['ID do ticket'])

    all_closed_ids_historico = set()
    id_col_historico = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_historico_fechados.columns), None)
    if id_col_historico and not df_historico_fechados.empty:
        all_closed_ids_historico = set(normalize_ids(df_historico_fechados[id_col_historico]).unique())
    
    df_abertos = df_atual
    
    df_abertos_base_para_reducao = df_abertos[~df_abertos['Atribuir a um grupo'].str.contains(GRUPOS_EXCLUSAO_PERMANENTE_REGEX, case=False, na=False, regex=True)].copy()

    df_atual_filtrado = df_abertos_base_para_reducao.copy()
    
    if all_closed_ids_historico:
         df_atual_filtrado = df_atual_filtrado[~df_atual_filtrado['ID do ticket'].isin(all_closed_ids_historico)]
    
    df_15dias_filtrado = df_15dias[~df_15dias['Atribuir a um grupo'].str.contains(GRUPOS_EXCLUSAO_TOTAL_REGEX, case=False, na=False, regex=True)]
    
    # Passar data de referência para o aging
    try:
        if data_atual_str != 'N/A':
            ref_date_obj = datetime.strptime(data_atual_str, '%d/%m/%Y')
        else:
            ref_date_obj = None
    except:
        ref_date_obj = None

    df_aging = analisar_aging(df_atual_filtrado, reference_date=ref_date_obj)
    
    df_encerrados_filtrado = pd.DataFrame()
     
    if not df_historico_fechados.empty:
        if 'Atribuir a um grupo' not in df_historico_fechados.columns:
            found_col = next((col for col in ['Grupo Atribuído', 'Grupo'] if col in df_historico_fechados.columns), None)
            if found_col:
                df_historico_fechados.rename(columns={found_col: 'Atribuir a um grupo'}, inplace=True)
            else:
                df_historico_fechados['Atribuir a um grupo'] = 'Desconhecido'

        df_encerrados_filtrado = df_historico_fechados[~df_historico_fechados['Atribuir a um grupo'].str.contains(GRUPOS_EXCLUSAO_PERMANENTE_REGEX, case=False, na=False, regex=True)]

    total_fechados_hoje = 0
    hoje_sp = datetime.now(ZoneInfo('America/Sao_Paulo')).date()
    
    if not df_encerrados_filtrado.empty and 'Data de Fechamento' in df_encerrados_filtrado.columns:
        df_encerrados_filtrado['Data de Fechamento_dt_comp'] = pd.to_datetime(
            df_encerrados_filtrado['Data de Fechamento'], 
            dayfirst=True, 
            errors='coerce'
        )
        fechados_hoje_df = df_encerrados_filtrado[
            df_encerrados_filtrado['Data de Fechamento_dt_comp'].dt.date == hoje_sp
        ].copy()
        
        id_col_backlog = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_abertos_base_para_reducao.columns), 'ID do ticket')
        open_ids_base = set(normalize_ids(df_abertos_base_para_reducao[id_col_backlog]).unique())
        
        id_col_hist = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in fechados_hoje_df.columns), None)
        closed_today_ids = set(normalize_ids(fechados_hoje_df[id_col_hist]).unique())
        
        # Cálculo inicial do card (pode ser sobrescrito abaixo)
        total_fechados_hoje = len(open_ids_base.intersection(closed_today_ids))

    # --- LÓGICA DE CARD: OLHAR DIRETAMENTE O ARQUIVO FECHADOS (IGUAL AO POP-UP) ---
    # Isso garante que o número do Card bata com o do Pop-up, ignorando inconsistências do histórico
    try:
        if os.path.exists(f"{DATA_DIR}dados_fechados.csv"):
             df_last_closed = read_local_csv(f"{DATA_DIR}dados_fechados.csv", get_file_mtime(f"{DATA_DIR}dados_fechados.csv"))
             if not df_last_closed.empty:
                 id_col_last = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_last_closed.columns), None)
                 id_col_backlog_base = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_abertos_base_para_reducao.columns), 'ID do ticket')
                 
                 # Filtra por HOJE no arquivo bruto
                 col_data_fechamento_last = next((c for c in ['Data de Fechamento', 'Data de Resolução'] if c in df_last_closed.columns), None)
                 
                 if id_col_last and id_col_backlog_base:
                     if col_data_fechamento_last:
                         df_last_closed['dt_temp_last'] = pd.to_datetime(df_last_closed[col_data_fechamento_last], dayfirst=True, errors='coerce')
                         df_last_closed_hoje = df_last_closed[df_last_closed['dt_temp_last'].dt.date == hoje_sp]
                     else:
                         # Fallback
                         df_last_closed_hoje = df_last_closed

                     ids_last_closed_hoje = set(normalize_ids(df_last_closed_hoje[id_col_last]))
                     ids_backlog_base = set(normalize_ids(df_abertos_base_para_reducao[id_col_backlog_base]))
                     
                     # Sobrescreve com o valor exato do último upload
                     total_fechados_hoje = len(ids_backlog_base.intersection(ids_last_closed_hoje))
    except Exception:
        pass
    # ----------------------------------------------------------------------------------------

    data_mais_recente_fechado_str = "" 

    if not df_encerrados_filtrado.empty and 'Data de Fechamento' in df_encerrados_filtrado.columns:
        try:
            if 'Data de Fechamento_dt_comp' not in df_encerrados_filtrado.columns:
                 df_encerrados_filtrado['Data de Fechamento_dt_comp'] = pd.to_datetime(df_encerrados_filtrado['Data de Fechamento'], dayfirst=True, errors='coerce')
            
            if not df_encerrados_filtrado['Data de Fechamento_dt_comp'].isnull().all():
                data_mais_recente_fechado_dt = df_encerrados_filtrado['Data de Fechamento_dt_comp'].max().date()
                data_mais_recente_fechado_str = data_mais_recente_fechado_dt.strftime('%d/%m/%Y') 
        except Exception as e:
            st.warning(f"Não foi possível processar datas de fechamento: {e}")

    tab1, tab2, tab3, tab4 = st.tabs(["Dashboard Completo", "Report Visual", "Evolução Semanal", "Evolução Aging"])

    with tab1:
        
        df_para_aviso = df_atual_filtrado[
            df_atual_filtrado['Atribuir a um grupo'].str.contains(
                GRUPOS_DE_AVISO_REGEX, case=False, na=False, regex=True
            )
        ]
        
        if not df_para_aviso.empty:
            total_para_aviso = len(df_para_aviso)
            contagem_por_grupo = df_para_aviso['Atribuir a um grupo'].value_counts()
            
            aviso_str_lista = [f"**Atenção:** Foram encontrados **{total_para_aviso}** chamados em grupos que deveriam estar zerados ({GRUPOS_DE_AVISO_TEXTO}):"]
            for grupo, contagem in contagem_por_grupo.items():
                aviso_str_lista.append(f"- **{grupo}:** {contagem} chamado(s)")
            
            st.warning("\n".join(aviso_str_lista))

        info_messages = ["**Filtros e Regras Aplicadas:**", 
                         f"- Grupos contendo {GRUPOS_EXCLUSAO_PERMANENTE_TEXTO} foram desconsiderados da análise.", 
                         "- A contagem de dias do chamado desconsidera o dia da sua abertura (prazo -1 dia)."]
        
        # --- INTEGRAÇÃO DO AVISO DE DATAS INVÁLIDAS ---
        diff_count = len(df_atual_filtrado) - len(df_aging)
        if diff_count > 0:
            info_messages.append(f"- **Atenção:** {diff_count} chamados foram desconsiderados por data inválida/vazia.")
        
        st.info("\n".join(info_messages))
        
        st.subheader("Análise de Antiguidade do Backlog Atual")
        texto_hora = f" (atualizado às {hora_atualizacao_str})" if hora_atualizacao_str else ""
        st.markdown(f"<p style='font-size: 0.9em; color: #666;'><i>Data de referência: {data_atual_str}{texto_hora}</i></p>", unsafe_allow_html=True)
        
        # CORREÇÃO DA MATEMÁTICA: TOTAL = SOMA DOS CARDS (df_aging)
        total_chamados = len(df_aging)

        col_spacer1, col_total, col_fechados, col_spacer2 = st.columns([1, 1.5, 1.5, 1])
        with col_total:
            st.markdown(f"""<div class="metric-box"><span class="label">Total de Chamados Abertos</span><span class="value">{total_chamados}</span></div>""", unsafe_allow_html=True)
        with col_fechados:
            st.markdown(f"""<div class="metric-box"><span class="label">Chamados Fechados HOJE</span><span class="value">{total_fechados_hoje}</span></div>""", unsafe_allow_html=True)

        st.markdown("---")

        if not df_aging.empty:
            aging_counts = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
            aging_counts.columns = ['Faixa de Antiguidade', 'Quantidade']
            ordem_faixas = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
            todas_as_faixas = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas})
            aging_counts = pd.merge(todas_as_faixas, aging_counts, on='Faixa de Antiguidade', how='left').fillna(0).astype({'Quantidade': int})
            aging_counts['Faixa de Antiguidade'] = pd.Categorical(aging_counts['Faixa de Antiguidade'], categories=ordem_faixas, ordered=True)
            aging_counts = aging_counts.sort_values('Faixa de Antiguidade')
            if 'faixa_selecionada' not in st.session_state:
                st.session_state.faixa_selecionada = "0-2 dias"
            cols = st.columns(len(ordem_faixas))
            for i, row in aging_counts.iterrows():
                with cols[i]:
                    faixa_encoded = quote(row['Faixa de Antiguidade'])
                    card_html = f"""<a href="?faixa={faixa_encoded}&scroll=true" target="_self" class="metric-box"><span class="label">{row['Faixa de Antiguidade']}</span><span class="value">{row['Quantidade']}</span></a>"""
                    st.markdown(card_html, unsafe_allow_html=True)
        else:
            st.warning("Nenhum dado válido para a análise de antiguidade (verifique as datas de criação no arquivo).")

        st.markdown(f"<h3>Comparativo de Backlog: Atual vs. 15 Dias Atrás <span style='font-size: 0.6em; color: #666; font-weight: normal;'>({data_15dias_str})</span></h3>", unsafe_allow_html=True)
        df_comparativo = processar_dados_comparativos(df_atual_filtrado.copy(), df_15dias_filtrado.copy())
        df_comparativo['Status'] = df_comparativo.apply(get_status, axis=1)
        
        df_comparativo = df_comparativo.rename(columns={'Atribuir a um grupo': 'Grupo'})
        
        df_comparativo = df_comparativo[['Grupo', '15 Dias Atrás', 'Atual', 'Diferença', 'Status']]
        st.dataframe(df_comparativo.set_index('Grupo').style.map(lambda val: 'background-color: #ffcccc' if val > 0 else ('background-color: #ccffcc' if val < 0 else 'background-color: white'), subset=['Diferença']), use_container_width=True)
        st.markdown("---")
        
        st.markdown(f"<h3>Histórico de Chamados Encerrados (Impacto no Backlog)</h3>", unsafe_allow_html=True)

        if df_historico_fechados.empty:
            st.info("O histórico de chamados encerrados ainda não possui dados. Faça uma 'Atualização Rápida' para começar a popular.")
        elif not df_encerrados_filtrado.empty:
            
            df_encerrados_para_exibir = df_encerrados_filtrado.copy()
            
            date_col_name = next((col for col in ['Data de criação', 'Data de Criacao'] if col in df_encerrados_para_exibir.columns), None)
            colunas_para_exibir_fechados = ['Status', 'ID do ticket', 'Descrição']
            novo_nome_analista = "Analista de Resolução" 
            analista_col_name_origem = "Analista atribuído" 
            novo_nome_grupo = "Grupo Atribuído"
            grupo_col_name_origem = "Atribuir a um grupo"

            if analista_col_name_origem in df_encerrados_para_exibir.columns:
                df_encerrados_para_exibir.rename(columns={analista_col_name_origem: novo_nome_analista}, inplace=True)
                colunas_para_exibir_fechados.append(novo_nome_analista)
            if grupo_col_name_origem in df_encerrados_para_exibir.columns:
                df_encerrados_para_exibir.rename(columns={grupo_col_name_origem: novo_nome_grupo}, inplace=True)
                colunas_para_exibir_fechados.append(novo_nome_grupo)

            if date_col_name and 'Data de Fechamento_dt_comp' in df_encerrados_para_exibir.columns:
                try:
                    data_criacao = pd.to_datetime(df_encerrados_para_exibir[date_col_name], errors='coerce').dt.normalize()
                    data_fechamento = df_encerrados_para_exibir['Data de Fechamento_dt_comp'].dt.normalize()
                    
                    dias_calculados = (data_fechamento - data_criacao).dt.days
                    df_encerrados_para_exibir['Dias em Aberto'] = dias_calculados.clip(lower=0)
                    colunas_para_exibir_fechados.append('Dias em Aberto')
                except Exception as e:
                    st.warning(f"Não foi possível calcular 'Dias em Aberto' para o histórico: {e}")
            
            try:
                datas_disponiveis = sorted(df_encerrados_para_exibir['Data de Fechamento_dt_comp'].dt.strftime('%d/%m/%Y').unique(), reverse=True)
                
                if not datas_disponiveis:
                    st.warning("Não há datas de fechamento válidas no histórico.")
                else:
                    opcoes_filtro = datas_disponiveis
                    
                    try:
                        default_index = opcoes_filtro.index(data_mais_recente_fechado_str)
                    except ValueError:
                        default_index = 0 
                    
                    data_selecionada = st.selectbox(
                        "Filtrar por Data de Fechamento:", 
                        options=opcoes_filtro, 
                        key="filtro_data_fechados",
                        index=default_index 
                    )
                    
                    data_dt_filtro = datetime.strptime(data_selecionada, '%d/%m/%Y').date()
                    df_encerrados_para_exibir = df_encerrados_para_exibir[df_encerrados_para_exibir['Data de Fechamento_dt_comp'].dt.date == data_dt_filtro]
                
                df_encerrados_para_exibir['Data de Fechamento'] = df_encerrados_para_exibir['Data de Fechamento_dt_comp'].dt.strftime('%d/%m/%Y')
                colunas_para_exibir_fechados.append('Data de Fechamento')
            
            except Exception as e:
                st.error(f"Erro ao processar datas de fechamento: {e}")
            
            id_col_encerrados = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_encerrados_para_exibir.columns), None)
            
            # --- CARREGA LISTA DE FECHADOS ANTERIOR PARA COMPARAR "NOVO" ---
            previous_closed_ids_loaded = set(read_local_json_file(STATE_FILE_PREV_CLOSED, default_return_type='list'))
            
            # --- DEFINE O STATUS "NOVO" ---
            if id_col_encerrados:
                 df_encerrados_para_exibir['Status'] = df_encerrados_para_exibir[id_col_encerrados].apply(
                      lambda x: "Novo" if normalize_ids(pd.Series([x])).iloc[0] not in previous_closed_ids_loaded else ""
                  )
            else:
                df_encerrados_para_exibir['Status'] = ""
            
            # --- FILTRO DE IMPACTO: MOSTRAR APENAS OS QUE CONSTAM NO ARQUIVO DE ABERTOS ---
            # Isso garante que só aparecem os chamados que reduziram o backlog,
            # removendo "fast-tracks" que não impactaram o estoque.
            if id_col_encerrados and 'open_ids_base' in locals():
                df_encerrados_para_exibir = df_encerrados_para_exibir[
                    df_encerrados_para_exibir[id_col_encerrados].apply(lambda x: normalize_ids(pd.Series([x])).iloc[0] in open_ids_base)
                ]
            # ----------------------------------------------------------------------------
            
            df_encerrados_para_exibir = df_encerrados_para_exibir.loc[:, ~df_encerrados_para_exibir.columns.duplicated()]
            
            colunas_finais = [col for col in colunas_para_exibir_fechados if col in df_encerrados_para_exibir.columns]
            
            if df_encerrados_para_exibir.empty:
                st.info(f"Nenhum chamado fechado em {data_selecionada} causou redução no backlog atual.")
            else:
                st.data_editor(
                    df_encerrados_para_exibir[colunas_finais], 
                    hide_index=True, 
                    disabled=True, 
                    use_container_width=True,
                    column_config={
                        "Status": st.column_config.Column(
                            width="small"
                        )
                    }
                )
            
        else:
            st.info("O arquivo de chamados encerrados do dia ainda não foi carregado.")

        if not df_aging.empty:
            st.markdown("---")
            st.subheader("Detalhar e Buscar Chamados")
            st.info('Marque "Contato" se já falou com o usuário e a solicitação continua pendente. Use "Observações" para anotações.')

            if 'scroll_to_details' not in st.session_state:
                st.session_state.scroll_to_details = False
            if needs_scroll or st.session_state.get('scroll_to_details', False):
                js_code = """<script> setTimeout(() => { const element = window.parent.document.getElementById('detalhar-e-buscar-chamados'); if (element) { element.scrollIntoView({ behavior: 'smooth', block: 'start' }); } }, 250); </script>"""
                components.html(js_code, height=0)
                st.session_state.scroll_to_details = False

            st.selectbox("Selecione uma faixa de idade para ver os detalhes (ou clique em um card acima):", 
                         options=ordem_faixas, 
                         key='faixa_selecionada',
                         on_change=sync_ticket_data)
            
            faixa_atual = st.session_state.faixa_selecionada
            filtered_df = df_aging[df_aging['Faixa de Antiguidade'] == faixa_atual].copy()
            if not filtered_df.empty:
                if 'Data de criação' in filtered_df.columns:
                     filtered_df['Data de criação'] = filtered_df['Data de criação'].dt.strftime('%d/%m/%Y')

                def highlight_row(row):
                    return ['background-color: #fff8c4'] * len(row) if row['Contato'] else [''] * len(row)

                filtered_df['Contato'] = filtered_df['ID do ticket'].apply(lambda id: str(id) in st.session_state.contacted_tickets)
                filtered_df['Observações'] = filtered_df['ID do ticket'].apply(lambda id: st.session_state.observations.get(str(id), ''))

                st.session_state.last_filtered_df = filtered_df.reset_index(drop=True)

                colunas_para_exibir_renomeadas = {
                    'Contato': 'Contato',
                    'ID do ticket': 'ID do ticket',
                    'Descrição': 'Descrição',
                    'Atribuir a um grupo': 'Grupo Atribuído',
                    'Dias em Aberto': 'Dias em Aberto',
                    'Data de criação': 'Data de criação',
                    'Observações': 'Observações'
                }
                
                colunas_desabilitadas_fixas = [
                    'ID do ticket', 'Descrição', 'Grupo Atribuído', 
                    'Dias em Aberto', 'Data de criação'
                ]
                colunas_editaveis_admin = [
                    'Contato', 'Observações'
                ]
                if is_admin:
                    colunas_desabilitadas_final = colunas_desabilitadas_fixas
                else:
                    colunas_desabilitadas_final = colunas_desabilitadas_fixas + colunas_editaveis_admin
                
                st.data_editor(
                    st.session_state.last_filtered_df.rename(columns=colunas_para_exibir_renomeadas)[list(colunas_para_exibir_renomeadas.values())].style.apply(highlight_row, axis=1),
                    use_container_width=True,
                    hide_index=True,
                    disabled=colunas_desabilitadas_final, 
                    key=f'ticket_editor_{st.session_state.editor_key_counter}'
                )
                
                st.button(
                    "Salvar Contatos e Observações",
                    on_click=sync_ticket_data,
                    type="primary",
                    disabled=not is_admin 
                )
                
            else:
                st.info("Não há chamados nesta categoria.")
            
            st.subheader("Buscar Chamados por Grupo")
            lista_grupos = sorted(df_aging['Atribuir a um grupo'].dropna().unique())
            grupo_selecionado = st.selectbox("Busca de chamados por grupo:", options=lista_grupos)
            if grupo_selecionado:
                resultados_busca = df_aging[df_aging['Atribuir a um grupo'] == grupo_selecionado].copy()
                if 'Data de criação' in resultados_busca.columns:
                    resultados_busca['Data de criação'] = resultados_busca['Data de criação'].dt.strftime('%d/%m/%Y')
                st.write(f"Encontrados {len(resultados_busca)} chamados para o grupo '{grupo_selecionado}':")
                colunas_para_exibir_busca = ['ID do ticket', 'Descrição', 'Dias em Aberto', 'Data de criação']
                st.data_editor(resultados_busca[[col for col in colunas_para_exibir_busca if col in resultados_busca.columns]], use_container_width=True, hide_index=True, disabled=True)

    with tab2:
        st.subheader("Resumo do Backlog Atual")
        if not df_aging.empty:
            
            total_chamados_tab2 = len(df_aging)
            _, col_total_tab2, _ = st.columns([2, 1.5, 2])
            with col_total_tab2: st.markdown( f"""<div class="metric-box"><span class="label">Total de Chamados</span><span class="value">{total_chamados_tab2}</span></div>""", unsafe_allow_html=True )
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
            
            chart_data = df_aging.groupby(['Atribuir a um grupo', 'Faixa de Antiguidade']).size().reset_index(name='Quantidade')
            group_totals = chart_data.groupby('Atribuir a um grupo')['Quantidade'].sum().sort_values(ascending=False)

            if not group_totals.empty:
                
                orientation_choice = st.radio( "Orientação do Gráfico:", ["Vertical", "Horizontal"], index=0, horizontal=True )
                
                new_labels_map = {group: f"{group} ({total})" for group, total in group_totals.items()}
                chart_data['Atribuir a um grupo'] = chart_data['Atribuir a um grupo'].map(new_labels_map)
                sorted_new_labels = [new_labels_map[group] for group in group_totals.index]
                def lighten_color(hex_color, amount=0.2):
                    try:
                        hex_color = hex_color.lstrip('#')
                        h, l, s = colorsys.rgb_to_hls(*[int(hex_color[i:i+2], 16)/255.0 for i in (0, 2, 4)])
                        new_l = l + (1 - l) * amount
                        r, g, b = colorsys.hls_to_rgb(h, new_l, s)
                        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
                    except Exception: return hex_color
                base_color = "#375623"
                palette = [ lighten_color(base_color, 0.85), lighten_color(base_color, 0.70), lighten_color(base_color, 0.55), lighten_color(base_color, 0.40), lighten_color(base_color, 0.20), base_color ]
                color_map = {faixa: color for faixa, color in zip(ordem_faixas, palette)}
                
                if orientation_choice == 'Horizontal':
                    num_groups = len(group_totals)
                    dynamic_height = max(500, num_groups * 30)
                    fig_stacked_bar = px.bar( chart_data, x='Quantidade', y='Atribuir a um grupo', orientation='h', color='Faixa de Antiguidade', title="Composição da Idade do Backlog por Grupo", labels={'Quantidade': 'Qtd. de Chamados', 'Atribuir a um grupo': ''}, category_orders={'Atribuir a um grupo': sorted_new_labels, 'Faixa de Antiguidade': ordem_faixas}, color_discrete_map=color_map, text_auto=True )
                    fig_stacked_bar.update_traces(textangle=0, textfont_size=12)
                    fig_stacked_bar.update_layout(height=dynamic_height, legend_title_text='Antiguidade')
                else:
                    fig_stacked_bar = px.bar( chart_data, x='Atribuir a um grupo', y='Quantidade', color='Faixa de Antiguidade', title="Composição da Idade do Backlog por Grupo", labels={'Quantidade': 'Qtd. de Chamados', 'Atribuir a um grupo': 'Grupo'}, category_orders={'Atribuir a um grupo': sorted_new_labels, 'Faixa de Antiguidade': ordem_faixas}, color_discrete_map=color_map, text_auto=True )
                    fig_stacked_bar.update_traces(textangle=0, textfont_size=12)
                    fig_stacked_bar.update_layout(height=600, xaxis_title=None, xaxis_tickangle=-45, legend_title_text='Antiguidade')
                
                st.plotly_chart(fig_stacked_bar, use_container_width=True)

                # --- PARETO LIBERADO PARA TODOS (SEM IF IS_ADMIN) ---
                df_pareto = group_totals.to_frame(name='Total')
                df_pareto['CumulativePct'] = df_pareto['Total'].cumsum() / df_pareto['Total'].sum()
                
                total_backlog_geral = df_pareto['Total'].sum()
                total_grupos_geral = len(df_pareto)
                
                pareto_limit = 0.80
                num_groups_for_80_pct = 1
                if df_pareto['CumulativePct'].iloc[0] <= pareto_limit:
                    try:
                        groups_under_80 = df_pareto[df_pareto['CumulativePct'] <= pareto_limit]
                        num_groups_for_80_pct = len(groups_under_80) + 1
                    except Exception:
                        num_groups_for_80_pct = 1 
                
                if num_groups_for_80_pct > total_grupos_geral:
                    num_groups_for_80_pct = total_grupos_geral

                final_pareto_groups = df_pareto.head(num_groups_for_80_pct)
                actual_pct = final_pareto_groups.iloc[-1]['CumulativePct']
                actual_call_count = final_pareto_groups['Total'].sum()
                
                top_3_groups = group_totals.head(3)
                
                summary_text = [f"**Análise Rápida (Princípio de Pareto):**\n"]
                summary_text.append(f"* Nossa análise mostra que **{num_groups_for_80_pct}** grupos (de um total de **{total_grupos_geral}**) são responsáveis por **{actual_call_count}** chamados, o que representa **{actual_pct:.0%}** de todo o backlog (de {total_backlog_geral} chamados).\n")
                summary_text.append(f"* Os 3 grupos de maior impacto são:\n")
                
                list_items = []
                for i, (group, count) in enumerate(top_3_groups.items(), 1):
                    list_items.append(f"    {i}.  **{group}** ({count} chamados)")
                summary_text.append("\n".join(list_items))
                
                summary_text.append(f"\n**Análise por Categoria:**\n")
                
                try:
                    total_sap = group_totals[group_totals.index.str.contains('SAP', case=False, na=False)].sum()
                    total_3n = group_totals[group_totals.index.str.contains('3N', case=False, na=False)].sum()
                    total_outros = group_totals[~group_totals.index.str.contains('SAP|3N', case=False, na=False)].sum()
                    
                    summary_text.append(f"* Grupos contendo 'SAP' representam **{total_sap}** chamados ({total_sap/total_backlog_geral:.0%}).")
                    summary_text.append(f"* Grupos contendo '3N' representam **{total_3n}** chamados ({total_3n/total_backlog_geral:.0%}).")
                    summary_text.append(f"* Os demais grupos (sem 'SAP' ou '3N') somam **{total_outros}** chamados ({total_outros/total_backlog_geral:.0%}).")
                    
                    if (total_sap + total_3n + total_outros) != total_backlog_geral:
                            summary_text.append(f"\n*(Nota: Pode haver sobreposição nos totais acima se um grupo contiver 'SAP' e '3N'.)*")
                
                except Exception as e:
                    summary_text.append(f"*Ocorreu um erro ao gerar a análise por categoria: {e}*")

                st.info("\n".join(summary_text))
        else:
            st.warning("Nenhum dado para gerar o report visual.")

    with tab3:
        st.subheader("Evolução do Backlog")
        dias_evolucao = st.slider("Ver evolução dos últimos dias:", min_value=7, max_value=30, value=7, key="slider_evolucao")

        df_evolucao_tab3 = carregar_dados_evolucao(dias_evolucao, df_historico_fechados.copy()) 

        if not df_evolucao_tab3.empty:

            df_evolucao_tab3['Data'] = pd.to_datetime(df_evolucao_tab3['Data'])
            df_evolucao_tab3 = df_evolucao_tab3[df_evolucao_tab3['Data'].dt.dayofweek < 5].copy()

            if not df_evolucao_tab3.empty:

                st.info("Esta visualização ainda está coletando dados históricos. Utilize as outras abas como referência principal por enquanto.")
                
                try:
                    latest_date_in_chart = df_evolucao_tab3['Data'].max()
                    
                    agregado_agora = df_aging.groupby('Atribuir a um grupo').size().reset_index(name='Total Chamados')
                    agregado_agora['Data'] = latest_date_in_chart
                    
                    df_evolucao_tab3 = df_evolucao_tab3[df_evolucao_tab3['Data'] != latest_date_in_chart]
                    
                    df_evolucao_tab3 = pd.concat([df_evolucao_tab3, agregado_agora], ignore_index=True)
                    
                    df_evolucao_tab3 = df_evolucao_tab3.sort_values(by=['Data', 'Atribuir a um grupo'])

                    df_evolucao_tab3 = df_evolucao_tab3[~df_evolucao_tab3['Atribuir a um grupo'].str.contains(GRUPOS_EXCLUSAO_TOTAL_REGEX, case=False, na=False, regex=True)]
                    
                except Exception as e:
                    pass
                

                df_total_abertos = df_evolucao_tab3.groupby('Data')['Total Chamados'].sum().reset_index()
                df_total_abertos = df_total_abertos.sort_values('Data')
                df_total_abertos['Tipo'] = 'Abertos (Backlog)'
                
                end_date_tab3 = date.today()
                start_date_tab3 = end_date_tab3 - timedelta(days=dias_evolucao)
                
                df_total_fechados = pd.DataFrame()
                if not df_encerrados_filtrado.empty and 'Data de Fechamento' in df_encerrados_filtrado.columns:
                    df_fechados_hist = df_encerrados_filtrado[['Data de Fechamento']].copy()
                    
                    df_fechados_hist['Data'] = pd.to_datetime(df_fechados_hist['Data de Fechamento'], dayfirst=True, errors='coerce')
                    
                    df_fechados_hist = df_fechados_hist.dropna(subset=['Data'])
                    
                    df_fechados_hist = df_fechados_hist[
                        (df_fechados_hist['Data'].dt.date >= start_date_tab3) &
                        (df_fechados_hist['Data'].dt.date <= end_date_tab3)
                    ]
                    
                    if not df_fechados_hist.empty:
                        # DEDUPLICATION FIX: Ensure we count distinct tickets per day
                        id_col_fechados_hist = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_fechados_hist.columns), None)
                        if id_col_fechados_hist:
                             df_fechados_hist = df_fechados_hist.drop_duplicates(subset=[id_col_fechados_hist])
                        
                        counts_por_data = df_fechados_hist.groupby(df_fechados_hist['Data'].dt.date).size()
                        df_total_fechados = counts_por_data.reset_index(name='Total Chamados')
                        df_total_fechados['Data'] = pd.to_datetime(df_total_fechados['Data'])
                        df_total_fechados['Tipo'] = 'Fechados'
                
                if not df_total_fechados.empty:
                    df_total_diario_combinado = pd.concat([df_total_abertos, df_total_fechados], ignore_index=True)
                else:
                    df_total_diario_combinado = df_total_abertos
                    
                df_total_diario_combinado = df_total_diario_combinado.sort_values('Data')
                
                
                if not df_total_diario_combinado.empty and 'Fechados' in df_total_diario_combinado['Tipo'].unique():
                    latest_date = df_total_diario_combinado['Data'].max()

                    df_total_diario_combinado.loc[
                        (df_total_diario_combinado['Data'] == latest_date) & 
                        (df_total_diario_combinado['Tipo'] == 'Fechados'), 
                        'Total Chamados'
                    ] = total_fechados_hoje
                

                df_total_diario_combinado['Data (Eixo)'] = df_total_diario_combinado['Data'].dt.strftime('%d/%m')
                ordem_datas_total = df_total_diario_combinado['Data (Eixo)'].unique().tolist()
                
                fig_total_evolucao = px.line(
                    df_total_diario_combinado,
                    x='Data (Eixo)',
                    y='Total Chamados',
                    color='Tipo',
                    title='Evolução Total de Chamados: Backlog Líquido vs. Fechados (Dias de Semana)',
                    markers=True,
                    labels={"Data (Eixo)": "Data", "Total Chamados": "Total Geral de Chamados", "Tipo": "Métrica"},
                    category_orders={'Data (Eixo)': ordem_datas_total},
                    color_discrete_map={
                        'Abertos (Backlog)': '#375623', 
                        'Fechados': '#f28801' 
                    }
                )

                fig_total_evolucao.update_layout(height=400)
                st.plotly_chart(fig_total_evolucao, use_container_width=True)

                st.markdown("---")

                st.info("Esta visualização já filtra os chamados fechados e permite filtrar grupos clicando 2x na legenda.")

                df_evolucao_tab3_sorted = df_evolucao_tab3.sort_values('Data')
                df_evolucao_tab3_sorted['Data (Eixo)'] = df_evolucao_tab3_sorted['Data'].dt.strftime('%d/%m')

                ordem_datas_grupo = df_evolucao_tab3_sorted['Data (Eixo)'].unique().tolist()

                df_filtrado_display = df_evolucao_tab3_sorted.rename(columns={'Atribuir a um grupo': 'Grupo Atribuído'})

                fig_evolucao_grupo = px.line(
                    df_filtrado_display,
                    x='Data (Eixo)',
                    y='Total Chamados',
                    color='Grupo Atribuído',
                    title='Evolução por Grupo (Apenas Dias de Semana)',
                    markers=True,
                    labels={ "Data (Eixo)": "Data", "Total Chamados": "Nº de Chamados", "Grupo Atribuído": "Grupo" },
                    category_orders={'Data (Eixo)': ordem_datas_grupo}
                )
                fig_evolucao_grupo.update_layout(height=600)
                st.plotly_chart(fig_evolucao_grupo, use_container_width=True)

            else:
                st.info("Ainda não há dados históricos suficientes (considerando apenas dias de semana).")

        else:
            st.info("Ainda não há dados históricos suficientes.")

    with tab4:
        st.subheader("Evolução do Aging do Backlog")
        
        st.info("Esta visualização ainda está coletando dados históricos. Utilize as outras abas como referência principal por enquanto.")

        try:
            df_hist = carregar_evolucao_aging(dias_para_analisar=90) 

            ordem_faixas_scaffold = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
            hoje_data = None
            hoje_counts_df = pd.DataFrame()

            if 'df_aging' in locals() and not df_aging.empty and data_atual_str != 'N/A':
                try:
                    hoje_data = pd.to_datetime(datetime.strptime(data_atual_str, "%d/%m/%Y").date())
                    hoje_counts_raw = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
                    hoje_counts_raw.columns = ['Faixa de Antiguidade', 'total']
                    df_todas_faixas_hoje = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas_scaffold})
                    hoje_counts_df = pd.merge(
                        df_todas_faixas_hoje,
                        hoje_counts_raw,
                        on='Faixa de Antiguidade',
                        how='left'
                    ).fillna(0)
                    hoje_counts_df['total'] = hoje_counts_df['total'].astype(int)
                    hoje_counts_df['data'] = hoje_data
                except ValueError:
                    st.warning("Data atual inválida. Não foi possível carregar dados de 'hoje'.")
                    hoje_data = None
            else:
                st.warning("Não foi possível carregar dados de 'hoje'.")


            if not df_hist.empty and not hoje_counts_df.empty:
                df_combinado = pd.concat([df_hist, hoje_counts_df], ignore_index=True)
                df_combinado = df_combinado.drop_duplicates(subset=['data', 'Faixa de Antiguidade'], keep='last')
            elif not df_hist.empty:
                df_combinado = df_hist.copy()
            elif not hoje_counts_df.empty:
                df_combinado = hoje_counts_df.copy()
            else:
                st.error("Não há dados históricos nem dados de hoje para a análise de aging.")
                st.stop()

            df_combinado['data'] = pd.to_datetime(df_combinado['data'])
            df_combinado = df_combinado.sort_values(by=['data', 'Faixa de Antiguidade'])


            st.markdown("##### Comparativo")
            periodo_comp_opts = {
                "Ontem": 1,
                "7 dias atrás": 7,
                "15 dias atrás": 15,
                "30 dias atrás": 30
            }
            periodo_comp_selecionado = st.radio(
                "Comparar 'Hoje' com:",
                options=periodo_comp_opts.keys(),
                horizontal=True,
                key="radio_comp_periodo"
            )

            data_comparacao_final = None
            df_comparacao_dados = pd.DataFrame()
            data_comparacao_str = "N/A"

            if hoje_data:
                target_comp_date = hoje_data.date() - timedelta(days=periodo_comp_opts[periodo_comp_selecionado])
                data_comparacao_encontrada, _ = find_closest_snapshot_before(hoje_data.date(), target_comp_date) 

                if data_comparacao_encontrada:
                    data_comparacao_final = pd.to_datetime(data_comparacao_encontrada)
                    data_comparacao_str = data_comparacao_final.strftime('%d/%m')
                    df_comparacao_dados = df_combinado[df_combinado['data'] == data_comparacao_final].copy()
                else:
                    st.warning(f"Não foi encontrado snapshot próximo a {periodo_comp_selecionado} ({target_comp_date.strftime('%d/%m')}). A comparação pode não ser precisa.")


            cols_linha1 = st.columns(3)
            cols_linha2 = st.columns(3)
            cols_map = {0: cols_linha1[0], 1: cols_linha1[1], 2: cols_linha1[2], 
                        3: cols_linha2[0], 4: cols_linha2[1], 5: cols_linha2[2]}

            for i, faixa in enumerate(ordem_faixas_scaffold):
                with cols_map[i]:
                    valor_hoje = 'N/A'
                    if not hoje_counts_df.empty:
                        valor_hoje_series = hoje_counts_df.loc[hoje_counts_df['Faixa de Antiguidade'] == faixa, 'total']
                        if not valor_hoje_series.empty:
                            valor_hoje = int(valor_hoje_series.iloc[0])
                    
                    valor_comparacao = 0
                    delta_text = "N/A"
                    delta_class = "delta-neutral"

                    if data_comparacao_final and not df_comparacao_dados.empty and isinstance(valor_hoje, int):
                        valor_comp_series = df_comparacao_dados.loc[df_comparacao_dados['Faixa de Antiguidade'] == faixa, 'total']
                        if not valor_comp_series.empty:
                            valor_comparacao = int(valor_comp_series.iloc[0])
                        
                        delta_abs = valor_hoje - valor_comparacao
                        delta_perc = (delta_abs / valor_comparacao) if valor_comparacao > 0 else 0
                        delta_text, delta_class = formatar_delta_card(delta_abs, delta_perc, valor_comparacao, data_comparacao_str)
                    elif isinstance(valor_hoje, int):
                        delta_text = "Sem dados para comparar"

                    st.markdown(f"""
                    <div class="metric-box">
                        <span class="label">{faixa}</span>
                        <span class="value">{valor_hoje}</span>
                        <span class="delta {delta_class}">{delta_text}</span>
                    </div>
                    """, unsafe_allow_html=True)

            st.divider()

            st.markdown(f"##### Gráfico de Evolução (Últimos 7 dias)")

            periodo_grafico = "Últimos 7 dias"
            hoje_filtro_grafico = datetime.now().date()
            data_inicio_filtro_grafico = hoje_filtro_grafico - timedelta(days=7)
            df_filtrado_grafico = df_combinado[df_combinado['data'].dt.date >= data_inicio_filtro_grafico].copy()


            if df_filtrado_grafico.empty:
                st.warning("Não há dados para o período selecionado.")
            else:
                df_grafico = df_filtrado_grafico.sort_values(by='data')
                df_grafico['Data (Eixo)'] = df_grafico['data'].dt.strftime('%d/%m')
                ordem_datas_grafico = df_grafico['Data (Eixo)'].unique().tolist()

                def lighten_color(hex_color, amount=0.2):
                    try:
                        hex_color = hex_color.lstrip('#')
                        h, l, s = colorsys.rgb_to_hls(*[int(hex_color[i:i+2], 16)/255.0 for i in (0, 2, 4)])
                        new_l = l + (1 - l) * amount
                        r, g, b = colorsys.hls_to_rgb(h, new_l, s)
                        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
                    except Exception: return hex_color
                base_color = "#375623"
                palette = [ lighten_color(base_color, 0.85), lighten_color(base_color, 0.70), lighten_color(base_color, 0.55), lighten_color(base_color, 0.40), lighten_color(base_color, 0.20), base_color ]
                color_map = {faixa: color for faixa, color in zip(ordem_faixas_scaffold, palette)}

                tipo_grafico = st.radio(
                    "Selecione o tipo de gráfico:",
                    ("Gráfico de Linha (Comparativo)", "Gráfico de Área (Composição)"),
                    horizontal=True,
                    key="radio_tipo_grafico_aging"
                )

                if tipo_grafico == "Gráfico de Linha (Comparativo)":
                    fig_aging_all = px.line(
                        df_grafico,
                        x='Data (Eixo)',
                        y='total',
                        color='Faixa de Antiguidade',
                        title='Evolução por Faixa de Antiguidade',
                        markers=True,
                        labels={"Data (Eixo)": "Data", "total": "Total Chamados", "Faixa de Antiguidade": "Faixa"},
                        category_orders={
                            'Data (Eixo)': ordem_datas_grafico,
                            'Faixa de Antiguidade': ordem_faixas_scaffold
                        },
                        color_discrete_map=color_map
                    )
                else:
                    fig_aging_all = px.area(
                        df_grafico,
                        x='Data (Eixo)',
                        y='total',
                        color='Faixa de Antiguidade',
                        title='Composição da Evolução por Antiguidade',
                        markers=True,
                        labels={"Data (Eixo)": "Data", "total": "Total Chamados", "Faixa de Antiguidade": "Faixa"},
                        category_orders={
                            'Data (Eixo)': ordem_datas_grafico,
                            'Faixa de Antiguidade': ordem_faixas_scaffold
                        },
                        color_discrete_map=color_map
                    )
                
                fig_aging_all.update_layout(height=500)
                st.plotly_chart(fig_aging_all, use_container_width=True)

        except Exception as e:
            st.error(f"Ocorreu um erro ao gerar a aba de Evolução Aging: {e}")
            st.exception(e)

except Exception as e:
    st.error(f"Ocorreu um erro ao carregar os dados: {e}")
    st.exception(e)

if 'ticket_editor' in st.session_state and st.session_state.ticket_editor.get('edited_rows'):
    js_code = """
    <script>
    window.onbeforeunload = function() {
        return "Você tem alterações não salvas. Deseja realmente sair?";
    };
    </script>
    """
    components.html(js_code, height=0)
else:
    js_code = """
    <script>
    window.onbeforeunload = null;
    </script>
    """
    components.html(js_code, height=0)

st.markdown("---")
st.markdown("""
<p style='text-align: center; color: #666; font-size: 0.9em; margin-bottom: 0;'>V1.0.48 | Este dashboard está em desenvolvimento.</p>
<p style='text-align: center; color: #666; font-size: 0.9em; margin-top: 0;'>Desenvolvido por Leonir Scatolin Junior</p>
""", unsafe_allow_html=True)
