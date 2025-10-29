# VERSÃO v0.9.30-740 (Corrigida - Adiciona clear cache extra)

import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import base64
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from github import Github, Auth, GithubException
from io import StringIO, BytesIO
import streamlit.components.v1 as components
from PIL import Image
from urllib.parse import quote
import json
import colorsys
import re

st.set_page_config(
    layout="wide",
    page_title="Backlog Copa Energia + Belago",
    page_icon="minilogo.png",
    initial_sidebar_state="collapsed"
)

# ==========================================================
# ||           LISTA DE GRUPOS OCULTOS - GLOBAL           ||
# ==========================================================
grupos_excluidos = ['Aprovadores GGM', 'liq liq-sutel', 'liq-sutel']
# ==========================================================


st.html("""
<style>
#GithubIcon { visibility: hidden; }
/* ... (estilos CSS permanecem os mesmos) ... */
.metric-box {
    border: 1px solid #CCCCCC;
    padding: 10px;
    border-radius: 5px;
    text-align: center;
    box-shadow: 0px 2px 4px rgba(0,0,0,0.1);
    margin-bottom: 10px;
    height: 120px; /* Altura fixa para alinhar */
    display: flex; /* Para centralizar verticalmente */
    flex-direction: column; /* Organiza os spans verticalmente */
    justify-content: center; /* Centraliza verticalmente */
}
a.metric-box { /* Estilo para os cards clicáveis da Tab1 */
    display: block;
    color: inherit;
    text-decoration: none !important;
}
a.metric-box:hover {
    background-color: #f0f2f6;
    text-decoration: none !important;
}
.metric-box span { /* Aplica a todos os spans dentro de metric-box */
    display: block;
    width: 100%;
    text-decoration: none !important;
}
.metric-box .label { /* Label (Nome da faixa) */
    font-size: 1em;
    color: #666666;
    margin-bottom: 5px; /* Espaço entre label e value */
}
.metric-box .value { /* Número principal */
    font-size: 2.5em;
    font-weight: bold;
    color: #375623;
}
.metric-box .delta { /* Texto de comparação (delta) */
    font-size: 0.9em;
    margin-top: 5px; /* Espaço entre value e delta */
}
/* Classes para colorir o delta */
.delta-positive { color: #d9534f; } /* Vermelho para aumento */
.delta-negative { color: #5cb85c; } /* Verde para redução */
.delta-neutral { color: #666666; } /* Cinza para sem mudança ou N/A */
</style>
""")


@st.cache_resource
def get_github_repo():
    try:
        expected_repo_name = st.secrets.get("EXPECTED_REPO")
        if not expected_repo_name:
            st.error("Configuração de segurança incompleta. O segredo do repositório não foi encontrado.")
            st.stop()
        auth = Auth.Token(st.secrets["GITHUB_TOKEN"])
        g = Github(auth=auth)
        return g.get_repo(expected_repo_name)
    except GithubException as e:
        if e.status == 404:
            st.error("Erro de segurança: O token não tem acesso ao repositório esperado ou o repositório não existe.")
            st.stop()
        st.error(f"Erro de conexão com o repositório: {e}")
        st.stop()
    except Exception as e:
        st.error(f"Erro de conexão com o repositório: {e}")
        st.stop()

def update_github_file(_repo, file_path, file_content, commit_message):
    try:
        contents = _repo.get_contents(file_path)
        if isinstance(file_content, str):
            file_content = file_content.encode('utf-8')
        _repo.update_file(contents.path, commit_message, file_content, contents.sha)
        if file_path not in ["contacted_tickets.json", "ticket_observations.json", "datas_referencia.txt"]: # Evitar spam de msg
            st.sidebar.info(f"Arquivo '{file_path}' atualizado.")
    except GithubException as e:
        if e.status == 404:
            if isinstance(file_content, str):
                file_content = file_content.encode('utf-8')
            _repo.create_file(file_path, commit_message, file_content)
            if file_path not in ["contacted_tickets.json", "ticket_observations.json", "datas_referencia.txt"]: # Evitar spam de msg
                st.sidebar.info(f"Arquivo '{file_path}' criado.")
        else:
            st.sidebar.error(f"Falha ao salvar '{file_path}': {e}")
            raise # Re-levanta a exceção para o bloco superior tratar

@st.cache_data(ttl=300)
def read_github_file(_repo, file_path):
    try:
        content_file = _repo.get_contents(file_path)
        content_bytes = content_file.decoded_content

        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content = content_bytes.decode("latin-1")
                if file_path == "dados_fechados.csv":
                    st.sidebar.warning(f"Arquivo '{file_path}' lido com encoding 'latin-1'. Verifique se o arquivo foi salvo corretamente.")
            except Exception as decode_err:
                    st.error(f"Não foi possível decodificar o arquivo '{file_path}' com utf-8 ou latin-1: {decode_err}")
                    return pd.DataFrame()

        if not content.strip():
             # Retorna DF vazio se o arquivo estiver vazio
             # st.warning(f"Arquivo '{file_path}' está vazio.") # Opcional: Avisar
             return pd.DataFrame()

        try:
                df = pd.read_csv(StringIO(content), delimiter=';', encoding='utf-8',
                                     dtype={'ID do ticket': str, 'ID do Ticket': str}, low_memory=False,
                                     on_bad_lines='warn') # 'warn' é melhor que 'error'
        except pd.errors.ParserError as parse_err:
                st.error(f"Erro ao parsear o CSV '{file_path}': {parse_err}. Verifique o delimitador (;) e a estrutura do arquivo.")
                return pd.DataFrame()
        except Exception as read_err:
                st.error(f"Erro inesperado ao ler o conteúdo CSV de '{file_path}': {read_err}")
                return pd.DataFrame()

        df.columns = df.columns.str.strip()
        df.dropna(how='all', inplace=True) # Remove linhas TOTALMENTE vazias
        return df

    except GithubException as e:
        if e.status == 404:
             # Arquivo não encontrado - retorna DF vazio silenciosamente
             return pd.DataFrame()
        st.error(f"Erro ao acessar o arquivo do GitHub '{file_path}': {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro inesperado ao ler o arquivo '{file_path}': {e}")
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
                dates[key.strip()] = value.strip()
        return dates
    except GithubException as e:
        if e.status == 404: # Arquivo pode não existir na primeira vez
            return {}
        else:
            st.warning(f"Erro ao ler {file_path}: {e}")
            return {}
    except Exception as e:
        st.warning(f"Erro inesperado ao ler {file_path}: {e}")
        return {}


@st.cache_data(ttl=300)
def read_github_json_dict(_repo, file_path):
    try:
        file_content = _repo.get_contents(file_path).decoded_content.decode("utf-8")
        return json.loads(file_content) if file_content else {}
    except GithubException as e:
        if e.status == 404: return {} # Arquivo não existe ainda
        st.error(f"Erro ao carregar JSON '{file_path}': {e}")
        return {}
    except json.JSONDecodeError:
        # Se o arquivo existe mas está vazio ou mal formatado
        st.warning(f"Arquivo JSON '{file_path}' vazio ou com formato inválido. Iniciando com dicionário vazio.")
        return {}
    except Exception as e:
        st.error(f"Erro inesperado ao ler JSON '{file_path}': {e}")
        return {}

def process_uploaded_file(uploaded_file):
    if uploaded_file is None:
        return None
    try:
        # Define dtypes explicitamente para evitar conversão automática para float/int
        dtype_spec = {'ID do ticket': str, 'ID do Ticket': str, 'ID': str} 
        
        if uploaded_file.name.endswith('.xlsx'):
            # sheet_name=0 pega a primeira aba por padrão
            df = pd.read_excel(uploaded_file, dtype=dtype_spec, sheet_name=0) 
        else: # Assume CSV ou similar
            # Tenta UTF-8, depois Latin-1 como fallback
            try:
                content = uploaded_file.getvalue().decode('utf-8')
            except UnicodeDecodeError:
                content = uploaded_file.getvalue().decode('latin1')
            
            # Especifica delimitador e dtype
            df = pd.read_csv(StringIO(content), delimiter=';', dtype=dtype_spec) 

        df.columns = df.columns.str.strip()
        df.dropna(how='all', inplace=True) # Remove linhas totalmente vazias

        # Converte de volta para CSV com UTF-8 para salvar no GitHub
        output = StringIO()
        df.to_csv(output, index=False, sep=';', encoding='utf-8')
        return output.getvalue().encode('utf-8')
    except Exception as e:
        st.sidebar.error(f"Erro ao ler ou processar o arquivo {uploaded_file.name}: {e}")
        return None

def processar_dados_comparativos(df_atual, df_15dias):
     # Garante que a coluna existe antes de agrupar
    if 'Atribuir a um grupo' not in df_atual.columns or 'Atribuir a um grupo' not in df_15dias.columns:
        st.warning("Coluna 'Atribuir a um grupo' não encontrada em um dos dataframes para comparação.")
        # Retorna um DF vazio ou com estrutura básica para evitar erros posteriores
        return pd.DataFrame(columns=['Grupo', '15 Dias Atrás', 'Atual', 'Diferença', 'Status'])

    contagem_atual = df_atual.groupby('Atribuir a um grupo').size().reset_index(name='Atual')
    contagem_15dias = df_15dias.groupby('Atribuir a um grupo').size().reset_index(name='15 Dias Atrás')
    # how='outer' garante que grupos presentes em apenas um DF apareçam
    df_comparativo = pd.merge(contagem_atual, contagem_15dias, on='Atribuir a um grupo', how='outer').fillna(0)
    df_comparativo['Diferença'] = df_comparativo['Atual'] - df_comparativo['15 Dias Atrás']
    # Converte para int APÓS o fillna
    df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']] = df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']].astype(int)
    return df_comparativo

@st.cache_data
def categorizar_idade_vetorizado(dias_series):
    """Categoriza uma Série pandas de dias em faixas de antiguidade."""
    condicoes = [
        dias_series >= 30, (dias_series >= 21) & (dias_series <= 29),
        (dias_series >= 11) & (dias_series <= 20), (dias_series >= 6) & (dias_series <= 10),
        (dias_series >= 3) & (dias_series <= 5), (dias_series >= 0) & (dias_series <= 2)
    ]
    opcoes = ["30+ dias", "21-29 dias", "11-20 dias", "6-10 dias", "3-5 dias", "0-2 dias"]
    # default='Inválido' ajuda a identificar problemas
    return np.select(condicoes, opcoes, default="Inválido") 

@st.cache_data
def analisar_aging(_df_atual):
    """Calcula 'Dias em Aberto' e 'Faixa de Antiguidade' em relação a HOJE."""
    # Validação inicial
    if _df_atual is None or _df_atual.empty:
         st.warning("Dataframe vazio passado para analisar_aging.")
         return pd.DataFrame()
         
    df = _df_atual.copy()
    date_col_name = None
    # Prioriza 'Data de criação' mas aceita 'Data de Criacao'
    if 'Data de criação' in df.columns: date_col_name = 'Data de criação'
    elif 'Data de Criacao' in df.columns: date_col_name = 'Data de Criacao'
    
    if not date_col_name:
        st.warning(f"Nenhuma coluna de data de criação ('Data de criação' ou 'Data de Criacao') encontrada no dataframe para analisar_aging. Colunas disponíveis: {df.columns.tolist()}")
        return pd.DataFrame() # Retorna DF vazio se não achar coluna de data
    
    # Garante que a coluna de data é datetime, tratando erros
    original_dtype = df[date_col_name].dtype
    df[date_col_name] = pd.to_datetime(df[date_col_name], errors='coerce')
    
    # Identifica e informa sobre linhas onde a data não pôde ser convertida
    linhas_invalidas = df[df[date_col_name].isna() & _df_atual[date_col_name].notna()] # Checa se era NaN no original
    if not linhas_invalidas.empty:
        with st.expander(f"⚠️ Atenção (analisar_aging): {len(linhas_invalidas)} chamados foram descartados por formato de data inválido na coluna '{date_col_name}' (dtype original: {original_dtype})."):
             colunas_debug = [col for col in ['ID do ticket', date_col_name, 'Atribuir a um grupo'] if col in linhas_invalidas.columns]
             st.dataframe(linhas_invalidas[colunas_debug].head())

    # Remove linhas com datas inválidas (NaT)
    df = df.dropna(subset=[date_col_name]) 
    if df.empty:
        st.warning(f"Nenhum chamado com data válida encontrado na coluna '{date_col_name}' após a limpeza em analisar_aging.")
        return pd.DataFrame() # Retorna DF vazio se não sobrou nada

    # Calcula idade em relação a HOJE
    hoje = pd.to_datetime('today').normalize()
    # Normaliza a data de criação para comparar apenas dias
    data_criacao_normalizada = df[date_col_name].dt.normalize() 
    dias_calculados = (hoje - data_criacao_normalizada).dt.days
    
    # Aplica a regra de negócio: dias em aberto = dias calculados - 1 (mínimo 0)
    df['Dias em Aberto'] = (dias_calculados - 1).clip(lower=0) 
    
    # Categoriza usando a função vetorizada
    df['Faixa de Antiguidade'] = categorizar_idade_vetorizado(df['Dias em Aberto'])
    
    # Verifica se alguma categoria ficou 'Inválido'
    invalid_categories = df[df['Faixa de Antiguidade'] == 'Inválido']
    if not invalid_categories.empty:
         st.warning(f"{len(invalid_categories)} chamados resultaram em 'Dias em Aberto' negativos ou inválidos após cálculo.")
         # Poderia adicionar um expander aqui para mostrar os inválidos
         
    return df

def get_status(row):
    diferenca = row['Diferença']
    if diferenca > 0: return "Alta Demanda"
    elif diferenca == 0: return "Estável / Atenção"
    else: return "Redução de Backlog"

@st.cache_data
def get_image_as_base64(path):
    try:
        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode()
    except FileNotFoundError:
        st.warning(f"Arquivo de imagem não encontrado em: {path}") # Avisa se não achar
        return None

def sync_ticket_data():
    # ... (código sync_ticket_data permanece o mesmo) ...
    if 'ticket_editor' not in st.session_state or not st.session_state.ticket_editor.get('edited_rows'):
        return
    edited_rows = st.session_state.ticket_editor['edited_rows']
    contact_changed = False
    observation_changed = False
    # Cria cópias para poder reverter em caso de erro
    original_contacts = st.session_state.contacted_tickets.copy()
    original_observations = st.session_state.observations.copy()

    try:
        for row_index, changes in edited_rows.items():
            try:
                ticket_id = str(st.session_state.last_filtered_df.iloc[row_index].get('ID do ticket', None))
                if ticket_id is None: continue 

                if 'Contato' in changes:
                    current_contact_status = ticket_id in st.session_state.contacted_tickets
                    new_contact_status = changes['Contato']
                    if current_contact_status != new_contact_status:
                        if new_contact_status: st.session_state.contacted_tickets.add(ticket_id)
                        else: st.session_state.contacted_tickets.discard(ticket_id)
                        contact_changed = True
                if 'Observações' in changes:
                    current_observation = st.session_state.observations.get(ticket_id, '')
                    new_observation = changes['Observações']
                    if current_observation != new_observation:
                        st.session_state.observations[ticket_id] = new_observation
                        observation_changed = True
            except IndexError:
                st.warning(f"Erro ao processar linha {row_index} (Índice fora do range). Mudanças nesta linha podem não ser salvas.")
                continue # Pula para a próxima linha editada
            except Exception as e:
                 st.warning(f"Erro inesperado ao processar edições na linha {row_index}: {e}. Mudanças nesta linha podem não ser salvas.")
                 continue # Pula para a próxima linha editada

        if contact_changed or observation_changed:
            now_str = datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M')
            # Tenta salvar no GitHub
            if contact_changed:
                data_to_save = list(st.session_state.contacted_tickets)
                json_content = json.dumps(data_to_save, indent=4)
                commit_msg = f"Atualizando contatos em {now_str}"
                update_github_file(st.session_state.repo, "contacted_tickets.json", json_content.encode('utf-8'), commit_msg)
            if observation_changed:
                json_content = json.dumps(st.session_state.observations, indent=4, ensure_ascii=False)
                commit_msg = f"Atualizando observações em {now_str}"
                update_github_file(st.session_state.repo, "ticket_observations.json", json_content.encode('utf-8'), commit_msg)
        
        # Se chegou aqui sem erro do update_github_file, limpa as edições
        st.session_state.ticket_editor['edited_rows'] = {}

    except Exception as e:
         st.error(f"Falha ao salvar alterações no GitHub: {e}")
         st.warning("Revertendo alterações locais. Suas últimas edições não foram salvas.")
         # Reverte para o estado original em caso de falha no GitHub
         st.session_state.contacted_tickets = original_contacts
         st.session_state.observations = original_observations
         # Mantém as edited_rows para o usuário ver o que falhou? Ou limpa?
         # st.session_state.ticket_editor['edited_rows'] = {} # Limpar pode ser confuso

    st.session_state.scroll_to_details = True
    # Força um rerun para refletir o estado atual (salvo ou revertido)
    st.rerun() 


@st.cache_data(ttl=3600)
def carregar_dados_evolucao(_repo, dias_para_analisar=7):
    # ... (código carregar_dados_evolucao permanece o mesmo, já filtrando grupos ocultos) ...
    global grupos_excluidos
    try:
        all_files_content = _repo.get_contents("snapshots")
        all_files = [f.path for f in all_files_content]
        df_evolucao_list = []
        end_date = date.today()
        start_date = end_date - timedelta(days=max(dias_para_analisar + 5, 10)) 

        processed_dates = []
        for file_name in all_files:
            if file_name.startswith("snapshots/backlog_") and file_name.endswith(".csv"):
                try:
                    date_str = file_name.replace("snapshots/backlog_", "").replace(".csv", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if start_date <= file_date <= end_date:
                        processed_dates.append((file_date, file_name))
                except ValueError: continue
                except Exception as e: 
                     st.warning(f"Erro processando nome de arquivo snapshot {file_name}: {e}")
                     continue

        processed_dates.sort(key=lambda x: x[0])
        files_to_process = processed_dates[-dias_para_analisar:] 

        for file_date, file_name in files_to_process:
                try:
                    df_snapshot = read_github_file(_repo, file_name)
                    if df_snapshot.empty or 'Atribuir a um grupo' not in df_snapshot.columns:
                        st.warning(f"Snapshot {file_name} vazio ou sem coluna 'Atribuir a um grupo'. Pulando.")
                        continue
                    
                    df_snapshot_final = df_snapshot[~df_snapshot['Atribuir a um grupo'].isin(grupos_excluidos)]
                    df_snapshot_final = df_snapshot_final[~df_snapshot_final['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
                    
                    if df_snapshot_final.empty:
                         st.info(f"Nenhum chamado válido encontrado em {file_name} após filtros.")
                         continue 

                    contagem_diaria = df_snapshot_final.groupby('Atribuir a um grupo').size().reset_index(name='Total Chamados')
                    contagem_diaria['Data'] = pd.to_datetime(file_date)
                    df_evolucao_list.append(contagem_diaria)
                except Exception as e:
                     st.warning(f"Erro ao processar snapshot {file_name}: {e}")
                     continue

        if not df_evolucao_list: 
             st.warning("Nenhum dado de evolução pôde ser carregado após processar snapshots.")
             return pd.DataFrame()

        df_consolidado = pd.concat(df_evolucao_list, ignore_index=True)
        return df_consolidado.sort_values(by=['Data', 'Atribuir a um grupo'])

    except GithubException as e:
        if e.status == 404: 
             st.warning("Pasta 'snapshots' não encontrada no repositório.")
             return pd.DataFrame()
        st.warning(f"Erro no GitHub ao carregar snapshots: {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro inesperado ao carregar evolução: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def find_closest_snapshot_before(_repo, current_report_date, target_date):
    # ... (código find_closest_snapshot_before permanece o mesmo) ...
    try:
        all_files_content = _repo.get_contents("snapshots")
        snapshots = []
        search_start_date = target_date - timedelta(days=10) 

        for file in all_files_content:
            match = re.search(r"backlog_(\d{4}-\d{2}-\d{2})\.csv", file.path)
            if match:
                try:
                    snapshot_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
                    if search_start_date <= snapshot_date <= target_date: 
                        snapshots.append((snapshot_date, file.path))
                except ValueError:
                    continue 

        if not snapshots:
            st.warning(f"Nenhum snapshot encontrado entre {search_start_date.strftime('%d/%m')} e {target_date.strftime('%d/%m')}.")
            return None, None

        snapshots.sort(key=lambda x: x[0], reverse=True) 
        return snapshots[0] 

    except GithubException as e:
         if e.status == 404:
              st.warning("Pasta 'snapshots' não encontrada para buscar data comparativa.")
         else:
              st.warning(f"Erro no GitHub ao buscar snapshots: {e}")
         return None, None
    except Exception as e:
        st.error(f"Erro inesperado ao buscar snapshots: {e}")
        return None, None


@st.cache_data(ttl=3600)
def carregar_evolucao_aging(_repo, dias_para_analisar=90):
    # ... (código carregar_evolucao_aging permanece o mesmo, já usando analisar_aging e filtrando grupos ocultos) ...
    global grupos_excluidos
    try:
        all_files_content = _repo.get_contents("snapshots")
        all_files = [f.path for f in all_files_content]
        lista_historico = []
        end_date = date.today() - timedelta(days=1) 
        start_date = end_date - timedelta(days=max(dias_para_analisar + 10, 60)) 

        processed_files = []
        for file_name in all_files:
            if file_name.startswith("snapshots/backlog_") and file_name.endswith(".csv"):
                try:
                    date_str = file_name.replace("snapshots/backlog_", "").replace(".csv", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if start_date <= file_date <= end_date: 
                        processed_files.append((file_date, file_name))
                except Exception as e:
                    st.warning(f"Erro processando nome de arquivo snapshot {file_name} para aging: {e}")
                    continue

        processed_files.sort(key=lambda x: x[0]) 

        for file_date, file_name in processed_files:
            try:
                df_snapshot = read_github_file(_repo, file_name)
                if df_snapshot.empty or 'Atribuir a um grupo' not in df_snapshot.columns:
                    st.warning(f"Snapshot {file_name} para aging vazio ou sem coluna 'Atribuir a um grupo'. Pulando.")
                    continue

                df_filtrado = df_snapshot[~df_snapshot['Atribuir a um grupo'].isin(grupos_excluidos)]
                df_filtrado = df_filtrado[~df_filtrado['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]

                if df_filtrado.empty:
                    st.info(f"Nenhum chamado válido em {file_name} para aging após filtros.")
                    continue 

                # Usa analisar_aging para calcular idade em relação a HOJE
                df_com_aging = analisar_aging(df_filtrado.copy())

                if df_com_aging.empty or 'Faixa de Antiguidade' not in df_com_aging.columns:
                     st.warning(f"analisar_aging retornou dataframe vazio para snapshot {file_name}.")
                     continue 

                contagem_faixas = df_com_aging['Faixa de Antiguidade'].value_counts().reset_index()
                contagem_faixas.columns = ['Faixa de Antiguidade', 'total']

                ordem_faixas_scaffold = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
                df_todas_faixas = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas_scaffold})

                contagem_completa = pd.merge(
                    df_todas_faixas, contagem_faixas,
                    on='Faixa de Antiguidade', how='left'
                ).fillna(0)

                contagem_completa['total'] = contagem_completa['total'].astype(int)
                contagem_completa['data'] = pd.to_datetime(file_date) # Usa a data do snapshot

                lista_historico.append(contagem_completa)

            except Exception as e:
                 st.warning(f"Erro ao processar aging do snapshot {file_name}: {e}")
                 continue

        if not lista_historico:
            st.warning("Nenhum dado histórico de aging pôde ser carregado.")
            return pd.DataFrame()

        return pd.concat(lista_historico, ignore_index=True)

    except GithubException as e:
         if e.status == 404:
              st.warning("Pasta 'snapshots' não encontrada para carregar evolução aging.")
         else:
              st.warning(f"Erro no GitHub ao carregar evolução aging: {e}")
         return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro inesperado ao carregar evolução de aging: {e}")
        return pd.DataFrame()

def formatar_delta_card(delta_abs, delta_perc, valor_comparacao, data_comparacao_str):
    # ... (código formatar_delta_card permanece o mesmo) ...
    delta_abs = int(delta_abs)
    if valor_comparacao > 0:
        delta_perc_str = f"{delta_perc * 100:.1f}%"
        delta_text = f"{delta_abs:+} ({delta_perc_str}) vs. {data_comparacao_str}"
    elif valor_comparacao == 0 and delta_abs > 0:
        delta_text = f"+{delta_abs} (Novo) vs. {data_comparacao_str}" 
    elif valor_comparacao == 0 and delta_abs < 0:
        delta_text = f"{delta_abs} vs. {data_comparacao_str}" 
    elif valor_comparacao > 0 and delta_abs == 0:
        delta_text = f"0 (0.0%) vs. {data_comparacao_str}"
    else: 
         delta_text = f"0 (0.0%) vs. {data_comparacao_str}"

    if delta_abs > 0:
        delta_class = "delta-positive"
    elif delta_abs < 0:
        delta_class = "delta-negative"
    else:
        delta_class = "delta-neutral"

    return delta_text, delta_class


logo_copa_b64 = get_image_as_base64("logo_sidebar.png")
logo_belago_b64 = get_image_as_base64("logo_belago.png")
if logo_copa_b64 and logo_belago_b64:
    st.markdown(f"""<div style="display: flex; justify-content: space-between; align-items: center;"><img src="data:image/png;base64,{logo_copa_b64}" width="150"><h1 style='text-align: center; margin: 0;'>Backlog Copa Energia + Belago</h1><img src="data:image/png;base64,{logo_belago_b64}" width="150"></div>""", unsafe_allow_html=True)
else:
    st.error("Arquivos de logo não encontrados.")

repo = get_github_repo()
st.session_state.repo = repo

st.sidebar.header("Área do Administrador")
password = st.sidebar.text_input("Senha para atualizar dados:", type="password")
is_admin = password == st.secrets.get("ADMIN_PASSWORD", "")

if is_admin:
    st.sidebar.success("Acesso de administrador liberado.")
    st.sidebar.subheader("Atualização Completa")
    uploaded_file_atual = st.sidebar.file_uploader("1. Backlog ATUAL", type=["csv", "xlsx"], key="uploader_atual")
    uploaded_file_15dias = st.sidebar.file_uploader("2. Backlog de 15 DIAS ATRÁS", type=["csv", "xlsx"], key="uploader_15dias")
    if st.sidebar.button("Salvar Novos Dados no Site"):
        if uploaded_file_atual and uploaded_file_15dias:
            with st.spinner("Processando e salvando atualização completa..."):
                now_sao_paulo = datetime.now(ZoneInfo('America/Sao_Paulo'))
                commit_msg = f"Dados atualizados em {now_sao_paulo.strftime('%d/%m/%Y %H:%M')}"
                content_atual = process_uploaded_file(uploaded_file_atual)
                content_15dias = process_uploaded_file(uploaded_file_15dias)
                if content_atual is not None and content_15dias is not None:
                    try:
                        update_github_file(repo, "dados_atuais.csv", content_atual, commit_msg)
                        update_github_file(repo, "dados_15_dias.csv", content_15dias, commit_msg)
                        today_str = now_sao_paulo.strftime('%Y-%m-%d')
                        snapshot_path = f"snapshots/backlog_{today_str}.csv"
                        update_github_file(repo, snapshot_path, content_atual, f"Snapshot de {today_str}")
                        data_do_upload = now_sao_paulo.date()
                        data_arquivo_15dias = data_do_upload - timedelta(days=15)
                        hora_atualizacao = now_sao_paulo.strftime('%H:%M')
                        datas_referencia_content = (f"data_atual:{data_do_upload.strftime('%d/%m/%Y')}\n"
                                                    f"data_15dias:{data_arquivo_15dias.strftime('%d/%m/%Y')}\n"
                                                    f"hora_atualizacao:{hora_atualizacao}")
                        update_github_file(repo, "datas_referencia.txt", datas_referencia_content.encode('utf-8'), commit_msg)
                        
                        # ==========================================================
                        # ||           FORÇAR LIMPEZA EXTRA DE CACHE              ||
                        # ==========================================================
                        st.cache_data.clear()
                        st.cache_resource.clear()
                        # ==========================================================

                        st.sidebar.success("Arquivos salvos! Forçando recarregamento...")
                        st.rerun()
                    except Exception as e:
                        st.sidebar.error(f"Erro durante a atualização completa: {e}")

        else:
            st.sidebar.warning("Para a atualização completa, carregue os arquivos ATUAL e de 15 DIAS.")
    st.sidebar.markdown("---")
    st.sidebar.subheader("Atualização Rápida")
    uploaded_file_fechados = st.sidebar.file_uploader("Apenas Chamados FECHADOS no dia", type=["csv", "xlsx"], key="uploader_fechados")
    if st.sidebar.button("Salvar Apenas Chamados Fechados"):
        if uploaded_file_fechados:
            with st.spinner("Salvando arquivo de chamados fechados..."):
                now_sao_paulo = datetime.now(ZoneInfo('America/Sao_Paulo'))
                commit_msg = f"Atualizando chamados fechados em {now_sao_paulo.strftime('%d/%m/%Y %H:%M')}"
                content_fechados = process_uploaded_file(uploaded_file_fechados)
                if content_fechados is not None:
                    try:
                        update_github_file(repo, "dados_fechados.csv", content_fechados, commit_msg)

                        datas_existentes = read_github_text_file(repo, "datas_referencia.txt")
                        data_atual_existente = datas_existentes.get('data_atual', 'N/A')
                        data_15dias_existente = datas_existentes.get('data_15dias', 'N/A')
                        hora_atualizacao_nova = now_sao_paulo.strftime('%H:%M')

                        datas_referencia_content_novo = (f"data_atual:{data_atual_existente}\n"
                                                       f"data_15dias:{data_15dias_existente}\n"
                                                       f"hora_atualizacao:{hora_atualizacao_nova}")
                        update_github_file(repo, "datas_referencia.txt", datas_referencia_content_novo.encode('utf-8'), commit_msg)

                        # ==========================================================
                        # ||           FORÇAR LIMPEZA EXTRA DE CACHE              ||
                        # ==========================================================
                        st.cache_data.clear()
                        st.cache_resource.clear()
                        # ==========================================================

                        st.sidebar.success("Arquivo de fechados salvo e hora atualizada! Recarregando...")
                        st.rerun()
                    except Exception as e:
                        st.sidebar.error(f"Erro durante a atualização rápida: {e}")
        else:
            st.sidebar.warning("Por favor, carregue o arquivo de chamados fechados para salvar.")
elif password:
    st.sidebar.error("Senha incorreta.")

# --- Bloco Principal ---
try:
    # Carrega estado inicial (contatos, observações)
    if 'contacted_tickets' not in st.session_state:
        # ... (código para carregar contacted_tickets) ...
        try:
            file_content = repo.get_contents("contacted_tickets.json").decoded_content.decode("utf-8")
            st.session_state.contacted_tickets = set(json.loads(file_content))
        except GithubException as e:
            if e.status == 404: st.session_state.contacted_tickets = set()
            else: st.error(f"Erro ao carregar o estado dos tickets: {e}"); st.session_state.contacted_tickets = set()
        except json.JSONDecodeError:
             st.warning("Arquivo 'contacted_tickets.json' corrompido ou vazio. Iniciando com lista vazia.")
             st.session_state.contacted_tickets = set()


    if 'observations' not in st.session_state:
        st.session_state.observations = read_github_json_dict(repo, "ticket_observations.json")

    # Trata parâmetros da URL (para scroll e seleção de faixa)
    needs_scroll = "scroll" in st.query_params
    if "faixa" in st.query_params:
        # ... (código para tratar faixa_from_url) ...
        faixa_from_url = st.query_params.get("faixa")
        ordem_faixas_validas = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
        if faixa_from_url in ordem_faixas_validas:
                st.session_state.faixa_selecionada = faixa_from_url
    if "scroll" in st.query_params or "faixa" in st.query_params:
        # Limpa os parâmetros da URL após usá-los para evitar re-scroll em cada rerun
        st.query_params.clear() 

    # --- Carregamento e Pré-processamento dos Dados ---
    df_atual = read_github_file(repo, "dados_atuais.csv")
    df_15dias = read_github_file(repo, "dados_15_dias.csv")
    df_fechados_raw = read_github_file(repo, "dados_fechados.csv") # Renomeado para _raw
    datas_referencia = read_github_text_file(repo, "datas_referencia.txt")
    data_atual_str = datas_referencia.get('data_atual', 'N/A')
    data_15dias_str = datas_referencia.get('data_15dias', 'N/A')
    hora_atualizacao_str = datas_referencia.get('hora_atualizacao', '')
    
    if df_atual.empty:
        st.warning("Arquivo 'dados_atuais.csv' não encontrado ou vazio. Carregue os dados na área do administrador.")
        st.stop()

    # Aplica filtros de grupos ocultos
    if 'Atribuir a um grupo' in df_atual.columns:
        df_atual = df_atual[~df_atual['Atribuir a um grupo'].isin(grupos_excluidos)].copy()
    else:
        st.error("Coluna 'Atribuir a um grupo' não encontrada em dados_atuais.csv.")
        st.stop()

    if not df_15dias.empty and 'Atribuir a um grupo' in df_15dias.columns:
        df_15dias_filtrado_ocultos = df_15dias[~df_15dias['Atribuir a um grupo'].isin(grupos_excluidos)].copy()
    else:
        df_15dias_filtrado_ocultos = pd.DataFrame()

    # Padroniza coluna de ID
    id_col_atual = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_atual.columns), None)
    if id_col_atual:
        df_atual[id_col_atual] = df_atual[id_col_atual].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        # Renomeia para 'ID do ticket' para consistência
        if id_col_atual != 'ID do ticket': 
            df_atual.rename(columns={id_col_atual: 'ID do ticket'}, inplace=True)
        id_col_atual = 'ID do ticket' # Garante que a variável reflete o nome correto
    else:
        st.error("Coluna de ID ('ID do ticket', 'ID do Ticket', 'ID') não encontrada em dados_atuais.csv.")
        st.stop()

    # Obtém IDs dos chamados fechados
    closed_ticket_ids = np.array([]) # Usa array numpy para melhor performance com isin
    if not df_fechados_raw.empty:
        id_col_fechados = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_fechados_raw.columns), None)
        if id_col_fechados:
            ids_fechados_series = df_fechados_raw[id_col_fechados].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().dropna()
            closed_ticket_ids = ids_fechados_series.unique()
        else:
             st.warning("Arquivo 'dados_fechados.csv' carregado, mas coluna de ID não encontrada.")

    # Filtra RH do dataframe atual principal
    df_atual_filtrado_rh = df_atual[~df_atual['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]

    # Filtra RH do dataframe de 15 dias (se existir)
    if not df_15dias_filtrado_ocultos.empty:
        df_15dias_filtrado = df_15dias_filtrado_ocultos[~df_15dias_filtrado_ocultos['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
    else:
        df_15dias_filtrado = pd.DataFrame() # Mantém vazio se o original já era

    # Calcula Aging para TODOS os chamados atuais (já filtrados por ocultos e RH)
    df_todos_com_aging = analisar_aging(df_atual_filtrado_rh.copy()) 

    if df_todos_com_aging.empty:
         st.error("A análise de aging não retornou nenhum dado válido para os dados atuais.")
         st.stop()

    # Separa em abertos (df_aging) e fechados (df_encerrados_filtrado)
    df_encerrados_filtrado = df_todos_com_aging[df_todos_com_aging[id_col_atual].isin(closed_ticket_ids)]
    df_aging = df_todos_com_aging[~df_todos_com_aging[id_col_atual].isin(closed_ticket_ids)]
    
    # --- Fim do Pré-processamento ---

    # Define as abas
    tab1, tab2, tab3, tab4 = st.tabs(["Dashboard Completo", "Report Visual", "Evolução Semanal", "Evolução Aging"])

    # --- Conteúdo da Tab 1 ---
    with tab1:
        # ... (código da Tab 1 permanece o mesmo, usando df_aging e df_encerrados_filtrado) ...
        info_messages = ["**Filtros e Regras Aplicadas:**", 
                         f"- Grupos ocultos ({', '.join(grupos_excluidos)}) e grupos contendo 'RH' foram desconsiderados da análise.", 
                         "- A contagem de dias do chamado desconsidera o dia da sua abertura (prazo -1 dia)."]
        if closed_ticket_ids.size > 0: 
            info_messages.append(f"- **{len(df_encerrados_filtrado)} chamados fechados no dia** (exceto RH e ocultos) foram deduzidos das contagens principais e movidos para a tabela de encerrados.")
        st.info("\n".join(info_messages))
        
        st.subheader("Análise de Antiguidade do Backlog Atual")
        texto_hora = f" (atualizado às {hora_atualizacao_str})" if hora_atualizacao_str else ""
        st.markdown(f"<p style='font-size: 0.9em; color: #666;'><i>Data de referência: {data_atual_str}{texto_hora}</i></p>", unsafe_allow_html=True)
        
        if not df_aging.empty:
            total_chamados = len(df_aging)
            total_fechados = len(df_encerrados_filtrado)
            col_spacer1, col_total, col_fechados, col_spacer2 = st.columns([1, 1.5, 1.5, 1])
            with col_total:
                st.markdown(f"""<div class="metric-box"><span class="label">Total de Chamados Abertos</span><span class="value">{total_chamados}</span></div>""", unsafe_allow_html=True)
            with col_fechados:
                st.markdown(f"""<div class="metric-box"><span class="label">Chamados Fechados no Dia</span><span class="value">{total_fechados}</span></div>""", unsafe_allow_html=True)

            st.markdown("---")
            aging_counts = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
            aging_counts.columns = ['Faixa de Antiguidade', 'Quantidade']
            ordem_faixas = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
            todas_as_faixas = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas})
            aging_counts = pd.merge(todas_as_faixas, aging_counts, on='Faixa de Antiguidade', how='left').fillna(0).astype({'Quantidade': int})
            aging_counts['Faixa de Antiguidade'] = pd.Categorical(aging_counts['Faixa de Antiguidade'], categories=ordem_faixas, ordered=True)
            aging_counts = aging_counts.sort_values('Faixa de Antiguidade')
            if 'faixa_selecionada' not in st.session_state:
                st.session_state.faixa_selecionada = "0-2 dias" 
            
            if st.session_state.faixa_selecionada not in ordem_faixas:
                 st.session_state.faixa_selecionada = "0-2 dias" 

            cols = st.columns(len(ordem_faixas))
            for i, row in aging_counts.iterrows():
                with cols[i]:
                    faixa_encoded = quote(row['Faixa de Antiguidade'])
                    card_html = f"""<a href="?faixa={faixa_encoded}&scroll=true" target="_self" class="metric-box"><span class="label">{row['Faixa de Antiguidade']}</span><span class="value">{row['Quantidade']}</span></a>"""
                    st.markdown(card_html, unsafe_allow_html=True)
        else:
            st.warning("Nenhum chamado aberto encontrado após aplicar os filtros.")

        st.markdown(f"<h3>Comparativo de Backlog: Atual vs. 15 Dias Atrás <span style='font-size: 0.6em; color: #666; font-weight: normal;'>({data_15dias_str if not df_15dias_filtrado.empty else 'Dados Indisponíveis'})</span></h3>", unsafe_allow_html=True)
        if not df_15dias_filtrado.empty:
            df_comparativo = processar_dados_comparativos(df_aging.copy(), df_15dias_filtrado.copy()) 
            if not df_comparativo.empty: # Checa se o processamento retornou algo
                 df_comparativo['Status'] = df_comparativo.apply(get_status, axis=1)
                 df_comparativo = df_comparativo.rename(columns={'Atribuir a um grupo': 'Grupo'}) 
                 df_comparativo = df_comparativo[['Grupo', '15 Dias Atrás', 'Atual', 'Diferença', 'Status']]
                 st.dataframe(df_comparativo.set_index('Grupo').style.map(lambda val: 'background-color: #ffcccc' if val > 0 else ('background-color: #ccffcc' if val < 0 else 'background-color: white'), subset=['Diferença']), use_container_width=True)
            else:
                 st.info("Nenhum dado comum encontrado para comparação entre os períodos.")
        else:
             st.warning("Não foi possível carregar ou processar os dados de 15 dias atrás para comparação.")
        
        st.markdown("---")

        st.markdown(f"<h3>Chamados Encerrados no Dia <span style='font-size: 0.6em; color: #666; font-weight: normal;'>({data_atual_str})</span></h3>", unsafe_allow_html=True)
        if not closed_ticket_ids.size > 0: 
             st.info("O arquivo de chamados encerrados do dia ('dados_fechados.csv') ainda não foi carregado.")
        elif not df_encerrados_filtrado.empty:
            colunas_fechados = ['ID do ticket', 'Descrição', 'Atribuir a um grupo', 'Dias em Aberto']
            # Garante que as colunas existem antes de tentar exibi-las
            colunas_existentes_fechados = [col for col in colunas_fechados if col in df_encerrados_filtrado.columns]
            st.data_editor(
                df_encerrados_filtrado[colunas_existentes_fechados], 
                hide_index=True, 
                disabled=True, 
                use_container_width=True,
                key="editor_fechados" 
            )
        else:
             st.info("Nenhum chamado encerrado hoje pertence aos grupos analisados.") 

        if not df_aging.empty:
            st.markdown("---")
            # Adiciona ID ao header para o JS encontrar
            st.subheader("Detalhar e Buscar Chamados Abertos", anchor="detalhar-e-buscar-chamados-abertos") 
            st.info('Marque "Contato" se já falou com o usuário e a solicitação continua pendente. Use "Observações" para anotações.')

            if 'scroll_to_details' not in st.session_state:
                st.session_state.scroll_to_details = False
            if needs_scroll or st.session_state.get('scroll_to_details', False):
                # O ID no JS deve corresponder ao anchor do subheader
                js_code = """<script> setTimeout(() => { const element = window.parent.document.getElementById('detalhar-e-buscar-chamados-abertos'); if (element) { element.scrollIntoView({ behavior: 'smooth', block: 'start' }); } }, 250); </script>"""
                components.html(js_code, height=0)
                st.session_state.scroll_to_details = False 

            st.selectbox("Selecione uma faixa de idade para ver os detalhes (ou clique em um card acima):", 
                         options=ordem_faixas, 
                         key='faixa_selecionada') 
            
            faixa_atual = st.session_state.faixa_selecionada
            filtered_df = df_aging[df_aging['Faixa de Antiguidade'] == faixa_atual].copy()
            
            if not filtered_df.empty:
                def highlight_row(row):
                    return ['background-color: #fff8c4'] * len(row) if row.get('Contato', False) else [''] * len(row)

                filtered_df['Contato'] = filtered_df['ID do ticket'].apply(lambda id: str(id) in st.session_state.contacted_tickets)
                filtered_df['Observações'] = filtered_df['ID do ticket'].apply(lambda id: st.session_state.observations.get(str(id), ''))

                st.session_state.last_filtered_df = filtered_df.reset_index(drop=True) 

                colunas_para_exibir_renomeadas = {
                    'Contato': 'Contato', 'ID do ticket': 'ID do ticket', 'Descrição': 'Descrição',
                    'Atribuir a um grupo': 'Grupo Atribuído', 'Dias em Aberto': 'Dias em Aberto',
                    'Data de criação': 'Data de criação', 'Observações': 'Observações'
                }
                colunas_existentes = [col for col in colunas_para_exibir_renomeadas if col in filtered_df.columns]
                colunas_renomeadas_existentes = [colunas_para_exibir_renomeadas[col] for col in colunas_existentes]
                colunas_editaveis = ['Contato', 'Observações'] # Nomes originais
                colunas_desabilitadas = [colunas_para_exibir_renomeadas[c] for c in colunas_existentes if c not in colunas_editaveis]


                st.data_editor(
                    # Aplica rename ANTES de selecionar colunas
                    st.session_state.last_filtered_df.rename(columns=colunas_para_exibir_renomeadas)[colunas_renomeadas_existentes].style.apply(highlight_row, axis=1),
                    use_container_width=True,
                    hide_index=True,
                    disabled=colunas_desabilitadas, # Usa a lista dinâmica
                    key='ticket_editor', 
                    on_change=sync_ticket_data
                )
            else:
                st.info(f"Não há chamados abertos na faixa '{faixa_atual}'.")
            
            st.subheader("Buscar Chamados Abertos por Grupo")
            if 'Atribuir a um grupo' in df_aging.columns:
                 lista_grupos = sorted(df_aging['Atribuir a um grupo'].dropna().unique())
                 if lista_grupos:
                      grupo_selecionado = st.selectbox("Selecione um grupo:", options=lista_grupos, key="busca_grupo")
                      if grupo_selecionado:
                           resultados_busca = df_aging[df_aging['Atribuir a um grupo'] == grupo_selecionado].copy()
                           
                           date_col_name_busca = next((col for col in ['Data de criação', 'Data de Criacao'] if col in resultados_busca.columns), None)
                           if date_col_name_busca:
                                # Converte para datetime ANTES de formatar
                                resultados_busca[date_col_name_busca] = pd.to_datetime(resultados_busca[date_col_name_busca]).dt.strftime('%d/%m/%Y')

                           st.write(f"Encontrados {len(resultados_busca)} chamados abertos para o grupo '{grupo_selecionado}':")
                           
                           colunas_para_exibir_busca = ['ID do ticket', 'Descrição', 'Dias em Aberto', date_col_name_busca]
                           colunas_existentes_busca = [col for col in colunas_para_exibir_busca if col in resultados_busca.columns and col is not None] # Remove None se date_col não existir
                           
                           st.data_editor(
                                resultados_busca[colunas_existentes_busca], 
                                use_container_width=True, hide_index=True, disabled=True,
                                key="editor_busca" 
                           )
                 else:
                      st.info("Nenhum grupo encontrado nos chamados abertos para seleção.")
            else:
                 st.warning("Coluna 'Atribuir a um grupo' não encontrada para busca.")


    # --- Conteúdo da Tab 2 ---
    with tab2:
        # ... (código da Tab 2 permanece o mesmo) ...
        st.subheader("Resumo do Backlog Atual")
        if not df_aging.empty:
            total_chamados = len(df_aging)
            _, col_total_tab2, _ = st.columns([2, 1.5, 2])
            with col_total_tab2: st.markdown( f"""<div class="metric-box"><span class="label">Total de Chamados</span><span class="value">{total_chamados}</span></div>""", unsafe_allow_html=True )
            st.markdown("---")
            aging_counts_tab2 = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
            aging_counts_tab2.columns = ['Faixa de Antiguidade', 'Quantidade']
            ordem_faixas = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
            todas_as_faixas_tab2 = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas})
            aging_counts_tab2 = pd.merge(todas_as_faixas_tab2, aging_counts_tab2, on='Faixa de Antiguidade', how='left').fillna(0).astype({'Quantidade': int})
            aging_counts_tab2['Faixa de Antiguidade'] = pd.Categorical(aging_counts_tab2['Faixa de Antiguidade'], categories=ordem_faixas, ordered=True)
            aging_counts_tab2 = aging_counts_tab2.sort_values('Faixa de Antiguidade')
            cols_tab2 = st.columns(len(ordem_faixas))
            for i, row in aging_counts_tab2.iterrows():
                with cols_tab2[i]: st.markdown( f"""<div class="metric-box"><span class="label">{row['Faixa de Antiguidade']}</span><span class="value">{row['Quantidade']}</span></div>""", unsafe_allow_html=True )
            st.markdown("---")
            st.subheader("Distribuição do Backlog por Grupo")
            orientation_choice = st.radio( "Orientação do Gráfico:", ["Vertical", "Horizontal"], index=0, horizontal=True )
            
            if 'Atribuir a um grupo' in df_aging.columns and 'Faixa de Antiguidade' in df_aging.columns:
                 chart_data = df_aging.groupby(['Atribuir a um grupo', 'Faixa de Antiguidade']).size().reset_index(name='Quantidade')
                 group_totals = chart_data.groupby('Atribuir a um grupo')['Quantidade'].sum().sort_values(ascending=False)
                 
                 if not group_totals.empty:
                      new_labels_map = {group: f"{group} ({total})" for group, total in group_totals.items()}
                      chart_data['Atribuir a um grupo'] = chart_data['Atribuir a um grupo'].map(new_labels_map)
                      sorted_new_labels = [new_labels_map[group] for group in group_totals.index]
                      def lighten_color(hex_color, amount=0.2):
                          # ... (função lighten_color) ...
                          try:
                              hex_color = hex_color.lstrip('#')
                              h, l, s = colorsys.rgb_to_hls(*[int(hex_color[i:i+2], 16)/255.0 for i in (0, 2, 4)])
                              new_l = l + (1 - l) * amount
                              r, g, b = colorsys.hls_to_rgb(h, new_l, s)
                              return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
                          except Exception: return hex_color
                      base_color = "#375623"
                      palette = [ lighten_color(base_color, 0.85), lighten_color(base_color, 0.70), lighten_color(base_color, 0.55), lighten_color(base_color, 0.40), lighten_color(base_color, 0.20), base_color ]
                      color_map = {faixa: color for faixa, color in zip(ordem_faixas, palette)}
                      
                      if orientation_choice == 'Horizontal':
                          num_groups = len(group_totals)
                          dynamic_height = max(500, num_groups * 30) 
                          fig_stacked_bar = px.bar( chart_data, x='Quantidade', y='Atribuir a um grupo', orientation='h', color='Faixa de Antiguidade', title="Composição da Idade do Backlog por Grupo", labels={'Quantidade': 'Qtd. de Chamados', 'Atribuir a um grupo': ''}, category_orders={'Atribuir a um grupo': sorted_new_labels, 'Faixa de Antiguidade': ordem_faixas}, color_discrete_map=color_map, text_auto=True )
                          fig_stacked_bar.update_traces(textangle=0, textfont_size=12)
                          fig_stacked_bar.update_layout(height=dynamic_height, legend_title_text='Antiguidade', yaxis={'categoryorder':'array', 'categoryarray':sorted_new_labels[::-1]}) 
                      else: 
                          fig_stacked_bar = px.bar( chart_data, x='Atribuir a um grupo', y='Quantidade', color='Faixa de Antiguidade', title="Composição da Idade do Backlog por Grupo", labels={'Quantidade': 'Qtd. de Chamados', 'Atribuir a um grupo': 'Grupo'}, category_orders={'Atribuir a um grupo': sorted_new_labels, 'Faixa de Antiguidade': ordem_faixas}, color_discrete_map=color_map, text_auto=True )
                          fig_stacked_bar.update_traces(textangle=0, textfont_size=12)
                          fig_stacked_bar.update_layout(height=600, xaxis_title=None, xaxis_tickangle=-45, legend_title_text='Antiguidade')
                      
                      st.plotly_chart(fig_stacked_bar, use_container_width=True)
                 else:
                      st.info("Nenhum grupo encontrado para gerar o gráfico de distribuição.")
            else:
                 st.warning("Colunas necessárias ('Atribuir a um grupo', 'Faixa de Antiguidade') não encontradas para gerar o gráfico.")
        else:
            st.warning("Nenhum dado de aging disponível para gerar o report visual.")


    # --- Conteúdo da Tab 3 ---
    with tab3:
        # ... (código da Tab 3 permanece o mesmo) ...
        st.subheader("Evolução do Backlog")
        dias_evolucao = st.slider("Ver evolução dos últimos dias:", min_value=7, max_value=30, value=7, key="slider_evolucao")

        df_evolucao_tab3 = carregar_dados_evolucao(repo, dias_para_analisar=dias_evolucao)

        if not df_evolucao_tab3.empty:
            df_evolucao_tab3['Data'] = pd.to_datetime(df_evolucao_tab3['Data'])
            df_evolucao_semana = df_evolucao_tab3[df_evolucao_tab3['Data'].dt.dayofweek < 5].copy()

            if not df_evolucao_semana.empty:
                st.info("Esta visualização considera apenas os dados de snapshots de dias de semana e já aplica os filtros de grupos ocultos e RH.")

                df_total_diario = df_evolucao_semana.groupby('Data')['Total Chamados'].sum().reset_index()
                df_total_diario = df_total_diario.sort_values('Data')
                df_total_diario['Data (Eixo)'] = df_total_diario['Data'].dt.strftime('%d/%m')
                ordem_datas_total = df_total_diario['Data (Eixo)'].tolist()

                fig_total_evolucao = px.area(
                    df_total_diario, x='Data (Eixo)', y='Total Chamados',
                    title='Evolução do Total Geral de Chamados Abertos (Apenas Dias de Semana)',
                    markers=True, labels={"Data (Eixo)": "Data", "Total Chamados": "Total Geral de Chamados"},
                    category_orders={'Data (Eixo)': ordem_datas_total}
                )
                fig_total_evolucao.update_layout(height=400)
                st.plotly_chart(fig_total_evolucao, use_container_width=True)

                st.markdown("---")

                st.info("Clique na legenda para filtrar grupos. Clique duplo para isolar um grupo.")
                df_evolucao_semana_sorted = df_evolucao_semana.sort_values('Data')
                df_evolucao_semana_sorted['Data (Eixo)'] = df_evolucao_semana_sorted['Data'].dt.strftime('%d/%m')
                ordem_datas_grupo = df_evolucao_semana_sorted['Data (Eixo)'].unique().tolist()
                df_filtrado_display = df_evolucao_semana_sorted.rename(columns={'Atribuir a um grupo': 'Grupo Atribuído'})

                fig_evolucao_grupo = px.line(
                    df_filtrado_display, x='Data (Eixo)', y='Total Chamados', color='Grupo Atribuído',
                    title='Evolução por Grupo (Apenas Dias de Semana)', markers=True,
                    labels={ "Data (Eixo)": "Data", "Total Chamados": "Nº de Chamados", "Grupo Atribuído": "Grupo" },
                    category_orders={'Data (Eixo)': ordem_datas_grupo}
                )
                fig_evolucao_grupo.update_layout(height=600)
                st.plotly_chart(fig_evolucao_grupo, use_container_width=True)

            else:
                st.info("Não há dados históricos suficientes considerando apenas dias de semana.")
        else:
            st.info("Não foi possível carregar dados históricos para a evolução.")


    # --- Conteúdo da Tab 4 ---
    with tab4:
        # ... (código da Tab 4 permanece o mesmo) ...
        st.subheader("Evolução do Aging do Backlog")
        st.info("Esta aba compara a 'foto' do aging de hoje com a 'foto' de dias anteriores, usando a mesma data de referência (hoje) para calcular a idade em ambos os momentos.")

        try:
            df_hist = carregar_evolucao_aging(repo, dias_para_analisar=90)

            ordem_faixas_scaffold = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
            hoje_data = None
            hoje_counts_df = pd.DataFrame() 

            if 'df_aging' in locals() and not df_aging.empty and data_atual_str != 'N/A':
                try:
                    hoje_data = pd.to_datetime(datetime.strptime(data_atual_str, "%d/%m/%Y").date())
                    hoje_counts_raw = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
                    hoje_counts_raw.columns = ['Faixa de Antiguidade', 'total']
                    df_todas_faixas_hoje = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas_scaffold})
                    hoje_counts_df = pd.merge(
                        df_todas_faixas_hoje, hoje_counts_raw,
                        on='Faixa de Antiguidade', how='left'
                    ).fillna(0)
                    hoje_counts_df['total'] = hoje_counts_df['total'].astype(int)
                    hoje_counts_df['data'] = hoje_data 
                except ValueError:
                    st.warning("Data atual ('datas_referencia.txt') inválida. Não foi possível processar dados de 'hoje' para comparação.")
                    hoje_data = None 
            else:
                st.warning("Não foi possível carregar ou processar dados de 'hoje' (df_aging).")


            if not df_hist.empty and not hoje_counts_df.empty:
                 df_combinado = pd.concat([df_hist, hoje_counts_df], ignore_index=True)
                 df_combinado = df_combinado.drop_duplicates(subset=['data', 'Faixa de Antiguidade'], keep='last') 
            elif not df_hist.empty:
                 df_combinado = df_hist.copy()
                 st.warning("Dados de 'hoje' não disponíveis para comparação.")
            elif not hoje_counts_df.empty:
                 df_combinado = hoje_counts_df.copy()
                 st.warning("Dados históricos não disponíveis para comparação.")
            else:
                 st.error("Não há dados históricos nem dados de hoje para a análise de aging.")
                 st.stop() 

            df_combinado['data'] = pd.to_datetime(df_combinado['data'])
            df_combinado = df_combinado.sort_values(by=['data', 'Faixa de Antiguidade'])


            st.markdown("##### Comparativo")
            periodo_comp_opts = { "Ontem": 1, "7 dias atrás": 7, "15 dias atrás": 15, "30 dias atrás": 30 }
            periodo_comp_selecionado = st.radio(
                "Comparar 'Hoje' com:", options=periodo_comp_opts.keys(),
                horizontal=True, key="radio_comp_periodo"
            )

            data_comparacao_final = None
            df_comparacao_dados = pd.DataFrame()
            data_comparacao_str = "N/A"

            if hoje_data:
                target_comp_date = hoje_data.date() - timedelta(days=periodo_comp_opts[periodo_comp_selecionado])
                data_comparacao_encontrada, _ = find_closest_snapshot_before(repo, hoje_data.date(), target_comp_date)

                if data_comparacao_encontrada:
                    data_comparacao_final = pd.to_datetime(data_comparacao_encontrada)
                    data_comparacao_str = data_comparacao_final.strftime('%d/%m')
                    df_comparacao_dados = df_combinado[df_combinado['data'] == data_comparacao_final].copy()
                    if df_comparacao_dados.empty:
                         st.warning(f"Snapshot de {data_comparacao_str} encontrado, mas sem dados válidos após processamento.")
                         data_comparacao_final = None 
                else:
                    st.warning(f"Não foi encontrado snapshot próximo a {periodo_comp_selecionado} ({target_comp_date.strftime('%d/%m')}).")

            cols_linha1 = st.columns(3)
            cols_linha2 = st.columns(3)
            cols_map = {0: cols_linha1[0], 1: cols_linha1[1], 2: cols_linha1[2],
                        3: cols_linha2[0], 4: cols_linha2[1], 5: cols_linha2[2]}

            for i, faixa in enumerate(ordem_faixas_scaffold):
                with cols_map[i]:
                    valor_hoje = 'N/A'
                    delta_text = "N/A"
                    delta_class = "delta-neutral"

                    if not hoje_counts_df.empty:
                        valor_hoje_series = hoje_counts_df.loc[hoje_counts_df['Faixa de Antiguidade'] == faixa, 'total']
                        if not valor_hoje_series.empty:
                            valor_hoje = int(valor_hoje_series.iloc[0])

                            if data_comparacao_final and not df_comparacao_dados.empty:
                                valor_comp_series = df_comparacao_dados.loc[df_comparacao_dados['Faixa de Antiguidade'] == faixa, 'total']
                                if not valor_comp_series.empty:
                                    valor_comparacao = int(valor_comp_series.iloc[0])
                                    delta_abs = valor_hoje - valor_comparacao
                                    delta_perc = (delta_abs / valor_comparacao) if valor_comparacao > 0 else 0
                                    delta_text, delta_class = formatar_delta_card(delta_abs, delta_perc, valor_comparacao, data_comparacao_str)
                                else:
                                     valor_comparacao = 0 # Define como 0 se a faixa não existia antes
                                     delta_abs = valor_hoje - valor_comparacao
                                     delta_text, delta_class = formatar_delta_card(delta_abs, 0, valor_comparacao, data_comparacao_str)
                            elif hoje_data: 
                                 delta_text = "Sem dados para comparar"
                        else: 
                             valor_hoje = 0 
                             delta_text = "N/A"
                    
                    elif not hoje_data:
                         delta_text = "Dados de hoje indisponíveis"

                    st.markdown(f"""
                    <div class="metric-box">
                        <span class="label">{faixa}</span>
                        <span class="value">{valor_hoje}</span>
                        <span class="delta {delta_class}">{delta_text}</span>
                    </div>
                    """, unsafe_allow_html=True)

            st.divider()

            st.markdown(f"##### Gráfico de Evolução (Últimos 7 dias)")
            
            hoje_filtro_grafico = datetime.now().date()
            data_inicio_filtro_grafico = hoje_filtro_grafico - timedelta(days=6) 
            df_filtrado_grafico = df_combinado[df_combinado['data'].dt.date >= data_inicio_filtro_grafico].copy()

            if df_filtrado_grafico.empty:
                st.warning("Não há dados de aging para os últimos 7 dias.")
            else:
                df_grafico = df_filtrado_grafico.sort_values(by='data')
                df_grafico['Data (Eixo)'] = df_grafico['data'].dt.strftime('%d/%m')
                ordem_datas_grafico = df_grafico['Data (Eixo)'].unique().tolist() 

                # ... (código da paleta de cores e tipo de gráfico) ...
                def lighten_color(hex_color, amount=0.2):
                    # ... (função lighten_color) ...
                    try:
                        hex_color = hex_color.lstrip('#')
                        h, l, s = colorsys.rgb_to_hls(*[int(hex_color[i:i+2], 16)/255.0 for i in (0, 2, 4)])
                        new_l = l + (1 - l) * amount
                        r, g, b = colorsys.hls_to_rgb(h, new_l, s)
                        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
                    except Exception: return hex_color
                base_color = "#375623"
                palette = [ lighten_color(base_color, 0.85), lighten_color(base_color, 0.70), lighten_color(base_color, 0.55), lighten_color(base_color, 0.40), lighten_color(base_color, 0.20), base_color ]
                color_map = {faixa: color for faixa, color in zip(ordem_faixas_scaffold, palette)}

                tipo_grafico = st.radio(
                    "Selecione o tipo de gráfico:",
                    ("Gráfico de Linha (Comparativo)", "Gráfico de Área (Composição)"),
                    horizontal=True, key="radio_tipo_grafico_aging"
                )

                if tipo_grafico == "Gráfico de Linha (Comparativo)":
                    fig_aging_all = px.line(
                        df_grafico, x='Data (Eixo)', y='total', color='Faixa de Antiguidade',
                        title='Evolução por Faixa de Antiguidade (Últimos 7 dias)', markers=True,
                        labels={"Data (Eixo)": "Data", "total": "Total Chamados", "Faixa de Antiguidade": "Faixa"},
                        category_orders={'Data (Eixo)': ordem_datas_grafico, 'Faixa de Antiguidade': ordem_faixas_scaffold},
                        color_discrete_map=color_map
                    )
                else: 
                    fig_aging_all = px.area(
                        df_grafico, x='Data (Eixo)', y='total', color='Faixa de Antiguidade',
                        title='Composição da Evolução por Antiguidade (Últimos 7 dias)', markers=True,
                        labels={"Data (Eixo)": "Data", "total": "Total Chamados", "Faixa de Antiguidade": "Faixa"},
                        category_orders={'Data (Eixo)': ordem_datas_grafico, 'Faixa de Antiguidade': ordem_faixas_scaffold},
                        color_discrete_map=color_map
                    )

                fig_aging_all.update_layout(height=500, legend_title_text='Faixa')
                st.plotly_chart(fig_aging_all, use_container_width=True)

        except Exception as e:
            st.error(f"Ocorreu um erro ao gerar a aba de Evolução Aging: {e}")
            st.exception(e) 

except Exception as e:
    st.error(f"Ocorreu um erro GERAL ao carregar ou processar os dados: {e}")
    st.exception(e) 

st.markdown("---")
# Atualiza versão no rodapé
st.markdown(""" 
<p style='text-align: center; color: #666; font-size: 0.9em; margin-bottom: 0;'>v0.9.32 | Este dashboard está em desenvolvimento.</p>
<p style='text-align: center; color: #666; font-size: 0.9em; margin-top: 0;'>Desenvolvido por Leonir Scatolin Junior</p>
""", unsafe_allow_html=True)
