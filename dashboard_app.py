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

# =============================================================================
# 1. CONFIGURAÇÕES E CONSTANTES GLOBAIS
# =============================================================================

# 1.1. EXCLUSÃO TOTAL (Lixo / Não é Backlog de TI)
REGEX_EXCLUSAO_PERMANENTE = r'RH|Aprovadores GGM|RDM' 
TEXTO_EXCLUSAO_PERMANENTE = "'RH', 'Aprovadores GGM' ou contendo 'RDM'"

# 1.2. FILTRO LÍQUIDO (Service Desk / L1 / Triagem)
REGEX_FILTRO_LIQUIDO = r'Service Desk|LIQ-SUTEL'
TEXTO_GRUPOS_AVISO = "'Service Desk (L1)' ou 'LIQ-SUTEL'"

# Regex combinado para funções que precisam limpar tudo de uma vez
REGEX_COMBINADO_TOTAL = f"{REGEX_EXCLUSAO_PERMANENTE}|{REGEX_FILTRO_LIQUIDO}"

# Caminhos de Arquivos
DATA_DIR = "data/"
FILE_ATUAL = f"{DATA_DIR}dados_atuais.csv"
FILE_15DIAS = f"{DATA_DIR}dados_15_dias.csv"
FILE_HISTORICO = f"{DATA_DIR}historico_fechados_master.csv"
FILE_CONTACTS = "contacted_tickets.json"
FILE_OBSERVATIONS = "ticket_observations.json"
FILE_REF_DATES = "datas_referencia.txt"

# =============================================================================
# 2. SETUP DA PÁGINA E CSS
# =============================================================================
st.set_page_config(
    layout="wide",
    page_title="Backlog Copa Energia + Belago",
    page_icon=f"{DATA_DIR}minilogo.png" if os.path.exists(f"{DATA_DIR}minilogo.png") else None,
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

# =============================================================================
# 3. FUNÇÕES UTILITÁRIAS (CORE)
# =============================================================================

def normalize_ids(series):
    """Padroniza IDs removendo .0 e espaços."""
    if series.empty: return series
    return series.astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

def get_file_mtime(file_path):
    return os.path.getmtime(file_path) if os.path.exists(file_path) else 0

def save_local_file(file_path, content, is_binary=False):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        mode = 'wb' if is_binary else 'w'
        encoding = None if is_binary else 'utf-8'
        with open(file_path, mode, encoding=encoding) as f:
            f.write(content)
    except Exception as e:
        st.error(f"Erro ao salvar {file_path}: {e}")

@st.cache_data
def read_local_csv(file_path, file_mtime):
    if not os.path.exists(file_path): return pd.DataFrame()
    for sep in [';', ',']:
        for enc in ['utf-8', 'latin1']:
            try:
                df = pd.read_csv(file_path, sep=sep, encoding=enc,
                                 dtype={'ID do ticket': str, 'ID do Ticket': str, 'ID': str}, 
                                 low_memory=False, on_bad_lines='warn')
                if df.shape[1] > 1:
                    df.columns = df.columns.str.strip()
                    df = df.loc[:, ~df.columns.duplicated()]
                    df.dropna(how='all', inplace=True)
                    id_col = next((c for c in ['ID do ticket', 'ID do Ticket', 'ID'] if c in df.columns), None)
                    if id_col: df[id_col] = normalize_ids(df[id_col])
                    return df
            except: continue
    return pd.DataFrame()

@st.cache_data
def read_local_text_file(file_path):
    if not os.path.exists(file_path): return {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return dict(line.split(':', 1) for line in content.strip().split('\n') if ':' in line)
    except: return {}

@st.cache_data
def read_local_json_file(file_path, default_return_type='dict'):
    if not os.path.exists(file_path): return {} if default_return_type == 'dict' else []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.loads(f.read())
    except: return {} if default_return_type == 'dict' else []

def get_image_as_base64(path):
    if not os.path.exists(path): return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def categorizar_idade_vetorizado(dias_series):
    condicoes = [
        dias_series >= 30, (dias_series >= 21) & (dias_series <= 29),
        (dias_series >= 11) & (dias_series <= 20), (dias_series >= 6) & (dias_series <= 10),
        (dias_series >= 3) & (dias_series <= 5), (dias_series >= 0) & (dias_series <= 2)
    ]
    opcoes = ["30+ dias", "21-29 dias", "11-20 dias", "6-10 dias", "3-5 dias", "0-2 dias"]
    return np.select(condicoes, opcoes, default="Erro")

@st.cache_data
def analisar_aging(df_in, reference_date=None):
    df = df_in.copy()
    date_col = next((c for c in ['Data de criação', 'Data de Criacao', 'Created', 'Aberto em'] if c in df.columns), None)
    if not date_col: return pd.DataFrame()
    
    df['dt_temp'] = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['dt_temp'])
    
    ref = pd.to_datetime(reference_date).normalize() if reference_date else pd.to_datetime('today').normalize()
    df['Dias em Aberto'] = (ref - df['dt_temp'].dt.normalize()).dt.days.clip(lower=0)
    df['Faixa de Antiguidade'] = categorizar_idade_vetorizado(df['Dias em Aberto'])
    return df.drop(columns=['dt_temp'])

def process_uploaded_file(uploaded_file):
    if not uploaded_file: return None
    try:
        content = uploaded_file.getvalue()
        if uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file, dtype=str)
        else:
            try: s = content.decode('utf-8')
            except: s = content.decode('latin1')
            try: df = pd.read_csv(StringIO(s), sep=';', dtype=str)
            except: df = pd.read_csv(StringIO(s), sep=',', dtype=str)
            
        output = StringIO()
        df.to_csv(output, index=False, sep=';', encoding='utf-8')
        return output.getvalue().encode('utf-8')
    except Exception as e:
        st.sidebar.error(f"Erro: {e}")
        return None

# --- FUNÇÕES RESTAURADAS ---

def processar_dados_comparativos(df_atual, df_15dias):
    """Gera dataframe comparativo para a tabela da Tab 1."""
    contagem_atual = df_atual.groupby('Atribuir a um grupo').size().reset_index(name='Atual')
    contagem_15dias = df_15dias.groupby('Atribuir a um grupo').size().reset_index(name='15 Dias Atrás')
    df_comparativo = pd.merge(contagem_atual, contagem_15dias, on='Atribuir a um grupo', how='outer').fillna(0)
    df_comparativo['Diferença'] = df_comparativo['Atual'] - df_comparativo['15 Dias Atrás']
    df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']] = df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']].astype(int)
    return df_comparativo

def formatar_delta_card(delta_abs, delta_perc, valor_comparacao, data_comparacao_str):
    """Formata o texto de variação para os cards de Aging."""
    delta_abs = int(delta_abs)
    if valor_comparacao > 0:
        delta_perc_str = f"{delta_perc * 100:.1f}%"
        delta_text = f"{delta_abs:+} ({delta_perc_str}) vs. {data_comparacao_str}"
    elif valor_comparacao == 0 and delta_abs > 0:
        delta_text = f"+{delta_abs} (Novo) vs. {data_comparacao_str}"
    else:
        delta_text = f"{delta_abs} vs. {data_comparacao_str}"

    if delta_abs > 0: delta_class = "delta-positive"
    elif delta_abs < 0: delta_class = "delta-negative"
    else: delta_class = "delta-neutral"
    return delta_text, delta_class

@st.cache_data
def find_closest_snapshot_before(current_report_date, target_date):
    """Encontra o arquivo de snapshot mais próximo da data alvo."""
    try:
        snapshot_dir = f"{DATA_DIR}snapshots"
        if not os.path.exists(snapshot_dir): return None, None
        local_files = [os.path.join(snapshot_dir, f) for f in os.listdir(snapshot_dir) if f.endswith('.csv')]
        
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
    except: return None, None

@st.cache_data
def carregar_evolucao_aging(dias_para_analisar=90):
    """Carrega histórico de aging dos snapshots, aplicando filtro LÍQUIDO."""
    try:
        snapshot_dir = f"{DATA_DIR}snapshots"
        if not os.path.exists(snapshot_dir): return pd.DataFrame()
        
        local_files = [os.path.join(snapshot_dir, f) for f in os.listdir(snapshot_dir) if f.endswith('.csv')]
        processed_files = []
        
        end_date = date.today()
        start_date = end_date - timedelta(days=max(dias_para_analisar, 60))
        
        for file_name in local_files:
            if "backlog_" in file_name:
                try:
                    date_str = file_name.split("backlog_")[1].replace(".csv", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if start_date <= file_date <= end_date:
                        processed_files.append((file_date, file_name))
                except: continue
        
        processed_files.sort(key=lambda x: x[0])
        lista_historico = []
        
        for file_date, file_name in processed_files:
            try:
                df_snapshot = read_local_csv(file_name, 0)
                if df_snapshot.empty: continue
                
                # APLICA FILTRO LÍQUIDO (Tudo que não é TI)
                if 'Atribuir a um grupo' in df_snapshot.columns:
                    df_snapshot = df_snapshot[~df_snapshot['Atribuir a um grupo'].astype(str).str.contains(REGEX_COMBINADO_TOTAL, case=False, na=False, regex=True)]
                
                date_col = next((c for c in ['Data de criação', 'Data de Criacao'] if c in df_snapshot.columns), None)
                if not date_col: continue
                
                # Recalcula aging
                df_snapshot['temp_date'] = pd.to_datetime(df_snapshot[date_col], errors='coerce')
                df_snapshot.dropna(subset=['temp_date'], inplace=True)
                
                snap_dt = pd.to_datetime(file_date)
                days = (snap_dt - df_snapshot['temp_date'].dt.normalize()).dt.days.clip(lower=0)
                
                faixas = categorizar_idade_vetorizado(days)
                contagem = pd.Series(faixas).value_counts().reset_index()
                contagem.columns = ['Faixa de Antiguidade', 'total']
                contagem['data'] = snap_dt
                lista_historico.append(contagem)
            except: continue
            
        if not lista_historico: return pd.DataFrame()
        return pd.concat(lista_historico, ignore_index=True)
    except: return pd.DataFrame()

# =============================================================================
# 4. LÓGICA DO ADMINISTRADOR (SIDEBAR)
# =============================================================================
logo_copa = get_image_as_base64(f"{DATA_DIR}logo_sidebar.png")
logo_belago = get_image_as_base64(f"{DATA_DIR}logo_belago.png")
header_html = f"""
<div style="display: flex; justify-content: space-between; align-items: center;">
    <img src="data:image/png;base64,{logo_copa}" width="120">
    <h2 style='text-align: center; margin: 0; font-size: 1.5em;'>Backlog Copa Energia</h2>
    <img src="data:image/png;base64,{logo_belago}" width="120">
</div>
""" if logo_copa and logo_belago else "<h1>Backlog Copa Energia</h1>"
st.markdown(header_html, unsafe_allow_html=True)

st.sidebar.header("Área do Administrador")
password = st.sidebar.text_input("Senha:", type="password")
is_admin = password == st.secrets.get("ADMIN_PASSWORD", "admin123")

if is_admin:
    st.sidebar.success("Admin Logado")
    st.sidebar.subheader("1. Atualização Completa (Backlog)")
    f_atual = st.sidebar.file_uploader("Backlog ATUAL", type=["csv", "xlsx"], key="u1")
    f_15 = st.sidebar.file_uploader("Backlog 15 DIAS", type=["csv", "xlsx"], key="u2")
    
    if st.sidebar.button("Processar Backlog Completo"):
        if f_atual and f_15:
            with st.spinner("Processando..."):
                if os.path.exists(FILE_HISTORICO): os.remove(FILE_HISTORICO)
                
                c_atual = process_uploaded_file(f_atual)
                c_15 = process_uploaded_file(f_15)
                
                if c_atual and c_15:
                    save_local_file(FILE_ATUAL, c_atual, True)
                    save_local_file(FILE_15DIAS, c_15, True)
                    
                    hoje = datetime.now(ZoneInfo('America/Sao_Paulo'))
                    save_local_file(f"{DATA_DIR}snapshots/backlog_{hoje.strftime('%Y-%m-%d')}.csv", c_atual, True)
                    save_local_file(f"{DATA_DIR}snapshots/backlog_{(hoje - timedelta(days=15)).strftime('%Y-%m-%d')}.csv", c_15, True)
                    
                    meta = f"data_atual:{hoje.strftime('%d/%m/%Y')}\ndata_15dias:{(hoje - timedelta(days=15)).strftime('%d/%m/%Y')}\nhora_atualizacao:{hoje.strftime('%H:%M')}"
                    save_local_file(FILE_REF_DATES, meta)
                    
                    st.cache_data.clear()
                    st.rerun()
        else:
            st.sidebar.warning("Carregue os dois arquivos.")

    st.sidebar.markdown("---")
    st.sidebar.subheader("2. Atualização Rápida (Fechados)")
    f_closed = st.sidebar.file_uploader("Fechados HOJE", type=["csv", "xlsx"], key="u3")
    
    if st.sidebar.button("Processar Fechados"):
        if f_closed:
            with st.spinner("Atualizando fechados..."):
                c_closed = process_uploaded_file(f_closed)
                if c_closed:
                    save_local_file(f"{DATA_DIR}dados_fechados.csv", c_closed, True)
                    
                    df_new = pd.read_csv(BytesIO(c_closed), sep=';', dtype=str)
                    id_col = next((c for c in ['ID do ticket', 'ID do Ticket', 'ID'] if c in df_new.columns), None)
                    
                    if id_col:
                        df_new[id_col] = normalize_ids(df_new[id_col])
                        df_master = read_local_csv(FILE_HISTORICO, 0)
                        
                        col_map = {id_col: 'ID do ticket', 'Data de Fechamento': 'Data de Fechamento', 'Analista atribuído': 'Analista atribuído', 'Atribuir a um grupo': 'Atribuir a um grupo'}
                        rename_real = {k: v for k, v in col_map.items() if k in df_new.columns}
                        df_part = df_new[list(rename_real.keys())].rename(columns=rename_real)
                        
                        df_final = pd.concat([df_master, df_part]).drop_duplicates(subset=['ID do ticket'], keep='last')
                        
                        out = StringIO()
                        df_final.to_csv(out, index=False, sep=';')
                        save_local_file(FILE_HISTORICO, out.getvalue().encode('utf-8'), True)
                        
                        st.success("Histórico atualizado!")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("Coluna de ID não encontrada.")

# =============================================================================
# 5. CARREGAMENTO E PROCESSAMENTO DE DADOS (FRONTEND)
# =============================================================================

try:
    if 'contacted_tickets' not in st.session_state:
        st.session_state.contacted_tickets = set(read_local_json_file(FILE_CONTACTS, 'list'))
    if 'observations' not in st.session_state:
        st.session_state.observations = read_local_json_file(FILE_OBSERVATIONS, 'dict')
    if 'editor_key' not in st.session_state: st.session_state.editor_key = 0

    if "faixa" in st.query_params:
        st.session_state.faixa_selecionada = st.query_params.get("faixa")
        st.query_params.clear()

    df_atual_raw = read_local_csv(FILE_ATUAL, get_file_mtime(FILE_ATUAL))
    df_15dias_raw = read_local_csv(FILE_15DIAS, get_file_mtime(FILE_15DIAS))
    df_hist_raw = read_local_csv(FILE_HISTORICO, get_file_mtime(FILE_HISTORICO))
    
    meta_dates = read_local_text_file(FILE_REF_DATES)

    if df_atual_raw.empty:
        st.warning("Aguardando dados. Realize o upload na barra lateral.")
        st.stop()

    def aplicar_exclusao_permanente(df):
        if df.empty or 'Atribuir a um grupo' not in df.columns: return df
        df['Atribuir a um grupo'] = df['Atribuir a um grupo'].astype(str)
        return df[~df['Atribuir a um grupo'].str.contains(REGEX_EXCLUSAO_PERMANENTE, case=False, na=False, regex=True)].copy()

    def separar_backlog_liquido(df):
        if df.empty or 'Atribuir a um grupo' not in df.columns: return df, pd.DataFrame()
        mask_aviso = df['Atribuir a um grupo'].str.contains(REGEX_FILTRO_LIQUIDO, case=False, na=False, regex=True)
        return df[~mask_aviso].copy(), df[mask_aviso].copy()

    # --- PROCESSAMENTO ---
    all_closed_ids = set()
    if not df_hist_raw.empty and 'ID do ticket' in df_hist_raw.columns:
        all_closed_ids = set(normalize_ids(df_hist_raw['ID do ticket']).unique())
    
    if 'ID do ticket' in df_atual_raw.columns:
        df_atual_raw = df_atual_raw[~normalize_ids(df_atual_raw['ID do ticket']).isin(all_closed_ids)]

    df_atual_limpo_perm = aplicar_exclusao_permanente(df_atual_raw)
    df_atual_liquido, df_atual_aviso = separar_backlog_liquido(df_atual_limpo_perm)

    date_str = meta_dates.get('data_atual')
    ref_date = datetime.strptime(date_str, '%d/%m/%Y') if date_str and date_str != 'N/A' else datetime.now()
    df_aging_liquido = analisar_aging(df_atual_liquido, ref_date)

    df_hist_limpo_perm = aplicar_exclusao_permanente(df_hist_raw)
    df_hist_liquido, _ = separar_backlog_liquido(df_hist_limpo_perm)

    total_fechados_hoje = 0
    hoje_date = datetime.now(ZoneInfo('America/Sao_Paulo')).date()
    
    if not df_hist_liquido.empty and 'Data de Fechamento' in df_hist_liquido.columns:
        df_hist_liquido['dt_fechamento'] = pd.to_datetime(df_hist_liquido['Data de Fechamento'], dayfirst=True, errors='coerce')
        total_fechados_hoje = len(df_hist_liquido[df_hist_liquido['dt_fechamento'].dt.date == hoje_date])

    df_15dias_limpo_perm = aplicar_exclusao_permanente(df_15dias_raw)
    df_15dias_liquido, _ = separar_backlog_liquido(df_15dias_limpo_perm)

except Exception as e:
    st.error(f"Erro crítico no processamento de dados: {e}")
    st.stop()

# =============================================================================
# 6. CONSTRUÇÃO DAS ABAS
# =============================================================================

tab1, tab2, tab3, tab4 = st.tabs(["Dashboard Operacional", "Visão Gerencial", "Evolução", "Análise de Aging"])

# --- TAB 1: DASHBOARD OPERACIONAL ---
with tab1:
    msgs = [
        "**Regras de Visualização (Backlog Líquido):**",
        f"- Chamados de {TEXTO_EXCLUSAO_PERMANENTE} foram removidos globalmente.",
        "- O 'Dias em Aberto' é calculado com base na data do relatório (D-0)."
    ]
    qtd_aviso = len(df_atual_aviso)
    if qtd_aviso > 0:
        msgs.append("---")
        msgs.append(f"⚠️ **Atenção:** Existem **{qtd_aviso}** chamados de {TEXTO_GRUPOS_AVISO} que foram **excluídos** dos indicadores abaixo:")
        for g, c in df_atual_aviso['Atribuir a um grupo'].value_counts().items():
            msgs.append(f"- **{g}:** {c}")
    st.info("\n".join(msgs))

    c1, c2, c3, c4 = st.columns([1, 1.5, 1.5, 1])
    with c2: st.markdown(f"""<div class="metric-box"><span class="label">Backlog Líquido</span><span class="value">{len(df_aging_liquido)}</span></div>""", unsafe_allow_html=True)
    with c3: st.markdown(f"""<div class="metric-box"><span class="label">Fechados HOJE</span><span class="value">{total_fechados_hoje}</span></div>""", unsafe_allow_html=True)
    st.markdown("---")

    if not df_aging_liquido.empty:
        counts = df_aging_liquido['Faixa de Antiguidade'].value_counts().reset_index()
        counts.columns = ['Faixa', 'Qtd']
        ordem = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
        final_counts = pd.DataFrame({'Faixa': ordem}).merge(counts, on='Faixa', how='left').fillna(0)
        final_counts['Qtd'] = final_counts['Qtd'].astype(int)
        cols = st.columns(6)
        for i, row in final_counts.iterrows():
            with cols[i]:
                encoded = quote(row['Faixa'])
                st.markdown(f"""<a href="?faixa={encoded}&scroll=true" target="_self" class="metric-box"><span class="label">{row['Faixa']}</span><span class="value">{row['Qtd']}</span></a>""", unsafe_allow_html=True)

    st.markdown(f"### Comparativo: Atual vs 15 Dias Atrás ({meta_dates.get('data_15dias', 'N/A')})")
    if not df_aging_liquido.empty and not df_15dias_liquido.empty:
        df_comp = processar_dados_comparativos(df_aging_liquido, df_15dias_liquido)
        df_comp['Status'] = df_comp.apply(lambda r: "Aumento" if r['Diferença'] > 0 else ("Redução" if r['Diferença'] < 0 else "Estável"), axis=1)
        st.dataframe(df_comp.set_index('Atribuir a um grupo').style.map(lambda v: 'background-color: #ffcccc' if v > 0 else ('background-color: #ccffcc' if v < 0 else ''), subset=['Diferença']), use_container_width=True)

    st.markdown("---")
    st.markdown("### Histórico Recente de Fechamentos (Líquido)")
    if not df_hist_liquido.empty:
        datas = sorted(df_hist_liquido['dt_fechamento'].dropna().dt.date.unique(), reverse=True)
        if datas:
            sel_date = st.selectbox("Filtrar Data:", options=datas, format_func=lambda x: x.strftime('%d/%m/%Y'))
            df_show_closed = df_hist_liquido[df_hist_liquido['dt_fechamento'].dt.date == sel_date].copy()
            cols_view = ['ID do ticket', 'Descrição', 'Atribuir a um grupo', 'Analista atribuído', 'Data de Fechamento']
            cols_final = [c for c in cols_view if c in df_show_closed.columns]
            st.dataframe(df_show_closed[cols_final], use_container_width=True, hide_index=True)
        else: st.warning("Sem datas válidas.")
    else: st.info("Sem histórico de fechados disponível.")

    st.markdown("---")
    st.subheader("Detalhar Backlog")
    if "scroll" in st.query_params:
        st.components.v1.html("<script>window.scrollTo({top: 800, behavior: 'smooth'});</script>", height=0)
    if 'faixa_selecionada' not in st.session_state: st.session_state.faixa_selecionada = "0-2 dias"
    st.selectbox("Selecione Faixa:", options=ordem, key="faixa_selecionada")
    df_detalhe = df_aging_liquido[df_aging_liquido['Faixa de Antiguidade'] == st.session_state.faixa_selecionada].copy()
    if not df_detalhe.empty:
        df_detalhe['Contato'] = df_detalhe['ID do ticket'].apply(lambda x: x in st.session_state.contacted_tickets)
        df_detalhe['Observações'] = df_detalhe['ID do ticket'].apply(lambda x: st.session_state.observations.get(x, ''))
        st.session_state.last_filtered_df = df_detalhe.reset_index(drop=True)
        cols_edit = ['Contato', 'ID do ticket', 'Descrição', 'Atribuir a um grupo', 'Dias em Aberto', 'Observações']
        cols_existing = [c for c in cols_edit if c in df_detalhe.columns]
        edited = st.data_editor(st.session_state.last_filtered_df[cols_existing], key=f"editor_{st.session_state.editor_key}", disabled=['ID do ticket', 'Descrição', 'Atribuir a um grupo', 'Dias em Aberto'], use_container_width=True, hide_index=True)
        if st.button("Salvar Alterações", type="primary"):
            edited_rows = st.session_state[f"editor_{st.session_state.editor_key}"].get('edited_rows', {})
            changed = False
            for idx, changes in edited_rows.items():
                row_data = st.session_state.last_filtered_df.iloc[int(idx)]
                tid = str(row_data['ID do ticket'])
                if 'Contato' in changes:
                    if changes['Contato']: st.session_state.contacted_tickets.add(tid)
                    else: st.session_state.contacted_tickets.discard(tid)
                    changed = True
                if 'Observações' in changes:
                    st.session_state.observations[tid] = changes['Observações']
                    changed = True
            if changed:
                save_local_file(FILE_CONTACTS, json.dumps(list(st.session_state.contacted_tickets)))
                save_local_file(FILE_OBSERVATIONS, json.dumps(st.session_state.observations))
                st.session_state.editor_key += 1
                st.toast("Salvo com sucesso!")
                st.rerun()
    else: st.info("Nenhum chamado nesta faixa.")

# --- TAB 2: VISÃO GERENCIAL ---
with tab2:
    if not df_aging_liquido.empty:
        st.subheader("Distribuição por Grupo")
        df_g = df_aging_liquido.groupby(['Atribuir a um grupo', 'Faixa de Antiguidade']).size().reset_index(name='Qtd')
        total_por_grupo = df_g.groupby('Atribuir a um grupo')['Qtd'].sum().sort_values(ascending=True)
        fig = px.bar(df_g, y='Atribuir a um grupo', x='Qtd', color='Faixa de Antiguidade', orientation='h', category_orders={'Atribuir a um grupo': total_por_grupo.index}, color_discrete_sequence=px.colors.sequential.Greens)
        fig.update_layout(height=600)
        st.plotly_chart(fig, use_container_width=True)
    else: st.warning("Sem dados.")

# --- TAB 3: EVOLUÇÃO ---
with tab3:
    st.subheader("Evolução Líquida")
    days = st.slider("Dias:", 7, 30, 15)
    
    @st.cache_data
    def load_evolution_data(days):
        if not os.path.exists(f"{DATA_DIR}snapshots"): return pd.DataFrame()
        files = sorted([f for f in os.listdir(f"{DATA_DIR}snapshots") if f.endswith('.csv')], reverse=True)[:days]
        data = []
        for f in files:
            dt_str = f.replace('backlog_', '').replace('.csv', '')
            try:
                dt = datetime.strptime(dt_str, '%Y-%m-%d').date()
                df = read_local_csv(f"{DATA_DIR}snapshots/{f}", 0)
                df = aplicar_exclusao_permanente(df)
                df, _ = separar_backlog_liquido(df)
                data.append({'Data': dt, 'Backlog': len(df), 'Tipo': 'Aberto'})
            except: continue
        return pd.DataFrame(data)
    
    df_evo = load_evolution_data(days)
    if not df_hist_liquido.empty:
        daily_closed = df_hist_liquido.groupby(df_hist_liquido['dt_fechamento'].dt.date).size().reset_index(name='Backlog')
        daily_closed.columns = ['Data', 'Backlog']
        daily_closed['Tipo'] = 'Fechado'
        df_evo = pd.concat([df_evo, daily_closed[daily_closed['Data'] >= (datetime.now().date() - timedelta(days=days))]])
    
    if not df_evo.empty:
        fig_evo = px.line(df_evo.sort_values('Data'), x='Data', y='Backlog', color='Tipo', markers=True, color_discrete_map={'Aberto': '#375623', 'Fechado': '#f28801'})
        st.plotly_chart(fig_evo, use_container_width=True)
    else: st.warning("Dados insuficientes.")

# --- TAB 4: AGING EVOLUÇÃO ---
with tab4:
    try:
        df_hist_aging = carregar_evolucao_aging(90)
        if not df_hist_aging.empty:
             # Adicionar dados de hoje
            counts_now = df_aging_liquido['Faixa de Antiguidade'].value_counts().reset_index()
            counts_now.columns = ['Faixa de Antiguidade', 'total']
            counts_now['data'] = pd.to_datetime(date.today())
            df_full_aging = pd.concat([df_hist_aging, counts_now], ignore_index=True)
            
            st.markdown("##### Evolução do Aging")
            fig_aging = px.area(df_full_aging, x='data', y='total', color='Faixa de Antiguidade', category_orders={'Faixa de Antiguidade': ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]}, color_discrete_sequence=px.colors.sequential.Greens)
            st.plotly_chart(fig_aging, use_container_width=True)
            
            # Cards Comparativos
            st.markdown("##### Comparativo vs Ontem")
            cols = st.columns(6)
            ontem = pd.to_datetime(date.today() - timedelta(days=1))
            df_ontem = df_full_aging[df_full_aging['data'] == ontem]
            
            for i, faixa in enumerate(["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]):
                val_hoje = counts_now[counts_now['Faixa de Antiguidade'] == faixa]['total'].sum()
                val_ontem = df_ontem[df_ontem['Faixa de Antiguidade'] == faixa]['total'].sum() if not df_ontem.empty else 0
                delta_text, delta_class = formatar_delta_card(val_hoje - val_ontem, 0, val_ontem, "Ontem")
                with cols[i]:
                    st.markdown(f"""<div class="metric-box"><span class="label">{faixa}</span><span class="value">{int(val_hoje)}</span><span class="delta {delta_class}">{delta_text}</span></div>""", unsafe_allow_html=True)
        else:
            st.info("Coletando histórico de aging...")
    except Exception as e: st.error(f"Erro no Aging: {e}")

st.markdown("---")
st.markdown("<div style='text-align: center; color: gray;'>V2.2 (Versão Final Corrigida) | Copa Energia</div>", unsafe_allow_html=True)
