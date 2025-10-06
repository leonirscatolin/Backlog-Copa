import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import base64
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- Configuração da Página ---
st.set_page_config(
    layout="wide", 
    page_title="Backlog Copa Energia + Belago",
    page_icon="copaenergialogo_1691612041.webp"
)

# --- FUNÇÕES DE CONEXÃO COM GOOGLE SHEETS ---
@st.cache_resource
def connect_gsheets():
    creds = Credentials.from_service_account_info(st.secrets["gcp_creds"], scopes=["https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(creds)
    spreadsheet = client.open("Historico_Backlog")
    return spreadsheet.worksheet("Página1")

def update_history(worksheet, total_chamados):
    hoje_str = datetime.now().strftime("%Y-%m-%d")
    df_historico = pd.DataFrame(worksheet.get_all_records())
    if not df_historico.empty:
        df_historico['Data_formatada'] = pd.to_datetime(df_historico['Data'], dayfirst=True).dt.strftime('%Y-%m-%d')
        if hoje_str in df_historico['Data_formatada'].values:
            return
    new_row = [datetime.now().strftime("%d/%m/%Y"), total_chamados]
    worksheet.append_row(new_row)

def get_history(worksheet):
    return pd.DataFrame(worksheet.get_all_records())

# --- FUNÇÕES DE PROCESSAMENTO ---
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

# --- INTERFACE DO APLICATIVO ---
st.title("Backlog Copa Energia + Belago")

st.sidebar.image("logo-og-copaenergia.webp", width='stretch')
st.sidebar.header("Carregar Arquivos")
uploaded_file_atual = st.sidebar.file_uploader("1. Backlog ATUAL (.csv)", type=['csv'])
uploaded_file_15dias = st.sidebar.file_uploader("2. Backlog de 15 DIAS ATRÁS (.csv)", type=['csv'])

if uploaded_file_atual and uploaded_file_15dias:
    try:
        df_atual = pd.read_csv(uploaded_file_atual, delimiter=';', encoding='latin1') 
        df_15dias = pd.read_csv(uploaded_file_15dias, delimiter=';', encoding='latin1')
        df_atual_filtrado = df_atual[~df_atual['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
        df_15dias_filtrado = df_15dias[~df_15dias['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
        df_aging = analisar_aging(df_atual_filtrado)
        
        tab1, tab2 = st.tabs(["Dashboard Completo", "Report Visual"])
        
        with tab1:
            st.info("""**Filtros e Regras Aplicadas:**...""") # Omitido
            st.subheader("Análise de Antiguidade do Backlog Atual")
            
            if not df_aging.empty:
                # Código dos cards de KPI
                pass
            else:
                st.warning("...")

            st.subheader("Comparativo de Backlog: Atual vs. 15 Dias Atrás")
            # Código da tabela de comparativo
            pass

            if not df_aging.empty:
                st.markdown("---") 
                st.subheader("Detalhar e Buscar Chamados")
                # Código dos filtros de busca
                pass
        
        with tab2:
            st.subheader("Resumo do Backlog Atual")
            if not df_aging.empty:
                # Código dos cards de KPI e gráficos da Tab 2
                pass

                st.markdown("---")
                st.subheader("Evolução do Histórico de Backlog")
                try:
                    worksheet = connect_gsheets()
                    total_chamados = len(df_aging)
                    update_history(worksheet, total_chamados)
                    df_historico = get_history(worksheet)
                    
                    if not df_historico.empty:
                        df_historico['Data'] = pd.to_datetime(df_historico['Data'], dayfirst=True)
                        df_historico = df_historico.sort_values(by='Data')
                        fig_historico = px.line(df_historico, x='Data', y='Total_Chamados', title="Total de chamados em aberto por dia", labels={'Data': 'Data', 'Total_Chamados': 'Total de Chamados'}, markers=True)
                        fig_historico.update_traces(line_color='#375623')
                        st.plotly_chart(fig_historico, use_container_width=True)
                    else:
                        st.info("...")
                except Exception as e:
                    st.warning(f"...")
            else:
                st.warning("...")
    except Exception as e:
        st.error(f"Ocorreu um erro ao processar os arquivos: {e}")
else:
    st.info("...")
