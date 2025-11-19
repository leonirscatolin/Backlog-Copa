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
# Removemos RH, Aprovadores e qualquer grupo que contenha "RDM"
REGEX_EXCLUSAO_PERMANENTE = r'RH|Aprovadores GGM|RDM' 
TEXTO_EXCLUSAO_PERMANENTE = "'RH', 'Aprovadores GGM' ou contendo 'RDM'"

# 1.2. FILTRO LÍQUIDO (Service Desk / L1 / Triagem)
# Estes chamados entram no sistema para ALERTA, mas são REMOVIDOS dos totais e gráficos
REGEX_FILTRO_LIQUIDO = r'Service Desk|LIQ-SUTEL'
TEXTO_GRUPOS_AVISO = "'Service Desk (L1)' ou 'LIQ-SUTEL'"

# Caminhos de Arquivos (CONSTANTES LIMPAS)
DATA_DIR = "data/"
FILE_ATUAL = f"{DATA_DIR}dados_atuais.csv"
FILE_15DIAS = f"{DATA_DIR}dados_15_dias.csv"
FILE_HISTORICO = f"{DATA_DIR}historico_fechados_master.csv"
FILE_CONTACTS = "contacted_tickets.json"
FILE_OBSERVATIONS = "ticket_observations.json"
FILE_REF_DATES = "datas_referencia.txt"
# REMOVIDO: FILE_PREV_CLOSED (Não é mais necessário nesta lógica unificada)

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
                    # Normalização imediata de IDs se existir coluna
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
        # Tenta detectar se é excel ou csv
        if uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file, dtype=str)
        else:
            # Fallback para CSV (tenta decodificar)
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
                # Limpa históricos anteriores
                if os.path.exists(FILE_HISTORICO): os.remove(FILE_HISTORICO)
                
                # Processa arquivos
                c_atual = process_uploaded_file(f_atual)
                c_15 = process_uploaded_file(f_15)
                
                if c_atual and c_15:
                    # Salva Dados Principais
                    save_local_file(FILE_ATUAL, c_atual, True)
                    save_local_file(FILE_15DIAS, c_15, True)
                    
                    # Salva Snapshots
                    hoje = datetime.now(ZoneInfo('America/Sao_Paulo'))
                    save_local_file(f"{DATA_DIR}snapshots/backlog_{hoje.strftime('%Y-%m-%d')}.csv", c_atual, True)
                    save_local_file(f"{DATA_DIR}snapshots/backlog_{(hoje - timedelta(days=15)).strftime('%Y-%m-%d')}.csv", c_15, True)
                    
                    # Atualiza Metadados
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
                    # Salva arquivo bruto
                    save_local_file(f"{DATA_DIR}dados_fechados.csv", c_closed, True)
                    
                    # Atualiza Histórico Mestre
                    df_new = pd.read_csv(BytesIO(c_closed), sep=';', dtype=str)
                    id_col = next((c for c in ['ID do ticket', 'ID do Ticket', 'ID'] if c in df_new.columns), None)
                    
                    if id_col:
                        df_new[id_col] = normalize_ids(df_new[id_col])
                        # Tenta carregar mestre existente
                        df_master = read_local_csv(FILE_HISTORICO, 0)
                        
                        # Normaliza colunas
                        col_map = {id_col: 'ID do ticket', 'Data de Fechamento': 'Data de Fechamento', 'Analista atribuído': 'Analista atribuído', 'Atribuir a um grupo': 'Atribuir a um grupo'}
                        # Renomeia o que encontrar
                        rename_real = {k: v for k, v in col_map.items() if k in df_new.columns}
                        df_part = df_new[list(rename_real.keys())].rename(columns=rename_real)
                        
                        # Concatena e Dedup
                        df_final = pd.concat([df_master, df_part]).drop_duplicates(subset=['ID do ticket'], keep='last')
                        
                        # Salva
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
    # Carregar Estados
    if 'contacted_tickets' not in st.session_state:
        st.session_state.contacted_tickets = set(read_local_json_file(FILE_CONTACTS, 'list'))
    if 'observations' not in st.session_state:
        st.session_state.observations = read_local_json_file(FILE_OBSERVATIONS, 'dict')
    if 'editor_key' not in st.session_state: st.session_state.editor_key = 0

    # Tratamento de URL Params (Filtro via Card)
    if "faixa" in st.query_params:
        st.session_state.faixa_selecionada = st.query_params.get("faixa")
        st.query_params.clear()

    # Leitura dos Arquivos Principais
    df_atual_raw = read_local_csv(FILE_ATUAL, get_file_mtime(FILE_ATUAL))
    df_15dias_raw = read_local_csv(FILE_15DIAS, get_file_mtime(FILE_15DIAS))
    df_hist_raw = read_local_csv(FILE_HISTORICO, get_file_mtime(FILE_HISTORICO))
    
    meta_dates = read_local_text_file(FILE_REF_DATES)

    if df_atual_raw.empty:
        st.warning("Aguardando dados. Realize o upload na barra lateral.")
        st.stop()

    # -------------------------------------------------------------------------
    # APLICAÇÃO CENTRALIZADA DE FILTROS (AQUI É O CORAÇÃO DA CORREÇÃO)
    # -------------------------------------------------------------------------
    
    # 1. Função Helper para aplicar exclusão permanente (RH, RDM)
    def aplicar_exclusao_permanente(df):
        if df.empty or 'Atribuir a um grupo' not in df.columns: return df
        # Garante que é string
        df['Atribuir a um grupo'] = df['Atribuir a um grupo'].astype(str)
        return df[~df['Atribuir a um grupo'].str.contains(REGEX_EXCLUSAO_PERMANENTE, case=False, na=False, regex=True)].copy()

    # 2. Função Helper para separar Backlog Líquido vs. Sujo (Service Desk)
    def separar_backlog_liquido(df):
        if df.empty or 'Atribuir a um grupo' not in df.columns: return df, pd.DataFrame()
        mask_aviso = df['Atribuir a um grupo'].str.contains(REGEX_FILTRO_LIQUIDO, case=False, na=False, regex=True)
        return df[~mask_aviso].copy(), df[mask_aviso].copy()

    # --- PROCESSAMENTO BACKLOG ATUAL ---
    # A. Remove fechados que ainda estão no arquivo de abertos (Sincronia)
    all_closed_ids = set()
    if not df_hist_raw.empty and 'ID do ticket' in df_hist_raw.columns:
        all_closed_ids = set(normalize_ids(df_hist_raw['ID do ticket']).unique())
    
    if 'ID do ticket' in df_atual_raw.columns:
        df_atual_raw = df_atual_raw[~normalize_ids(df_atual_raw['ID do ticket']).isin(all_closed_ids)]

    # B. Aplica filtros de Grupo
    df_atual_limpo_perm = aplicar_exclusao_permanente(df_atual_raw)
    df_atual_liquido, df_atual_aviso = separar_backlog_liquido(df_atual_limpo_perm) # <-- DADOS REAIS PARA O DASHBOARD

    # C. Processa Aging (Apenas do Líquido)
    date_str = meta_dates.get('data_atual')
    ref_date = datetime.strptime(date_str, '%d/%m/%Y') if date_str and date_str != 'N/A' else datetime.now()
    df_aging_liquido = analisar_aging(df_atual_liquido, ref_date)

    # --- PROCESSAMENTO HISTÓRICO DE FECHADOS ---
    df_hist_limpo_perm = aplicar_exclusao_permanente(df_hist_raw)
    df_hist_liquido, _ = separar_backlog_liquido(df_hist_limpo_perm) # <-- DADOS REAIS PARA GRÁFICOS E TABELA DE FECHADOS

    # --- KPI: FECHADOS HOJE (LÍQUIDO) ---
    # Garante que só conta se a data for *exatamente* hoje
    total_fechados_hoje = 0
    hoje_date = datetime.now(ZoneInfo('America/Sao_Paulo')).date()
    
    if not df_hist_liquido.empty and 'Data de Fechamento' in df_hist_liquido.columns:
        df_hist_liquido['dt_fechamento'] = pd.to_datetime(df_hist_liquido['Data de Fechamento'], dayfirst=True, errors='coerce')
        total_fechados_hoje = len(df_hist_liquido[df_hist_liquido['dt_fechamento'].dt.date == hoje_date])

    # --- EVOLUÇÃO 15 DIAS ---
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
    # 1. CAIXA AZUL DE INFORMAÇÕES E ALERTAS
    msgs = [
        "**Regras de Visualização (Backlog Líquido):**",
        f"- Chamados de {TEXTO_EXCLUSAO_PERMANENTE} foram removidos globalmente.",
        "- O 'Dias em Aberto' é calculado com base na data do relatório (D-0)."
    ]
    
    # Inserir aviso de Service Desk DENTRO da caixa azul
    qtd_aviso = len(df_atual_aviso)
    if qtd_aviso > 0:
        msgs.append("---")
        msgs.append(f"⚠️ **Atenção:** Existem **{qtd_aviso}** chamados de {TEXTO_GRUPOS_AVISO} que foram **excluídos** dos indicadores abaixo (não compõem o backlog líquido):")
        for g, c in df_atual_aviso['Atribuir a um grupo'].value_counts().items():
            msgs.append(f"- **{g}:** {c}")

    st.info("\n".join(msgs))

    # 2. KPIs PRINCIPAIS (Total Líquido e Fechados Hoje)
    c1, c2, c3, c4 = st.columns([1, 1.5, 1.5, 1])
    with c2:
        st.markdown(f"""<div class="metric-box"><span class="label">Backlog Líquido</span><span class="value">{len(df_aging_liquido)}</span></div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="metric-box"><span class="label">Fechados HOJE</span><span class="value">{total_fechados_hoje}</span></div>""", unsafe_allow_html=True)

    st.markdown("---")

    # 3. CARDS POR FAIXA (Usando df_aging_liquido)
    if not df_aging_liquido.empty:
        counts = df_aging_liquido['Faixa de Antiguidade'].value_counts().reset_index()
        counts.columns = ['Faixa', 'Qtd']
        ordem = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
        
        # Merge para garantir que todas as faixas apareçam, mesmo zeradas
        final_counts = pd.DataFrame({'Faixa': ordem}).merge(counts, on='Faixa', how='left').fillna(0)
        final_counts['Qtd'] = final_counts['Qtd'].astype(int)
        
        cols = st.columns(6)
        for i, row in final_counts.iterrows():
            with cols[i]:
                encoded = quote(row['Faixa'])
                st.markdown(f"""
                <a href="?faixa={encoded}&scroll=true" target="_self" class="metric-box">
                    <span class="label">{row['Faixa']}</span>
                    <span class="value">{row['Qtd']}</span>
                </a>
                """, unsafe_allow_html=True)

    # 4. TABELA DE COMPARAÇÃO (15 Dias)
    st.markdown(f"### Comparativo: Atual vs 15 Dias Atrás ({meta_dates.get('data_15dias', 'N/A')})")
    if not df_aging_liquido.empty and not df_15dias_liquido.empty:
        df_comp = processar_dados_comparativos(df_aging_liquido, df_15dias_liquido)
        df_comp['Status'] = df_comp.apply(lambda r: "Aumento" if r['Diferença'] > 0 else ("Redução" if r['Diferença'] < 0 else "Estável"), axis=1)
        st.dataframe(
            df_comp.set_index('Atribuir a um grupo').style.map(
                lambda v: 'background-color: #ffcccc' if v > 0 else ('background-color: #ccffcc' if v < 0 else ''), 
                subset=['Diferença']
            ),
            use_container_width=True
        )

    st.markdown("---")

    # 5. TABELA DE FECHADOS (Filtrada: Líquido Apenas)
    st.markdown("### Histórico Recente de Fechamentos (Líquido)")
    if not df_hist_liquido.empty:
        # Filtro de data
        datas = sorted(df_hist_liquido['dt_fechamento'].dropna().dt.date.unique(), reverse=True)
        if datas:
            sel_date = st.selectbox("Filtrar Data:", options=datas, format_func=lambda x: x.strftime('%d/%m/%Y'))
            
            # Aplica filtro de data na base LÍQUIDA
            df_show_closed = df_hist_liquido[df_hist_liquido['dt_fechamento'].dt.date == sel_date].copy()
            
            # Colunas para exibir
            cols_view = ['ID do ticket', 'Descrição', 'Atribuir a um grupo', 'Analista atribuído', 'Data de Fechamento']
            cols_final = [c for c in cols_view if c in df_show_closed.columns]
            
            st.dataframe(df_show_closed[cols_final], use_container_width=True, hide_index=True)
        else:
            st.warning("Sem datas válidas.")
    else:
        st.info("Sem histórico de fechados disponível.")

    st.markdown("---")
    
    # 6. DETALHE E BUSCA (Usando df_aging_liquido)
    st.subheader("Detalhar Backlog")
    
    # Auto-scroll logic
    if "scroll" in st.query_params:
        st.components.v1.html("<script>window.scrollTo({top: 800, behavior: 'smooth'});</script>", height=0)
    
    if 'faixa_selecionada' not in st.session_state: st.session_state.faixa_selecionada = "0-2 dias"

    st.selectbox("Selecione Faixa:", options=ordem, key="faixa_selecionada")
    
    df_detalhe = df_aging_liquido[df_aging_liquido['Faixa de Antiguidade'] == st.session_state.faixa_selecionada].copy()
    
    if not df_detalhe.empty:
        # Merge com contatos/obs
        df_detalhe['Contato'] = df_detalhe['ID do ticket'].apply(lambda x: x in st.session_state.contacted_tickets)
        df_detalhe['Observações'] = df_detalhe['ID do ticket'].apply(lambda x: st.session_state.observations.get(x, ''))
        
        # Salva referência para callback
        st.session_state.last_filtered_df = df_detalhe.reset_index(drop=True)
        
        # Editor
        cols_edit = ['Contato', 'ID do ticket', 'Descrição', 'Atribuir a um grupo', 'Dias em Aberto', 'Observações']
        cols_existing = [c for c in cols_edit if c in df_detalhe.columns]

        edited = st.data_editor(
            st.session_state.last_filtered_df[cols_existing],
            key=f"editor_{st.session_state.editor_key}",
            disabled=['ID do ticket', 'Descrição', 'Atribuir a um grupo', 'Dias em Aberto'],
            use_container_width=True,
            hide_index=True
        )
        
        # Botão Salvar (Sincroniza estado)
        if st.button("Salvar Alterações", type="primary"):
            # A função sync_ticket_data lê do st.session_state.editor_...
            # Precisamos garantir que o nome da chave bata com o esperado pela função sync_ticket_data
            # Mas como reescrevi a estrutura, vou chamar diretamente aqui:
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
    else:
        st.info("Nenhum chamado nesta faixa.")


# --- TAB 2: VISÃO GERENCIAL (Resumo Gráfico) ---
with tab2:
    if not df_aging_liquido.empty:
        st.subheader("Distribuição por Grupo")
        df_g = df_aging_liquido.groupby(['Atribuir a um grupo', 'Faixa de Antiguidade']).size().reset_index(name='Qtd')
        
        # Ordenação inteligente
        total_por_grupo = df_g.groupby('Atribuir a um grupo')['Qtd'].sum().sort_values(ascending=True)
        
        fig = px.bar(df_g, y='Atribuir a um grupo', x='Qtd', color='Faixa de Antiguidade', 
                     orientation='h', category_orders={'Atribuir a um grupo': total_por_grupo.index},
                     color_discrete_sequence=px.colors.sequential.Greens)
        fig.update_layout(height=600)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Sem dados.")

# --- TAB 3: EVOLUÇÃO ---
with tab3:
    st.subheader("Evolução Líquida (Últimos Dias)")
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
                # Aplica filtros
                df = aplicar_exclusao_permanente(df)
                df, _ = separar_backlog_liquido(df) # Pega só o liquido
                
                count = len(df)
                data.append({'Data': dt, 'Backlog': count, 'Tipo': 'Aberto'})
            except: continue
        return pd.DataFrame(data)
    
    df_evo = load_evolution_data(days)
    
    # Adiciona fechados do histórico líquido
    df_closed_evo = df_hist_liquido.copy()
    if not df_closed_evo.empty:
        df_closed_evo['Data'] = df_closed_evo['dt_fechamento'].dt.date
        daily_closed = df_closed_evo.groupby('Data').size().reset_index(name='Backlog')
        daily_closed['Tipo'] = 'Fechado'
        # Filtra datas
        min_date = datetime.now().date() - timedelta(days=days)
        daily_closed = daily_closed[daily_closed['Data'] >= min_date]
        
        df_evo = pd.concat([df_evo, daily_closed])
    
    if not df_evo.empty:
        fig_evo = px.line(df_evo.sort_values('Data'), x='Data', y='Backlog', color='Tipo', markers=True,
                          color_discrete_map={'Aberto': '#375623', 'Fechado': '#f28801'})
        st.plotly_chart(fig_evo, use_container_width=True)
    else:
        st.warning("Dados históricos insuficientes.")

# --- TAB 4: AGING ---
with tab4:
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

# Rodapé
st.markdown("---")
st.markdown("<div style='text-align: center; color: gray;'>V2.1 (Cleaned & Refactored) | Copa Energia</div>", unsafe_allow_html=True)
