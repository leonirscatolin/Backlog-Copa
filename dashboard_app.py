import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import base64
from datetime import datetime
import json # Importa a biblioteca JSON
import gspread

# --- Configuração da Página ---
st.set_page_config(
    layout="wide", 
    page_title="Backlog Copa Energia + Belago",
    page_icon="copaenergialogo_1691612041.webp"
)

# --- FUNÇÕES ---

@st.cache_resource
def connect_gsheets():
    # CORREÇÃO: Converte o segredo (que é uma string) para um dicionário antes de usar
    creds_dict = json.loads(st.secrets["gcp_creds"])
    sa = gspread.service_account_from_dict(creds_dict)
    spreadsheet = sa.open("Historico_Backlog")
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
        return "Demora na resolução"
    else:
        return "Alta demanda / Demora na resolução"

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
            border: 1px solid #CCCCCC; padding: 10px; border-radius: 5px;
            text-align: center; box-shadow: 0px 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 10px;
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
                    st.markdown(
                        f"""
                        <div class="metric-box">
                            <div class="value">{total_chamados}</div>
                            <div class="label">Total de Chamados</div>
                        </div>
                        """, unsafe_allow_html=True
                    )
                st.markdown("---")
                
                aging_counts = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
                aging_counts.columns = ['Faixa de Antiguidade', 'Quantidade']
                ordem_faixas = ["1-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
                todas_as_faixas = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas})
                aging_counts = pd.merge(todas_as_faixas, aging_counts, on='Faixa de Antiguidade', how='left').fillna(0).astype({'Quantidade': int})
                aging_counts['Faixa de Antiguidade'] = pd.Categorical(aging_counts['Faixa de Antiguidade'], categories=ordem_faixas, ordered=True)
                aging_counts = aging_counts.sort_values('Faixa de Antiguidade')

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
            df_comparativo = processar_dados_comparativos(df_atual_filtrado.copy(), df_15dias_filtrado.copy())
            df_comparativo['Status'] = df_comparativo.apply(get_status, axis=1)
            df_comparativo.rename(columns={'Atribuir a um grupo': 'Grupo'}, inplace=True)
            st.dataframe(df_comparativo.set_index('Grupo').style.map(lambda val: 'background-color: #ffcccc' if val > 0 else ('background-color: #ccffcc' if val < 0 else 'background-color: white'), subset=['Diferença']), use_container_width=True)

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
            st.subheader("Resumo do Backlog Atual")
            if not df_aging.empty:
                total_chamados = len(df_aging)
                _, col_total_tab2, _ = st.columns([2, 1.5, 2])
                with col_total_tab2:
                    st.markdown(
                        f"""
                        <div class="metric-box">
                            <div class="value">{total_chamados}</div>
                            <div class="label">Total de Chamados</div>
                        </div>
                        """, unsafe_allow_html=True
                    )
                st.markdown("---")
                
                aging_counts_tab2 = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
                aging_counts_tab2.columns = ['Faixa de Antiguidade', 'Quantidade']
                ordem_faixas_tab2 = ["1-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
                todas_as_faixas_tab2 = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas_tab2})
                aging_counts_tab2 = pd.merge(todas_as_faixas_tab2, aging_counts_tab2, on='Faixa de Antiguidade', how='left').fillna(0).astype({'Quantidade': int})
                aging_counts_tab2['Faixa de Antiguidade'] = pd.Categorical(aging_counts_tab2['Faixa de Antiguidade'], categories=ordem_faixas_tab2, ordered=True)
                aging_counts_tab2 = aging_counts_tab2.sort_values('Faixa de Antiguidade')
                
                cols_tab2 = st.columns(len(ordem_faixas_tab2))
                for i, row in aging_counts_tab2.iterrows():
                    with cols_tab2[i]:
                        st.markdown(
                            f"""
                            <div class="metric-box">
                                <div class="value">{row['Quantidade']}</div>
                                <div class="label">{row['Faixa de Antiguidade']}</div>
                            </div>
                            """, unsafe_allow_html=True
                        )
                
                st.markdown("---")
                st.subheader("Ofensores (Todos os Grupos)")
                top_ofensores = df_aging['Atribuir a um grupo'].value_counts().sort_values(ascending=True)
                fig_top_ofensores = px.bar(top_ofensores, x=top_ofensores.values, y=top_ofensores.index, orientation='h', text=top_ofensores.values, labels={'x': 'Qtd. Chamados', 'y': 'Grupo'})
                fig_top_ofensores.update_traces(textposition='outside', marker_color='#375623')
                fig_top_ofensores.update_layout(height=max(400, len(top_ofensores) * 25)) 
                st.plotly_chart(fig_top_ofensores, use_container_width=True)
                
                st.markdown("---")
                st.subheader("Evolução do Histórico de Backlog")
                try:
                    worksheet = connect_gsheets()
                    update_history(worksheet, total_chamados)
                    df_historico = get_history(worksheet)
                    if not df_historico.empty:
                        df_historico['Data'] = pd.to_datetime(df_historico['Data'], dayfirst=True)
                        df_historico = df_historico.sort_values(by='Data')
                        fig_historico = px.line(df_historico, x='Data', y='Total_Chamados', title="Total de chamados em aberto por dia", labels={'Data': 'Data', 'Total de Chamados': 'Total'}, markers=True)
                        fig_historico.update_traces(line_color='#375623')
                        st.plotly_chart(fig_historico, use_container_width=True)
                    else:
                        st.info("Histórico de dados ainda está sendo construído. Os dados de hoje foram salvos.")
                except Exception as e:
                    st.warning(f"Não foi possível carregar ou salvar o histórico. Verifique as configurações. Erro: {e}")
            else:
                st.warning("Nenhum dado para gerar o report visual.")

    except Exception as e:
        st.error(f"Ocorreu um erro ao processar os arquivos: {e}")
else:
    st.info("Aguardando o upload dos dois arquivos CSV.")
