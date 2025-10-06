import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import base64
from datetime import datetime
import json
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
import traceback

# --- Configuração da Página ---
st.set_page_config(
    layout="wide", 
    page_title="Backlog Copa Energia + Belago",
    page_icon="copaenergialogo_1691612041.webp"
)

# --- FUNÇÕES ---
# REMOVIDO o @st.cache_resource para forçar o erro a aparecer
def connect_gsheets():
    creds_json = json.loads(st.secrets["gcp_creds"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"]
    creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open("Historico_Backlog")
    return spreadsheet.worksheet("Página1")

def update_history(worksheet, total_chamados):
    hoje_str = datetime.now().strftime("%d/%m/%Y")
    all_values = worksheet.get_all_values()
    dates_in_sheet = [row[0] for row in all_values[1:]]
    if hoje_str in dates_in_sheet:
        return
    new_row = [hoje_str, total_chamados]
    worksheet.append_row(new_row)

def get_history(worksheet):
    df = get_as_dataframe(worksheet, parse_dates=True, usecols=[0,1])
    df.dropna(subset=['Data'], inplace=True)
    df['Total_Chamados'] = pd.to_numeric(df['Total_Chamados'])
    return df
    
def get_base_64_of_bin_file(bin_file):
    try:
        with open(bin_file, 'rb') as f: data = f.read()
        return base64.b64encode(data).decode()
    except FileNotFoundError: return None

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
        (dias_series >= 3) & (dias_series <= 5), (dias_series >= 1) & (dias_series <= 2)
    ]
    opcoes = ["30+ dias", "21-29 dias", "11-20 dias", "6-10 dias", "3-5 dias", "1-2 dias"]
    return np.select(condicoes, opcoes, default="Erro de Categoria")

def analisar_aging(df_atual):
    df = df_atual.copy()
    df['Data de criação'] = pd.to_datetime(df['Data de criação'], errors='coerce', dayfirst=True)
    df.dropna(subset=['Data de criação'], inplace=True)
    hoje = pd.to_datetime('today').normalize()
    data_criacao_normalizada = df['Data de criação'].dt.normalize()
    df['Dias em Aberto'] = (hoje - data_criacao_normalizada).dt.days + 1
    df['Faixa de Antiguidade'] = categorizar_idade_vetorizado(df['Dias em Aberto'])
    return df

def get_status(row):
    diferenca = row['Diferença']
    if diferenca > 0:
        return "Alta Demanda"
    elif diferenca == 0:
        return "Estável / Atenção"
    else: # diferenca < 0
        return "Redução de Backlog"

# --- INTERFACE DO APLICATIVO ---
st.title("Backlog Copa Energia + Belago")

gif_path = "237f1d13493514962376f142bb68_1691760314.gif"
belago_logo_path = "logo_belago.png"
gif_base64 = get_base_64_of_bin_file(gif_path)
belago_logo_base64 = get_base_64_of_bin_file(belago_logo_path)
if gif_base64 and belago_logo_base64:
    st.sidebar.markdown(
        f"""
        <div style="text-align: center;">
            <img src="data:image/gif;base64,{gif_base64}" alt="Logo Copa Energia" style="width: 100%; border-radius: 15px; margin-bottom: 20px;">
            <img src="data:image/png;base64,{belago_logo_base64}" alt="Logo Belago" style="width: 80%; border-radius: 15px;">
        </div>
        """,
        unsafe_allow_html=True,
    )

st.sidebar.header("Carregar Arquivos")
uploaded_file_atual = st.sidebar.file_uploader("1. Backlog ATUAL (.csv)", type="csv")
uploaded_file_15dias = st.sidebar.file_uploader("2. Backlog de 15 DIAS ATRÁS (.csv)", type="csv")

if uploaded_file_atual and uploaded_file_15dias:
    try:
        df_atual = pd.read_csv(uploaded_file_atual, delimiter=';', encoding='latin1') 
        df_15dias = pd.read_csv(uploaded_file_15dias, delimiter=';', encoding='latin1')
        
        df_atual_filtrado = df_atual[~df_atual['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
        df_15dias_filtrado = df_15dias[~df_15dias['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
        
        df_aging = analisar_aging(df_atual_filtrado)

        st.markdown("""
        <style>
        .metric-box {
            border: 1px solid #CCCCCC; padding: 10px; border-radius: 5px; text-align: center; 
            box-shadow: 0px 2px 4px rgba(0,0,0,0.1); margin-bottom: 10px;
        }
        .metric-box .value {font-size: 2.5em; font-weight: bold; color: #375623;}
        .metric-box .label {font-size: 1em; color: #666666;}
        </style>
        """, unsafe_allow_html=True)

        tab1, tab2 = st.tabs(["Dashboard Completo", "Report Visual"])

        with tab1:
            st.info(
                """
                **Filtros e Regras Aplicadas:**
                - Grupos contendo 'RH' foram desconsiderados da análise.
                - A contagem de 'Dias em Aberto' considera o dia da criação como Dia 1.
                """
            )
            st.subheader("Análise de Antiguidade do Backlog Atual")
            
            if not df_aging.empty:
                total_chamados = len(df_aging)
                _, col_total, _ = st.columns([2, 1.5, 2])
                with col_total:
                    st.markdown(f"""...""") # Omitido
                st.markdown("---")
                
                # ... (código dos cards de KPI de antiguidade)
            else:
                st.warning("Nenhum dado válido para a análise de antiguidade.")

            st.subheader("Comparativo de Backlog: Atual vs. 15 Dias Atrás")
            df_comparativo = processar_dados_comparativos(df_atual_filtrado.copy(), df_15dias_filtrado.copy())
            df_comparativo['Status'] = df_comparativo.apply(get_status, axis=1)
            df_comparativo.rename(columns={'Atribuir a um grupo': 'Grupo'}, inplace=True)
            st.dataframe(df_comparativo.set_index('Grupo').style.map(lambda val: 'background-color: #ffcccc' if val > 0 else ('background-color: #ccffcc' if val < 0 else 'background-color: white'), subset=['Diferença']), use_container_width=True)

            if not df_aging.empty:
                st.markdown("---") 
                st.subheader("Detalhar e Buscar Chamados")
                # ... (código dos filtros de busca)
        
        with tab2:
            st.subheader("Resumo do Backlog Atual")
            if not df_aging.empty:
                total_chamados = len(df_aging)
                _, col_total_tab2, _ = st.columns([2, 1.5, 2])
                with col_total_tab2:
                    st.markdown(f"""...""") # Omitido
                st.markdown("---")
                
                # ... (código dos cards e top ofensores)
                
                st.markdown("---")
                st.subheader("Evolução do Histórico de Backlog")
                
                try:
                    worksheet = connect_gsheets()
                    update_history(worksheet, total_chamados)
                    df_historico = get_history(worksheet)
                    if not df_historico.empty:
                        df_historico = df_historico.sort_values(by='Data')
                        fig_historico = px.line(df_historico, x='Data', y='Total_Chamados', title="Total de chamados em aberto por dia", labels={'Data': 'Data', 'Total_Chamados': 'Total'}, markers=True)
                        fig_historico.update_traces(line_color='#375623')
                        st.plotly_chart(fig_historico, use_container_width=True)
                    else:
                        st.info("Histórico de dados ainda está sendo construído.")
                except Exception as e:
                    st.warning("Não foi possível carregar ou salvar o histórico.")
                    st.error("Detalhes técnicos do erro:")
                    st.code(traceback.format_exc())
            else:
                st.warning("Nenhum dado para gerar o report visual.")
    except Exception as e:
        st.error(f"Ocorreu um erro ao processar os arquivos: {e}")
else:
    st.info("Aguardando o upload dos arquivos CSV.")
