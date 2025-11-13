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

GRUPOS_EXCLUSAO_PERMANENTE_REGEX = r'RH|Aprovadores GGM|RDM-GTR'
GRUPOS_EXCLUSAO_PERMANENTE_TEXTO = "'RH', 'Aprovadores GGM' ou 'RDM-GTR'"

GRUPOS_DE_AVISO_REGEX = r'Service Desk \(L1\)|LIQ-SUTEL'
GRUPOS_DE_AVISO_TEXTO = "'Service Desk (L1)' ou 'LIQ-SUTEL'"

GRUPOS_EXCLUSAO_TOTAL_REGEX = f"{GRUPOS_EXCLUSAO_PERMANENTE_REGEX}|{GRUPOS_DE_AVISO_REGEX}"

DATA_DIR = "data/"
STATE_FILE_CONTACTS = "contacted_tickets.json"
STATE_FILE_OBSERVATIONS = "ticket_observations.json"
STATE_FILE_REF_DATES = "datas_referencia.txt"
STATE_FILE_CLOSED_HISTORY = "closed_tickets_history.json"
STATE_FILE_MASTER_CLOSED_CSV = f"{DATA_DIR}historico_fechados_master.csv"

st.set_page_config(
    layout="wide",
    page_title="Backlog Copa Energia + Belago",
    page_icon=f"{DATA_DIR}minilogo.png",
    initial_sidebar_state="collapsed"
)

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
}
a.metric-box { 
    display: block;
    color: inherit;
    text-decoration: none !important;
}
a.metric-box:hover {
    background-color: #f0f2f6;
    text-decoration: none !important;
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
[data-testid="stSidebar"] [data-testid="stButton"] button:active {
    background-color: #b86700; 
    color: white;
    border-color: #b86700;
}
[data-testid="stSidebar"] [data-testid="stButton"] button:focus:not(:active) {
    border-color: #f28801;
    box-shadow: 0 0 0 0.2rem rgba(242, 136, 1, 0.5); 
}
</style>
""")

def save_local_file(file_path, file_content, is_binary=False):
    try:
        directory = os.path.dirname(file_path)
        if directory: 
            os.makedirs(directory, exist_ok=True)
            
        mode = 'wb' if is_binary else 'w'
        encoding = None if is_binary else 'utf-8'
        
        with open(file_path, mode, encoding=encoding) as f:
            f.write(file_content)
            
        if file_path not in [STATE_FILE_CONTACTS, STATE_FILE_OBSERVATIONS, STATE_FILE_REF_DATES, STATE_FILE_CLOSED_HISTORY, STATE_FILE_MASTER_CLOSED_CSV]:
            st.sidebar.info(f"Arquivo '{file_path}' salvo localmente.")
            
    except Exception as e:
        st.sidebar.error(f"Falha ao salvar '{file_path}' localmente: {e}")
        raise

@st.cache_data
def read_local_csv(file_path):
    if not os.path.exists(file_path):
        return pd.DataFrame() 
    
    try:
        try:
            df = pd.read_csv(file_path, delimiter=';', encoding='utf-8',
                             dtype={'ID do ticket': str, 'ID do Ticket': str, 'ID': str}, low_memory=False,
                             on_bad_lines='warn')
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, delimiter=';', encoding='latin1',
                             dtype={'ID do ticket': str, 'ID do Ticket': str, 'ID': str}, low_memory=False,
                             on_bad_lines='warn')
            if file_path in [f"{DATA_DIR}dados_fechados.csv", STATE_FILE_MASTER_CLOSED_CSV]:
                 st.sidebar.warning(f"Arquivo '{file_path}' lido com encoding 'latin-1' localmente.")
        
        df.columns = df.columns.str.strip()
        df.dropna(how='all', inplace=True)
        return df
        
    except pd.errors.ParserError as parse_err:
        st.error(f"Erro ao parsear o CSV '{file_path}': {parse_err}. Verifique o delimitador (;) e a estrutura do arquivo.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro inesperado ao ler o arquivo '{file_path}': {e}")
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
        st.warning(f"Erro inesperado ao ler {file_path}: {e}")
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
    except json.JSONDecodeError:
        st.error(f"Erro ao decodificar JSON '{file_path}' local.")
        return default_return
    except Exception as e:
        st.error(f"Erro inesperado ao ler JSON '{file_path}': {e}")
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
            df = pd.read_csv(StringIO(content), delimiter=';', dtype=dtype_spec)
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
def analisar_aging(_df_atual):
    df = _df_atual.copy()
    date_col_name = None
    if 'Data de criação' in df.columns: date_col_name = 'Data de criação'
    elif 'Data de Criacao' in df.columns: date_col_name = 'Data de Criacao'
    if not date_col_name:
        return pd.DataFrame()
    df[date_col_name] = pd.to_datetime(df[date_col_name], errors='coerce')
    linhas_invalidas = df[df[date_col_name].isna()]
    if not linhas_invalidas.empty:
        with st.expander(f"⚠️ Atenção: {len(linhas_invalidas)} chamados foram descartados por data inválida ou vazia."):
            st.dataframe(linhas_invalidas.head())
    
    df = df.dropna(subset=[date_col_name])
    
    hoje = pd.to_datetime('today').normalize()
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
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode()
    except Exception:
        return None

def sync_ticket_data():
    if 'ticket_editor' not in st.session_state or not st.session_state.ticket_editor.get('edited_rows'):
        return
        
    edited_rows = st.session_state.ticket_editor['edited_rows']
    contact_changed = False
    observation_changed = False
    
    for row_index, changes in edited_rows.items():
        try:
            ticket_id = str(st.session_state.last_filtered_df.iloc[row_index]['ID do ticket'])
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
            st.warning(f"Erro ao processar linha {row_index}.")
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
            
            st.toast("Alterações salvas com sucesso!", icon="✅")
            
        except Exception as e:
            st.error(f"Erro ao salvar alterações: {e}")
            st.session_state.scroll_to_details = True
            return

    else:
        pass 

    st.session_state.ticket_editor['edited_rows'] = {}
    st.session_state.scroll_to_details = True


@st.cache_data
def carregar_dados_evolucao(dias_para_analisar=7): 
    try:
        snapshot_dir = f"{DATA_DIR}snapshots"
        
        try:
            local_files = [os.path.join(snapshot_dir, f) for f in os.listdir(snapshot_dir) if f.endswith('.csv')]
            if not local_files:
                raise FileNotFoundError("Pasta de snapshots local vazia ou não encontrada.")
            all_files = local_files
        except FileNotFoundError:
             return pd.DataFrame() 

        df_evolucao_list = []
        end_date = date.today()
        start_date = end_date - timedelta(days=max(dias_para_analisar, 10))

        processed_dates = []
        for file_name in all_files:
            if file_name.startswith(f"{snapshot_dir}/backlog_") and file_name.endswith(".csv"):
                try:
                    date_str = file_name.replace(f"{snapshot_dir}/backlog_", "").replace(".csv", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if start_date <= file_date <= end_date:
                        processed_dates.append((file_date, file_name))
                except ValueError: continue
                except Exception: continue

        processed_dates.sort(key=lambda x: x[0], reverse=True)
        files_to_process = [f[1] for f in processed_dates[:dias_para_analisar]]

        for file_name in files_to_process:
                try:
                    date_str = file_name.replace(f"{snapshot_dir}/backlog_", "").replace(".csv", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    df_snapshot = read_local_csv(file_name) 
                    if not df_snapshot.empty and 'Atribuir a um grupo' in df_snapshot.columns:
                        
                        df_snapshot_filtrado = df_snapshot[~df_snapshot['Atribuir a um grupo'].str.contains(GRUPOS_EXCLUSAO_TOTAL_REGEX, case=False, na=False, regex=True)]
                        
                        df_snapshot_final = df_snapshot_filtrado
                        
                        contagem_diaria = df_snapshot_final.groupby('Atribuir a um grupo').size().reset_index(name='Total Chamados')
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
            if not local_files:
                raise FileNotFoundError("Pasta de snapshots local vazia ou não encontrada.")
            all_file_paths = local_files
        except FileNotFoundError:
            return None, None 

        snapshots = []
        search_start_date = target_date - timedelta(days=10)

        for file_path in all_file_paths:
            match = re.search(r"backlog_(\d{4}-\d{2}-\d{2})\.csv", file_path.split('/')[-1])
            if match:
                snapshot_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
                if search_start_date <= snapshot_date <= target_date:
                    snapshots.append((snapshot_date, file_path))

        if not snapshots:
            return None, None

        snapshots.sort(key=lambda x: x[0], reverse=True)
        return snapshots[0]

    except Exception as e:
        st.warning(f"Erro ao buscar snapshots: {e}")
        return None, None

@st.cache_data
def carregar_evolucao_aging(dias_para_analisar=90): 
    try:
        snapshot_dir = f"{DATA_DIR}snapshots"
        
        try:
            local_files = [os.path.join(snapshot_dir, f) for f in os.listdir(snapshot_dir) if f.endswith('.csv')]
            if not local_files:
                raise FileNotFoundError("Pasta de snapshots local vazia ou não encontrada.")
            all_files = local_files
        except FileNotFoundError:
            return pd.DataFrame() 

        lista_historico = []

        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=max(dias_para_analisar, 60))

        processed_files = []
        for file_name in all_files:
            if not file_name.startswith(snapshot_dir):
                file_name = f"{snapshot_dir}/{file_name.split('/')[-1]}"

            if file_name.startswith(f"{snapshot_dir}/backlog_") and file_name.endswith(".csv"):
                try:
                    date_str = file_name.replace(f"{snapshot_dir}/backlog_", "").replace(".csv", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if start_date <= file_date <= end_date:
                        processed_files.append((file_date, file_name))
                except Exception:
                    continue

        processed_files.sort(key=lambda x: x[0])

        for file_date, file_name in processed_files:
            try:
                df_snapshot = read_local_csv(file_name) 
                if df_snapshot.empty:
                    continue

                df_filtrado = df_snapshot[~df_snapshot['Atribuir a um grupo'].str.contains(GRUPOS_EXCLUSAO_TOTAL_REGEX, case=False, na=False, regex=True)]

                df_final = df_filtrado
                df_final = df_final.copy() 

                date_col_name = next((col for col in ['Data de criação', 'Data de Criacao'] if col in df_final.columns), None)
                if not date_col_name:
                    continue

                df_final[date_col_name] = pd.to_datetime(df_final[date_col_name], errors='coerce')
                df_final = df_final.dropna(subset=[date_col_name])

                snapshot_date_dt = pd.to_datetime(file_date)
                data_criacao_normalizada = df_final[date_col_name].dt.normalize()
                dias_calculados = (snapshot_date_dt - data_criacao_normalizada).dt.days
                dias_em_aberto_corrigido = (dias_calculados - 1).clip(lower=0)

                faixas_antiguidade = categorizar_idade_vetorizado(dias_em_aberto_corrigido)

                contagem_faixas = pd.Series(faixas_antiguidade).value_counts().reset_index()
                contagem_faixas.columns = ['Faixa de Antiguidade', 'total']

                ordem_faixas_scaffold = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
                df_todas_faixas = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas_scaffold})

                contagem_completa = pd.merge(
                    df_todas_faixas,
                    contagem_faixas,
                    on='Faixa de Antiguidade',
                    how='left'
                ).fillna(0)

                contagem_completa['total'] = contagem_completa['total'].astype(int)
                contagem_completa['data'] = snapshot_date_dt

                lista_historico.append(contagem_completa)

            except Exception:
                continue

        if not lista_historico:
            return pd.DataFrame()

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

    if delta_abs > 0:
        delta_class = "delta-positive"
    elif delta_abs < 0:
        delta_class = "delta-negative"
    else:
        delta_class = "delta-neutral"

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
                now_sao_paulo = datetime.now(ZoneInfo('America/Sao_Paulo'))
                commit_msg = f"Dados atualizados em {now_sao_paulo.strftime('%d/%m/%Y %H:%M')}"
                
                content_atual_raw = process_uploaded_file(uploaded_file_atual)
                content_15dias = process_uploaded_file(uploaded_file_15dias)
                
                if content_atual_raw is not None and content_15dias is not None:
                    try:
                        # <<< CORREÇÃO >>> Lógica de apagar o histórico foi REMOVIDA.
                        
                        df_novo_atual_raw = pd.read_csv(BytesIO(content_atual_raw), delimiter=';', dtype={'ID do ticket': str, 'ID do Ticket': str, 'ID': str})
                        
                        df_hist_fechados = read_local_csv(STATE_FILE_MASTER_CLOSED_CSV)
                        all_closed_ids_historico = set()
                        id_col_hist = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_hist_fechados.columns), None)
                        if id_col_hist and not df_hist_fechados.empty:
                            all_closed_ids_historico = set(df_hist_fechados[id_col_hist].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().dropna().unique())

                        id_col_atual = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_novo_atual_raw.columns), None)
                        
                        df_novo_atual_filtrado = df_novo_atual_raw 
                        
                        if id_col_atual and all_closed_ids_historico: 
                            df_novo_atual_raw[id_col_atual] = df_novo_atual_raw[id_col_atual].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
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
                        hora_atualizacao = now_sao_paulo.strftime('%H:%M')
                        datas_referencia_content = (f"data_atual:{data_do_upload.strftime('%d/%m/%Y')}\n"
                                                      f"data_15dias:{data_arquivo_15dias.strftime('%d/%m/%Y')}\n"
                                                      f"hora_atualizacao:{hora_atualizacao}")
                        save_local_file(STATE_FILE_REF_DATES, datas_referencia_content)
                        
                        st.cache_data.clear()
                        st.cache_resource.clear()
                        st.sidebar.success("Arquivos salvos! Recarregando...")
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
                commit_msg = f"Atualizando chamados fechados em {now_sao_paulo.strftime('%d/%m/%Y %H:%M')}"
                
                content_fechados = process_uploaded_file(uploaded_file_fechados)
                if content_fechados is None:
                    st.sidebar.error("Falha ao processar o arquivo de fechados.")
                    st.stop() 

                try:
                    save_local_file(f"{DATA_DIR}dados_fechados.csv", content_fechados, is_binary=True)

                    datas_existentes = read_local_text_file(STATE_FILE_REF_DATES)
                    data_atual_existente = datas_existentes.get('data_atual', 'N/A')
                    data_15dias_existente = datas_existentes.get('data_15dias', 'N/A')
                    hora_atualizacao_nova = now_sao_paulo.strftime('%H:%M')
                    today_snapshot_str = now_sao_paulo.strftime('%Y-%m-%d') # Data do sistema para o snapshot

                    datas_referencia_content_novo = (f"data_atual:{data_atual_existente}\n"
                                                       f"data_15dias:{data_15dias_existente}\n"
                                                       f"hora_atualizacao:{hora_atualizacao_nova}")
                    save_local_file(STATE_FILE_REF_DATES, datas_referencia_content_novo)
                    
                    df_atual_base = read_local_csv(f"{DATA_DIR}dados_atuais.csv")
                    if df_atual_base.empty:
                        st.sidebar.warning("Não foi possível ler o 'dados_atuais.csv' base para atualizar o snapshot.")
                        raise Exception("Arquivo 'dados_atuais.csv' base não encontrado.")
                    
                    # <<< INÍCIO DA LÓGICA DE HISTÓRICO CORRIGIDA >>>
                    
                    df_fechados_novo_upload = pd.read_csv(BytesIO(content_fechados), delimiter=';', dtype={'ID do ticket': str, 'ID do Ticket': str, 'ID': str})
                    
                    # <<< CORREÇÃO >>> Adicionando a definição de id_col_atual que faltava
                    id_col_atual = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_atual_base.columns), None)
                    if not id_col_atual:
                        st.sidebar.warning("Não foi possível encontrar coluna de ID no 'dados_atuais.csv' base.")
                        raise Exception("Coluna de ID não encontrada no 'dados_atuais.csv' base.")
                    # <<< FIM DA CORREÇÃO >>>
                        
                    id_col_upload = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_fechados_novo_upload.columns), None)
                    col_fechamento_upload = "Data de Fechamento" 
                    analista_col_name_origem = "Analista atribuído"
                    
                    if not id_col_upload:
                        raise Exception("Coluna de ID não encontrada no arquivo de fechados.")
                    
                    df_fechados_novo_upload[id_col_upload] = df_fechados_novo_upload[id_col_upload].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                    
                    if col_fechamento_upload in df_fechados_novo_upload.columns:
                        st.sidebar.info("Usando 'Data de Fechamento' do arquivo de upload.")
                        df_fechados_novo_upload['Data de Fechamento_dt'] = pd.to_datetime(df_fechados_novo_upload[col_fechamento_upload], errors='coerce')
                    else:
                        st.sidebar.warning(f"Coluna '{col_fechamento_upload}' não encontrada. Usando data de referência: {data_atual_existente}")
                        df_fechados_novo_upload['Data de Fechamento_dt'] = pd.to_datetime(data_atual_existente, format='%d/%m/%Y', errors='coerce')
                    
                    df_fechados_novo_upload['Data de Fechamento_str'] = df_fechados_novo_upload['Data de Fechamento_dt'].dt.strftime('%Y-%m-%d')
                    
                    df_historico_base = read_local_csv(STATE_FILE_MASTER_CLOSED_CSV)
                    
                    if not df_historico_base.empty:
                        id_col_hist = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_historico_base.columns), id_col_atual) # Usa id_col_atual como fallback
                        if id_col_hist != id_col_atual:
                            df_historico_base = df_historico_base.rename(columns={id_col_hist: id_col_atual})
                        df_historico_base[id_col_atual] = df_historico_base[id_col_atual].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                    
                    df_universo = pd.concat([df_atual_base, df_historico_base], ignore_index=True)
                    df_universo[id_col_atual] = df_universo[id_col_atual].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                    df_universo = df_universo.drop_duplicates(subset=[id_col_atual], keep='last')
                    
                    closed_ids_set_upload = set(df_fechados_novo_upload[id_col_upload].dropna().unique())
                    
                    df_encerrados_para_atualizar = df_universo[df_universo[id_col_atual].isin(closed_ids_set_upload)].copy()
                    
                    cols_para_merge = [id_col_upload, 'Data de Fechamento_str']
                    if analista_col_name_origem in df_fechados_novo_upload.columns:
                        cols_para_merge.append(analista_col_name_origem)

                    df_lookup = df_fechados_novo_upload[cols_para_merge].drop_duplicates(subset=[id_col_upload])
                    
                    if analista_col_name_origem in df_lookup.columns:
                         df_lookup[analista_col_name_origem] = df_lookup[analista_col_name_origem].astype(str).replace(r'\s+', ' ', regex=True).str.strip()

                    df_lookup = df_lookup.rename(columns={
                        id_col_upload: id_col_atual, 
                        'Data de Fechamento
