import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import base64
from datetime import datetime, date
from github import Github, Auth
from io import StringIO
from urllib.parse import quote

# --- Configuração da Página ---
st.set_page_config(
    layout="wide",
    page_title="Backlog Copa Energia + Belago",
    page_icon="minilogo.png",
    initial_sidebar_state="collapsed"
)

# --- FUNÇÕES ---
@st.cache_resource
def get_github_repo():
    try:
        auth = Auth.Token(st.secrets["GITHUB_TOKEN"])
        g = Github(auth=auth)
        return g.get_repo("leonirscatolin/dashboard-backlog")
    except Exception as e:
        st.error("Erro de conexão com o repositório. Verifique o GITHUB_TOKEN.")
        st.stop()

def update_github_file(_repo, file_path, file_content):
    commit_message = f"Dados atualizados em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    try:
        contents = _repo.get_contents(file_path)
        _repo.update_file(contents.path, commit_message, file_content, contents.sha)
        st.sidebar.info(f"Arquivo '{file_path}' atualizado.")
    except Exception:
        _repo.create_file(file_path, commit_message, file_content)
        st.sidebar.info(f"Arquivo '{file_path}' criado.")
    st.cache_data.clear()

@st.cache_data(ttl=300)
def read_github_file(_repo, file_path):
    try:
        content_file = _repo.get_contents(file_path)
        content = content_file.decoded_content.decode("utf-8")
        return pd.read_csv(StringIO(content), delimiter=';', encoding='latin1')
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def read_github_text_file(_repo, file_path):
    try:
        content_file = _repo.get_contents(file_path)
        content = content_file.decoded_content.decode("utf-8")
        dates = {}
        for line in content.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                dates[key] = value
        return dates
    except Exception:
        return {}

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
    if diferenca > 0: return "Alta Demanda"
    elif diferenca == 0: return "Estável / Atenção"
    else: return "Redução de Backlog"

# --- INTERFACE DO APLICATIVO ---
col1, col2, col3 = st.columns([1, 4, 1])
with col1: st.image("logo_sidebar.png", width=150)
with col2: st.markdown("<h1 style='text-align: center;'>Backlog Copa Energia + Belago</h1>", unsafe_allow_html=True)
with col3: st.image("logo_belago.png", width=150)

# --- LÓGICA DE LOGIN E UPLOAD ---
st.sidebar.header("Área do Administrador")
password = st.sidebar.text_input("Senha para atualizar dados:", type="password")
is_admin = password == st.secrets.get("ADMIN_PASSWORD", "")
repo = get_github_repo()
if is_admin:
    st.sidebar.success("Acesso de administrador liberado.")
    st.sidebar.header("Carregar Novos Arquivos")
    
    uploaded_file_atual = st.sidebar.file_uploader("1. Backlog ATUAL (.csv)", type="csv")
    st.sidebar.markdown(f"Data de referência do arquivo ATUAL: **{date.today().strftime('%d/%m/%Y')}**")
    
    uploaded_file_15dias = st.sidebar.file_uploader("2. Backlog de 15 DIAS ATRÁS (.csv)", type="csv")
    data_arquivo_15dias = st.sidebar.date_input( "Data de referência do arquivo de 15 DIAS", value=date.today() )
    
    if st.sidebar.button("Salvar Novos Dados no Site"):
        if uploaded_file_atual and uploaded_file_15dias:
            with st.spinner("Salvando arquivos e datas de referência..."):
                update_github_file(repo, "dados_atuais.csv", uploaded_file_atual.getvalue())
                update_github_file(repo, "dados_15_dias.csv", uploaded_file_15dias.getvalue())
                
                data_arquivo_atual = date.today()
                datas_referencia_content = (
                    f"data_atual:{data_arquivo_atual.strftime('%d/%m/%Y')}\n"
                    f"data_15dias:{data_arquivo_15dias.strftime('%d/%m/%Y')}"
                )
                update_github_file(repo, "datas_referencia.txt", datas_referencia_content)

            st.sidebar.balloons()
        else:
            st.sidebar.warning("Carregue os dois arquivos para salvar.")
elif password:
    st.sidebar.error("Senha incorreta.")


st.markdown("---")

# --- LÓGICA DE EXIBIÇÃO PARA TODOS ---
try:
    df_atual = read_github_file(repo, "dados_atuais.csv")
    df_15dias = read_github_file(repo, "dados_15_dias.csv")
    
    datas_referencia = read_github_text_file(repo, "datas_referencia.txt")
    data_atual_str = datas_referencia.get('data_atual', 'N/A')
    data_15dias_str = datas_referencia.get('data_15dias', 'N/A')

    st.markdown(f"""
    <div style="text-align: center; font-size: 0.9em; color: #666;">
        Data de referência dos dados: <b>{data_atual_str}</b> (Atual) e <b>{data_15dias_str}</b> (15 Dias Atrás).
    </div>
    <br>
    """, unsafe_allow_html=True)

    if df_atual.empty or df_15dias.empty:
        st.warning("Ainda não há dados para exibir. O administrador precisa carregar os arquivos pela primeira vez.")
    else:
        df_atual_filtrado = df_atual[~df_atual['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
        df_15dias_filtrado = df_15dias[~df_15dias['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
        df_aging = analisar_aging(df_atual_filtrado)

        st.markdown("""
        <style>
        #GithubIcon { visibility: hidden; }
        .metric-box { border: 1px solid #CCCCCC; padding: 10px; border-radius: 5px; text-align: center; box-shadow: 0px 2px 4px rgba(0,0,0,0.1); margin-bottom: 10px; }
        a.metric-box { display: block; color: inherit; text-decoration: none !important; }
        a.metric-box:hover { background-color: #f0f2f6; text-decoration: none !important; }
        .metric-box span { display: block; width: 100%; text-decoration: none !important; }
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
                with col_total: st.markdown(f"""<div class="metric-box"><span class="value">{total_chamados}</span><span class="label">Total de Chamados</span></div>""", unsafe_allow_html=True)
                st.markdown("---")
                aging_counts = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
                aging_counts.columns = ['Faixa de Antiguidade', 'Quantidade']
                ordem_faixas = ["1-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
                todas_as_faixas = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas})
                aging_counts = pd.merge(todas_as_faixas, aging_counts, on='Faixa de Antiguidade', how='left').fillna(0).astype({'Quantidade': int})
                aging_counts['Faixa de Antiguidade'] = pd.Categorical(aging_counts['Faixa de Antiguidade'], categories=ordem_faixas, ordered=True)
                aging_counts = aging_counts.sort_values('Faixa de Antiguidade')
                
                # Lógica simplificada para lidar com o filtro via URL
                if 'faixa_selecionada' not in st.session_state:
                    st.session_state.faixa_selecionada = ordem_faixas[0]
                
                if st.query_params.get("faixa"):
                    faixa_from_url = st.query_params.get("faixa")
                    if faixa_from_url in ordem_faixas:
                        st.session_state.faixa_selecionada = faixa_from_url
                        st.query_params.clear()

                cols = st.columns(len(ordem_faixas))
                for i, row in aging_counts.iterrows():
                    with cols[i]:
                        faixa_encoded = quote(row['Faixa de Antiguidade'])
                        # <-- ALTERADO: Link com a âncora # para tentar a rolagem
                        card_html = f"""<a href="?faixa={faixa_encoded}#detalhar-e-buscar-chamados" target="_self" class="metric-box"><span class="value">{row['Quantidade']}</span><span class="label">{row['Faixa de Antiguidade']}</span></a>"""
                        st.markdown(card_html, unsafe_allow_html=True)
            else: st.warning("Nenhum dado válido para a análise de antiguidade.")
            
            st.markdown(f"<h3>Comparativo de Backlog: Atual vs. 15 Dias Atrás <span style='font-size: 0.6em; color: #666; font-weight: normal;'>({data_15dias_str})</span></h3>", unsafe_allow_html=True)
            
            df_comparativo = processar_dados_comparativos(df_atual_filtrado.copy(), df_15dias_filtrado.copy())
            df_comparativo['Status'] = df_comparativo.apply(get_status, axis=1)
            df_comparativo.rename(columns={'Atribuir a um grupo': 'Grupo'}, inplace=True)
            st.dataframe(df_comparativo.set_index('Grupo').style.map(lambda val: 'background-color: #ffcccc' if val > 0 else ('background-color: #ccffcc' if val < 0 else 'background-color: white'), subset=['Diferença']), use_container_width=True)

            if not df_aging.empty:
                st.markdown("---")
                st.subheader("Detalhar e Buscar Chamados")

                st.selectbox( "Selecione uma faixa de idade para ver os detalhes (ou clique em um card acima):", options=ordem_faixas, key='faixa_selecionada' )
                faixa_atual = st.session_state.faixa_selecionada
                if faixa_atual and not df_aging[df_aging['Faixa de Antiguidade'] == faixa_atual].empty:
                    filtered_df = df_aging[df_aging['Faixa de Antiguidade'] == faixa_atual].copy()
                    filtered_df['Data de criação'] = filtered_df['Data de criação'].dt.strftime('%d/%m/%Y')
                    colunas_para_exibir = ['ID do ticket', 'Descrição', 'Atribuir a um grupo', 'Dias em Aberto', 'Data de criação']
                    st.dataframe(filtered_df[colunas_para_exibir], use_container_width=True)
                else: st.write("Não há chamados nesta categoria.")

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
                with col_total_tab2: st.markdown( f"""<div class="metric-box"><span class="value">{total_chamados}</span><span class="label">Total de Chamados</span></div>""", unsafe_allow_html=True )
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
                    with cols_tab2[i]: st.markdown( f"""<div class="metric-box"><span class="value">{row['Quantidade']}</span><span class="label">{row['Faixa de Antiguidade']}</span></div>""", unsafe_allow_html=True )
                st.markdown("---")
                st.subheader("Ofensores (Todos os Grupos)")
                top_ofensores = df_aging['Atribuir a um grupo'].value_counts().sort_values(ascending=True)
                fig_top_ofensores = px.bar(top_ofensores, x=top_ofensores.values, y=top_ofensores.index, orientation='h', text=top_ofensores.values, labels={'x': 'Qtd. Chamados', 'y': 'Grupo'})
                fig_top_ofensores.update_traces(textposition='outside', marker_color='#375623')
                fig_top_ofensores.update_layout(height=max(400, len(top_ofensores) * 25))
                st.plotly_chart(fig_top_ofensores, use_container_width=True)
            else: st.warning("Nenhum dado para gerar o report visual.")

except Exception as e:
    st.error(f"Ocorreu um erro ao carregar os dados: {e}")
