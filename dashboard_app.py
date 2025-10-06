import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
# Removido: import base64 (não é mais necessário)
from datetime import datetime

# Configuração da página
st.set_page_config(
    layout="wide", 
    page_title="Backlog Copa Energia + Belago",
    page_icon="copaenergialogo_1691612041.webp"
)

# --- FUNÇÃO 'get_base_64_of_bin_file' REMOVIDA ---

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

# --- MUDANÇA: Usando st.sidebar.image de forma direta ---
# O GIF será exibido como uma imagem estática
st.sidebar.image("237f1d13493514962376f142bb68_1691760314.gif", use_container_width=True)
st.sidebar.image("logo_belago.png", use_container_width=True)
# --- FIM DA MUDANÇA ---

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

        tab1, tab2 = st.tabs(["Dashboard Completo", "Report Visual (Em Desenvolvimento)"])

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
                aging_counts = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
                aging_counts.columns = ['Faixa de Antiguidade', 'Quantidade']
                ordem_faixas = ["1-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
                todas_as_faixas = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas})
                aging_counts = pd.merge(todas_as_faixas, aging_counts, on='Faixa de Antiguidade', how='left').fillna(0).astype({'Quantidade': int})
                aging_counts['Faixa de Antiguidade'] = pd.Categorical(aging_counts['Faixa de Antiguidade'], categories=ordem_faixas, ordered=True)
                aging_counts = aging_counts.sort_values('Faixa de Antiguidade')

                st.markdown("""
                <style>
                .metric-box {
                    border: 1px solid #CCCCCC; padding: 10px; border-radius: 5px;
                    text-align: center; box-shadow: 0px 2px 4px rgba(0,0,0,0.1);
                    margin-bottom: 10px;
                }
                .metric-box .value {font-size: 2.5em; font-weight: bold; color: #375623;}
                .metric-box .label {font-size: 1em; color: #666666;}
                </style>
                """, unsafe_allow_html=True)
                
                cols = st.columns(len(ordem_faixas))
                for i, row in aging_counts.iterrows():
                    with cols[i]:
                        st.markdown(
                            f"""
                            <div class="metric-box">
                                <div class="value">{row['Quantidade']}</div>
                                <div class="label">{row['Faixa de Antiguidade']}</div>
                            </div>
                            """, unsafe_allow_html=True
                        )
            else:
                st.warning("Nenhum dado válido para a análise de antiguidade.")

            st.subheader("Comparativo de Backlog: Atual vs. 15 Dias Atrás")
            df_comparativo = processar_dados_comparativos(df_atual.copy(), df_15dias.copy())
            df_comparativo.rename(columns={'Atribuir a um grupo': 'Grupo'}, inplace=True)
            st.dataframe(df_comparativo.set_index('Grupo').style.applymap(lambda val: 'background-color: #ffcccc' if val > 0 else ('background-color: #ccffcc' if val < 0 else 'background-color: white'), subset=['Diferença']), use_container_width=True)

            if not df_aging.empty:
                st.markdown("---") 
                st.subheader("Detalhar e Buscar Chamados")
                opcoes_filtro = aging_counts['Faixa de Antiguidade'].tolist()
                selected_bucket = st.selectbox("Selecione uma faixa de idade para ver os detalhes:", options=opcoes_filtro)
                if selected_bucket and not df_aging[df_aging['Faixa de Antiguidade'] == selected_bucket].empty:
                    filtered_df = df_aging[df_aging['Faixa de Antiguidade'] == selected_bucket].copy()
                    filtered_df['Data de criação'] = filtered_df['Data de criação'].dt.strftime('%d/%m/%Y')
                    colunas_para_exibir = ['ID do ticket', 'Descrição', 'Atribuir a um grupo', 'Dias em Aberto', 'Data de criação']
                    st.dataframe(filtered_df[colunas_para_exibir], use_container_width=True)
                else:
                    st.write("Não há chamados nesta categoria.")

                st.markdown("---")
                st.subheader("Buscar Chamados por Grupo")
                lista_grupos = sorted(df_aging['Atribuir a um grupo'].dropna().unique())
                lista_grupos.insert(0, "Selecione um grupo...")
                grupo_selecionado = st.selectbox("Busca de chamados por grupo:", options=lista_grupos)
                if grupo_selecionado != "Selecione um grupo...":
                    resultados_busca = df_aging[df_aging['Atribuir a um grupo'] == grupo_selecionado].copy()
                    resultados_busca['Data de criação'] = resultados_busca['Data de criação'].dt.strftime('%d/%m/%Y')
                    st.write(f"Encontrados {len(resultados_busca)} chamados para o grupo '{grupo_selecionado}':")
                    colunas_para_exibir_busca = ['ID do ticket', 'Descrição', 'Dias em Aberto', 'Data de criação']
                    st.dataframe(resultados_busca[colunas_para_exibir_busca], use_container_width=True)
        
        with tab2:
            st.warning("A aba 'Report Visual' será desenvolvida em um próximo passo.")

    except Exception as e:
        st.error(f"Ocorreu um erro ao processar os arquivos: {e}")
else:
    st.info("Aguardando o upload dos dois arquivos CSV.")
