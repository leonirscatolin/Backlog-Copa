import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import base64
from datetime import datetime
from fpdf import FPDF

# Configuração da página
st.set_page_config(
    layout="wide", 
    page_title="Backlog Copa Energia + Belago",
    page_icon="copaenergialogo_1691612041.webp"
)

# --- FUNÇÕES DE PROCESSAMENTO ---
def get_base_64_of_bin_file(bin_file):
    try:
        with open(bin_file, 'rb') as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except FileNotFoundError:
        return None

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
        return "Alta demanda"
    elif diferenca == 0:
        return "Estável / Atenção"
    else: # diferenca < 0
        return "Redução de Backlog"

def criar_relatorio_pdf(df_comparativo_pdf, fig_antiguidade_pdf):
    fig_antiguidade_pdf.write_image("temp_chart.png", scale=2)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    pdf.cell(0, 10, f"Relatório de Backlog - {data_hoje}", 0, 1, "C")
    pdf.ln(10)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "Análise de Antiguidade do Backlog Atual", 0, 1, "L")
    pdf.image("temp_chart.png", x=10, y=None, w=190)
    pdf.ln(10)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "Comparativo de Backlog: Atual vs. 15 Dias Atrás", 0, 1, "L")
    pdf.ln(5)
    pdf.set_font("Arial", "B", 8)
    # Larguras das colunas
    col_widths = {'Grupo': 85, '15 Dias Atrás': 25, 'Atual': 15, 'Diferença': 20, 'Status': 45}
    for col in df_comparativo_pdf.columns:
        pdf.cell(col_widths[col], 8, col, 1, 0, "C")
    pdf.ln()
    pdf.set_font("Arial", "", 8)
    for index, row in df_comparativo_pdf.iterrows():
        for col in df_comparativo_pdf.columns:
            pdf.cell(col_widths[col], 8, str(row[col]), 1, 0, "L" if col == "Grupo" else "C")
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

# --- INTERFACE DO APLICATIVO ---
st.title("Backlog Copa Energia + Belago")

gif_path = "237f1d13493514962376f142bb68_1691760314.gif"
belago_logo_path = "logo_belago.png"
gif_base64 = get_base_64_of_bin_file(gif_path)
belago_logo_base64 = get_base_64_of_bin_file(belago_logo_path)
if gif_base64 and belago_logo_base64:
    st.sidebar.markdown(f"""...""", unsafe_allow_html=True) # Omitido

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
            # (Código da Tab 1, incluindo o botão de gerar PDF)
            pass
        with tab2:
            # (Código da Tab 2)
            pass
    except Exception as e:
        st.error(f"Ocorreu um erro ao processar os arquivos: {e}")
else:
    st.info("Aguardando o upload dos arquivos CSV.")
