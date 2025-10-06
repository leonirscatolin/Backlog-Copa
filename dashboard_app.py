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

# --- FUNÇÕES DE PROCESSAMENTO ---
def get_base_64_of_bin_file(bin_file):
    try:
        with open(bin_file, 'rb') as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except FileNotFoundError:
        # Não mostra erro se o arquivo não for encontrado localmente, 
        # pois no deploy ele estará no GitHub
        return None

def processar_dados_comparativos(df_atual, df_15dias):
    contagem_atual = df_atual.groupby('Atribuir a um grupo').size().reset_index(name='Atual')
    contagem_15dias = df_15dias.groupby('Atribuir a um grupo').size().reset_index(name='15 Dias Atrás')
    df_comparativo = pd.merge(contagem_atual, contagem_15dias, on='Atribuir a um grupo', how='outer').fillna(0)
    df_comparativo['Diferença'] = df_comparativo['Atual'] - df_comparativo['15 Dias Atrás']
    df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']] = df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']].astype(int)
    return df_comparativo

def categorizar_idade_vetorizado(dias_series):
    # CONDIÇÕES CORRIGIDAS PARA O PADRÃO ORIGINAL
    condicoes = [
        dias_series >= 30,
        (dias_series >= 21) & (dias_series <= 29),
        (dias_series >= 11) & (dias_series <= 20),
        (dias_series >= 6) & (dias_series <= 10),
        (dias_series >= 3) & (dias_series <= 5),
        (dias_series >= 0) & (dias_series <= 2) 
    ]
    # OPÇÕES CORRIGIDAS PARA O PADRÃO ORIGINAL
    opcoes = ["30+ dias", "21 a 29 dias", "11 a 20 dias", "6 a 10 dias", "3 a 5 dias", "0 a 2 dias"]
    return np.select(condicoes, opcoes, default="Erro de Categoria")

def analisar_aging(df_atual):
    df = df_atual.copy()
    df['Data de criação'] = pd.to_datetime(df['Data de criação'], errors='coerce', dayfirst=True)
    df.dropna(subset=['Data de criação'], inplace=True)
    
    hoje = pd.to_datetime('today').normalize()
    data_criacao_normalizada = df['Data de criação'].dt.normalize()
    
    # CÁLCULO DE DIAS CORRIGIDO PARA O PADRÃO (sem o +1)
    df['Dias em Aberto'] = (hoje - data_criacao_normalizada).dt.days

    df['Faixa de Antiguidade'] = categorizar_idade_vetorizado(df['Dias em Aberto'])
    return df

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
        
        tab1, tab2 = st.tabs(["Dashboard Completo", "Report Visual (Em Desenvolvimento)"])

        with tab1:
            df_aging = analisar_aging(df_atual)
            st.subheader("Análise de Antiguidade do Backlog Atual")
            
            if not df_aging.empty:
                aging_counts = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
                aging_counts.columns = ['Faixa de Antiguidade', 'Quantidade']
                ordem_faixas = ["0 a 2 dias", "3 a 5 dias", "6 a 10 dias", "11 a 20 dias", "21 a 29 dias", "30+ dias"]
                todas_as_faixas = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas})
                aging_counts = pd.merge(todas_as_faixas, aging_counts, on='Faixa de Antiguidade', how='left').fillna(0).astype({'Quantidade': int})
                aging_counts['Faixa de Antiguidade'] = pd.Categorical(aging_counts['Faixa de Antiguidade'], categories=ordem_faixas, ordered=True)
                aging_counts = aging_counts.sort_values('Faixa de Antiguidade')
                aging_counts['Quantidade_texto'] = aging_counts['Quantidade'].astype(str)
                fig_antiguidade = px.bar(
                    aging_counts, x='Faixa de Antiguidade', y='Quantidade', text='Quantidade_texto',
                    title='Distribuição de Chamados por Antiguidade',
                    labels={'Faixa de Antiguidade': 'Idade do Chamado', 'Quantidade': 'Nº de Chamados'}
                )
                fig_antiguidade.update_traces(textposition='outside', marker_color='#375623', hovertemplate='<b>%{x}</b><br>Quantidade: %{y}<extra></extra>')
                fig_antiguidade.update_yaxes(dtick=1)
                st.plotly_chart(fig_antiguidade, use_container_width=True)
            else:
                st.warning("Nenhum dado válido para a análise de antiguidade.")

            st.subheader("Comparativo de Backlog: Atual vs. 15 Dias Atrás")
            df_comparativo = processar_dados_comparativos(df_atual.copy(), df_15dias.copy())
            df_comparativo.rename(columns={'Atribuir a um grupo': 'Grupo'}, inplace=True)
            st.dataframe(df_comparativo.set_index('Grupo').style.applymap(lambda val: 'background-color: #ffcccc' if val > 0 else ('background-color: #ccffcc' if val < 0 else 'background-color: white'), subset=['Diferença']), use_container_width=True)

            if not df_aging.empty:
                st.markdown("---") 
                st.subheader("Detalhar e Buscar Chamados")
                # (As seções de filtro e busca continuam aqui...)
        
        with tab2:
            st.warning("A aba 'Report Visual' com a funcionalidade de PDF foi desativada temporariamente para garantir a estabilidade do aplicativo.")
            st.info("Podemos reativar e corrigir a exportação para PDF no futuro.")

    except Exception as e:
        st.error(f"Ocorreu um erro ao processar os arquivos: {e}")
else:
    st.info("Aguardando o upload dos dois arquivos CSV na barra lateral.")
