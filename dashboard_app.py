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

# --- Configuração da Página ---
st.set_page_config(
    layout="wide", 
    page_title="Backlog Copa Energia + Belago",
    page_icon="copaenergialogo_1691612041.webp"
)

# --- FUNÇÕES ---
@st.cache_resource
def connect_gsheets():
    creds_json = json.loads(st.secrets["gcp_creds"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"]
    creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open("Historico_Backlog")
    return spreadsheet.worksheet("Página1")

def update_history(worksheet, total_chamados):
    hoje_str = datetime.now().strftime("%d/%m/%Y")
    df_historico = get_history(worksheet)
    if not df_historico.empty and hoje_str in df_historico['Data'].dt.strftime('%d/%m/%Y').values:
        return
    new_row = [hoje_str, total_chamados]
    worksheet.append_row(new_row)

def get_history(worksheet):
    df = get_as_dataframe(worksheet, parse_dates=True, usecols=[0,1])
    df.dropna(subset=['Data'], inplace=True)
    if 'Total_Chamados' in df.columns:
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
    st.sidebar.markdown(f"""...""", unsafe_allow_html=True) # Omitido

st.sidebar.header("Carregar Arquivos")
uploaded_file_atual = st.sidebar.file_uploader("1. Backlog ATUAL (.csv)", type="csv")
uploaded_file_15dias = st.sidebar.file_uploader("2. Backlog de 15 DIAS ATRÁS (.csv)", type="csv")

if uploaded_file_atual and uploaded_file_15dias:
    try:
        # (Resto do código completo...)
        pass
    except Exception as e:
        st.error(f"Ocorreu um erro ao processar os arquivos: {e}")
else:
    st.info("Aguardando o upload dos dois arquivos CSV.")
