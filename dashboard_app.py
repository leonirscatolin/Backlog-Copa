# dashboard_app.py (Arquivo Principal)
import streamlit as st
import pandas as pd
from datetime import datetime
import base64

# --- Configuração da Página ---
st.set_page_config(
    layout="wide", 
    page_title="Dashboard de Backlog",
    page_icon="copaenergialogo_1691612041.webp"
)

# --- FUNÇÕES (copiadas para cá para manter o app autocontido) ---
def get_base64_of_bin_file(bin_file):
    try:
        with open(bin_file, 'rb') as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except FileNotFoundError:
        st.error(f"Arquivo de mídia não encontrado: {bin_file}. Envie o arquivo para o repositório no GitHub.")
        return None

# --- Interface ---
st.title("Dashboard Detalhado de Backlog")
st.markdown("Faça o upload dos arquivos na barra lateral para começar a análise.")

# Logos na Barra Lateral
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
uploaded_file_atual = st.sidebar.file_uploader("1. Backlog ATUAL (.csv)", type=['csv'])
uploaded_file_15dias = st.sidebar.file_uploader("2. Backlog de 15 DIAS ATRÁS (.csv)", type=['csv'])

# --- LÓGICA DE PROCESSAMENTO E ARMAZENAMENTO NA SESSÃO ---
if uploaded_file_atual and uploaded_file_15dias:
    try:
        df_atual = pd.read_csv(uploaded_file_atual, delimiter=';', encoding='latin1') 
        df_15dias = pd.read_csv(uploaded_file_15dias, delimiter=';', encoding='latin1')
        
        # Guardando os dataframes brutos na sessão para a outra página usar
        st.session_state['df_atual'] = df_atual
        st.session_state['df_15dias'] = df_15dias
        
        st.success("Arquivos carregados com sucesso! Navegue para a página 'Report Visual' na barra lateral.")
        st.info("Os dados detalhados que ficavam aqui agora estão na página 'Dashboard Completo' (esta página).")

    except Exception as e:
        st.error(f"Ocorreu um erro ao carregar os arquivos: {e}")
        st.warning("Verifique se os arquivos CSV estão corretos.")
else:
    st.info("Aguardando o upload dos arquivos CSV na barra lateral para habilitar as páginas de análise.")
