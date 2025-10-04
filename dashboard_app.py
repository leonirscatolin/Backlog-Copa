import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import base64
from datetime import datetime

# Configuração da página
st.set_page_config(
    layout="wide", 
    page_title="Backlog Copa Energia + Belago",
    page_icon="copaenergialogo_1691612041.webp"
)

# --- FUNÇÃO PARA CARREGAR IMAGENS ---
# Agora serve tanto para o GIF quanto para o PNG
def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

# --- FUNÇÕES DE PROCESSAMENTO (sem alterações) ---
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
        (dias_series >= 3) & (dias_series <= 5), (dias_series >= 0) & (dias_series <= 2)
    ]
    opcoes = ["30+ dias", "21 a 29 dias", "11 a 20 dias", "6 a 10 dias", "3 a 5 dias", "0 a 2 dias"]
    return np.select(condicoes, opcoes, default="Erro de Categoria")

def analisar_aging(df_atual):
    df = df_atual.copy()
    df['Data de criação'] = pd.to_datetime(df['Data de criação'], errors='coerce', dayfirst=True)
    df.dropna(subset=['Data de criação'], inplace=True)
    df['Dias em Aberto'] = (datetime.now() - df['Data de criação']).dt.days
    df['Faixa de Antiguidade'] = categorizar_idade_vetorizado(df['Dias em Aberto'])
    return df

# --- INTERFACE DO APLICATIVO ---
st.title("Backlog Copa Energia + Belago")
st.markdown("Faça o upload dos arquivos CSV para visualizar a comparação e a análise de antiguidade dos chamados.")

# --- MUDANÇA AQUI: Exibindo os dois logos na barra lateral ---
# Nome dos seus arquivos de imagem
gif_path = "copaenergiamkp-conceito_1691612041.gif"
belago_logo_path = "logo_belago.png" # Use o nome que você deu ao arquivo

# Codificamos as imagens para serem usadas em HTML
gif_base64 = get_base64_of_bin_file(gif_path)
belago_logo_base64 = get_base64_of_bin_file(belago_logo_path)

# Usamos st.markdown com HTML para exibir as duas imagens
st.sidebar.markdown(
    f"""
    <div style="text-align: center;">
        <img src="data:image/gif;base64,{gif_base64}" alt="Logo Copa Energia" style="width: 100%; border-radius: 15px; margin-bottom: 20px;">
        <img src="data:image/png;base64,{belago_logo_base64}" alt="Logo Belago" style="width: 80%; border-radius: 15px;">
    </div>
    """,
    unsafe_allow_html=True,
)
# --- FIM DA MUDANÇA ---


st.sidebar.header("Carregar Arquivos")
uploaded_file_atual = st.sidebar.file_uploader("1. Backlog ATUAL (.csv)", type=['csv'])
uploaded_file_15dias = st.sidebar.file_uploader("2. Backlog de 15 DIAS ATRÁS (.csv)", type=['csv'])

if uploaded_file_atual and uploaded_file_15dias:
    try:
        df_atual = pd.read_csv(uploaded_file_atual, delimiter=';', encoding='latin1') 
        df_15dias = pd.read_csv(uploaded_file_15dias, delimiter=';', encoding='latin1')
        st.success("Arquivos carregados com sucesso!")

        df_atual = df_atual[~df_atual['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
        df_15dias = df_15dias[~df_15dias['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
        st.info("Filtro aplicado: Grupos contendo 'RH' foram desconsiderados da análise.")

        st.subheader("Comparativo de Backlog: Atual vs. 15 Dias Atrás")
        df_comparativo = processar_dados_comparativos(df_atual.copy(), df_15dias.copy())

        def aplicar_cores(val):
            if val > 0: color = '#ffcccc'
            elif val < 0: color = '#ccffcc'
            else: color = 'white'
            return f'background-color: {color}'

        df_comparativo.rename(columns={'Atribuir a um grupo': 'Grupo'}, inplace=True)
        styled_df = df_comparativo.set_index('Grupo').style.applymap(aplicar_cores, subset=['Diferença'])
        st.dataframe(styled_df, use_container_width=True)

        st.subheader("Análise de Antiguidade do Backlog Atual")
        df_aging = analisar_aging(df_atual) 

        if not df_aging.empty:
            # (O resto do código para os gráficos e filtros continua o mesmo)
            # ...

    except Exception as e:
        st.error(f"Ocorreu um erro ao processar os arquivos: {e}")
        st.warning("Verifique se os nomes das colunas ('Atribuir a um grupo', 'Data de criação') estão corretos e se as datas são válidas.")
else:
    st.info("Aguardando o upload dos dois arquivos CSV.")
