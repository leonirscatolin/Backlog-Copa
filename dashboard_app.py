import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime, timedelta

# --- Configuração da Página ---
st.set_page_config(
    layout="wide", 
    page_title="Backlog Copa Energia + Belago",
    page_icon="copaenergialogo_1691612041.webp"
)

# --- FUNÇÕES DE PROCESSAMENTO ---
def categorizar_idade_vetorizado(dias_series):
    condicoes = [
        dias_series >= 30, (dias_series >= 21) & (dias_series <= 29),
        (dias_series >= 11) & (dias_series <= 20), (dias_series >= 6) & (dias_series <= 10),
        (dias_series >= 3) & (dias_series <= 5), (dias_series >= 1) & (dias_series <= 2)
    ]
    opcoes = ["30+ dias", "21-29 dias", "11-20 dias", "6-10 dias", "3-5 dias", "1-2 dias"]
    return np.select(condicoes, opcoes, default="Erro de Categoria")

def analisar_aging(df):
    df_proc = df.copy()
    # A coluna de data de criação já vem do banco no formato correto
    df_proc['data_criacao'] = pd.to_datetime(df_proc['data_criacao'], errors='coerce')
    df_proc.dropna(subset=['data_criacao'], inplace=True)
    
    hoje = pd.to_datetime('today').normalize()
    data_criacao_normalizada = df_proc['data_criacao'].dt.normalize()
    df_proc['Dias em Aberto'] = (hoje - data_criacao_normalizada).dt.days + 1
    df_proc['Faixa de Antiguidade'] = categorizar_idade_vetorizado(df_proc['Dias em Aberto'])
    return df_proc

def get_status(row):
    diferenca = row['Diferença']
    if diferenca > 0:
        return "Alta Demanda"
    elif diferenca == 0:
        return "Estável / Atenção"
    else:
        return "Redução de Backlog"

# --- INTERFACE DO APLICATIVO ---
st.title("Backlog Copa Energia + Belago")

# --- BARRA LATERAL ---
st.sidebar.image("logo-og-copaenergia.webp", use_container_width=True)
st.sidebar.header("Carregar Backlog do Dia")
uploaded_file_atual = st.sidebar.file_uploader("Carregue o arquivo de backlog ATUAL (.csv)", type="csv")

# Conexão com o banco de dados
conn = st.connection("db", type="sql")

# --- LÓGICA DE UPLOAD E SALVAMENTO ---
if uploaded_file_atual:
    try:
        df_novo = pd.read_csv(uploaded_file_atual, delimiter=';', encoding='latin1')
        df_novo_filtrado = df_novo[~df_novo['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
        
        df_para_salvar = df_novo_filtrado[['ID do ticket', 'Atribuir a um grupo', 'Data de criação']].copy()
        df_para_salvar.columns = ['id_ticket', 'grupo', 'data_criacao']
        df_para_salvar['data_snapshot'] = datetime.now().date()
        df_para_salvar['data_criacao'] = pd.to_datetime(df_para_salvar['data_criacao'], dayfirst=True, errors='coerce').dt.date

        hoje_str = datetime.now().strftime('%Y-%m-%d')
        
        with conn.session as s:
            s.execute(f"DELETE FROM backlog_historico WHERE data_snapshot = '{hoje_str}';")
            s.commit()
        
        conn.write(df_para_salvar, "backlog_historico", if_exists="append", index=False, chunksize=1000)
        st.success(f"Snapshot de {datetime.now().strftime('%d/%m/%Y')} salvo/atualizado com sucesso no banco de dados!")
        st.info("Os dados abaixo estão sendo lidos diretamente do banco de dados.")

    except Exception as e:
        st.error(f"Ocorreu um erro ao processar e salvar o arquivo: {e}")

# --- EXIBIÇÃO DOS DADOS (SEMPRE LENDO DO BANCO) ---
st.markdown("---")

try:
    hoje = datetime.now().date()
    data_15_dias = hoje - timedelta(days=15)
    
    df_hoje = conn.query(f"SELECT * FROM backlog_historico WHERE data_snapshot = '{hoje}';")
    df_15_dias_atras = conn.query(f"SELECT * FROM backlog_historico WHERE data_snapshot = '{data_15_dias}';")
    
    if df_hoje.empty:
        st.warning("Nenhum snapshot para a data de hoje encontrado no banco de dados. Por favor, carregue o arquivo do dia na barra lateral.")
    else:
        df_aging = analisar_aging(df_hoje)
        
        st.markdown("""<style>...</style>""", unsafe_allow_html=True) # Omitido
        tab1, tab2 = st.tabs(["Dashboard Completo", "Report Visual"])

        with tab1:
            st.info("""**Filtros e Regras Aplicadas:**...""") # Omitido
            st.subheader("Análise de Antiguidade do Backlog Atual")
            
            # ... (código dos cards de KPI)
            
            st.subheader("Comparativo de Backlog: Atual vs. 15 Dias Atrás")
            contagem_hoje = pd.DataFrame([{'Grupo': 'Todos', 'Atual': len(df_hoje)}])
            contagem_15_dias = pd.DataFrame([{'Grupo': 'Todos', '15 Dias Atrás': len(df_15_dias_atras)}])
            # ... (lógica de comparativo precisa ser reescrita para usar os dados do DB)

            st.markdown("---") 
            st.subheader("Detalhar e Buscar Chamados")
            # ... (lógica de filtros)

        with tab2:
            st.subheader("Resumo do Backlog Atual")
            # ... (código da tab 2)
            st.markdown("---")
            st.subheader("Evolução do Histórico de Backlog")
            
            df_historico_completo = conn.query("SELECT data_snapshot, grupo, COUNT(id_ticket) as quantidade FROM backlog_historico GROUP BY data_snapshot, grupo ORDER BY data_snapshot;")
            if not df_historico_completo.empty:
                # ... (código do gráfico de evolução)
                pass

except Exception as e:
    st.error(f"Ocorreu um erro ao buscar os dados do banco: {e}")
