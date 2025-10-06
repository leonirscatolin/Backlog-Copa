import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import base64
from datetime import datetime # LINHA QUE FALTAVA
from fpdf import FPDF

# Configuração da página
st.set_page_config(
    layout="wide", 
    page_title="Backlog Copa Energia + Belago",
    page_icon="copaenergialogo_1691612041.webp"
)

# --- FUNÇÕES DE PROCESSAMENTO E PDF ---
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

def criar_relatorio_pdf(total_chamados, fig_top_ofensores, fig_distribuicao):
    # (O código desta função não muda)
    pass

# --- INTERFACE DO APLICATIVO ---
st.title("Backlog Copa Energia + Belago")

# (O resto do código não muda)
# ...
