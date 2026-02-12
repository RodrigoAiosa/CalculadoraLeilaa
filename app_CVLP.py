import streamlit as st
import pandas as pd
import io
import os
import time
import glob
import shutil
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Calculadora de Viabilidade Leilão", layout="wide", page_icon="⚖️")

def format_brl(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_csv_para_excel(df):
    """Converte números com ponto decimal para vírgula e adiciona formatação de moeda"""
    df_formatado = df.copy()
    
    # Colunas que devem ser formatadas como moeda
    colunas_moeda = ['Avaliacao', 'Lance', 'Investimento Inicial', 'Lucro Liquido']
    
    for col in df_formatado.columns:
        if df_formatado[col].dtype in ['float64', 'int64']:
            if col in colunas_moeda:
                # Formatar como moeda brasileira
                df_formatado[col] = df_formatado[col].apply(
                    lambda x: f'R$ {x:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.') if pd.notna(x) else x
                )
            else:
                # Apenas substituir ponto por vírgula (para ROI % e outros números)
                df_formatado[col] = df_formatado[col].apply(
                    lambda x: str(x).replace('.', ',') if pd.notna(x) else x
                )
    return df_formatado

def tratar_texto_caixa(df):
    """Corrige os erros de codificação brutais da Caixa e remove espaços."""
    mapa = {
        'NÂ°': 'N°', 'imÃ³vel': 'imóvel', 'EndereÃ§o': 'Endereço', 
        'PreÃ§o': 'Preço', 'avaliaÃ§Ã£o': 'avaliação', 'DescriÃ§Ã£o': 'Descrição',
        'Ã§Ã£o': 'ção', 'Ã³': 'ó', 'Ã¢': 'â', 'Ã©': 'é', 'Ãº': 'ú', 'Ã': 'á'
    }
    df.columns = [c.strip() for c in df.columns]
    for col in df.columns:
        for erro, correto in mapa.items():
            if erro in col:
                df.rename(columns={col: col.replace(erro, correto)}, inplace=True)
    
    cols_obj = df.select_dtypes(include=['object']).columns
    for col in cols_obj:
        for erro, correto in mapa.items():
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(erro, correto)
    return df

# --- FUNÇÃO PARA SALVAR E ACUMULAR DADOS ---
def salvar_dados(nova_simulacao):
    arquivo = "historico_simulacoes.csv"
    df_novo = pd.DataFrame([nova_simulacao])
    
    if os.path.exists(arquivo):
        df_antigo = pd.read_csv(arquivo, sep=';', encoding='utf-8-sig')
        df_final = pd.concat([df_antigo, df_novo], ignore_index=True)
    else:
        df_final = df_novo
        
    df_final.to_csv(arquivo, index=False, sep=';', encoding='utf-8-sig')
    return df_final

# --- MOTOR DE SCRAPING ---
def robo_caixa():
    download_dir = os.path.join(os.getcwd(), "temp_caixa")
    if not os.path.exists(download_dir): os.makedirs(download_dir)
    
    for f in glob.glob(os.path.join(download_dir, "*.csv")):
        try: os.remove(f)
        except: pass

    chrome_path = shutil.which("chromium") or shutil.which("google-chrome")
    driver_path = shutil.which("chromedriver")

    if not chrome_path or not driver_path:
        return None, "Erro: Binários não encontrados. Verifique o packages.txt."

    options = webdriver.ChromeOptions()
    options.binary_location = chrome_path
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    prefs = {"download.default_directory": download_dir, "download.prompt_for_download": False}
    options.add_experimental_option("prefs", prefs)
    
    driver = None
    try:
        service = Service(executable_path=driver_path)
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)
        driver.get("https://venda-imoveis.caixa.gov.br/sistema/download-lista.asp")
        
        wait = WebDriverWait(driver, 25)
        dropdown = wait.until(EC.presence_of_element_located((By.ID, "cmb_estado")))
        Select(dropdown).select_by_value("geral")
        
        btn = wait.until(EC.element_to_be_clickable((By.ID, "btn_next1")))
        driver.execute_script("arguments[0].click();", btn)

        timeout = 90
        start = time.time()
        while time.time() - start < timeout:
            arquivos = glob.glob(os.path.join(download_dir, "*.csv"))
            if arquivos:
                time.sleep(3)
                df = pd.read_csv(arquivos[0], sep=';', encoding='ISO-8859-1', skiprows=2)
                df = tratar_texto_caixa(df)
                csv_data = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
                driver.quit()
                return csv_data, len(df)
            time.sleep(3)
    except Exception as e:
        if driver: driver.quit()
        return None, f"Erro: {str(e)}"
    return None, "Tempo esgotado."

# --- INTERFACE PRINCIPAL ---
def main():
    # --- LOGOTIPO NA SIDEBAR ---
    caminho_logo = "logo.jpg"
    
    if os.path.exists(caminho_logo):
        st.sidebar.image(caminho_logo, use_container_width=True)
    else:
        st.sidebar.warning("Logo não encontrado no caminho local. Tentando pasta raiz...")
        arquivos_imagem = glob.glob("logo.*")
        if arquivos_imagem:
            st.sidebar.image(arquivos_imagem[0], use_container_width=True)

    st.title("⚖️ Calculadora de Viabilidade Leilão - **ARREMATE SEM MEDO**")

    # --- SIDEBAR: PERFIS ---
    st.sidebar.header("🚀 Perfil de Investimento")
    tipo_imovel = st.sidebar.selectbox("Selecione o tipo de imóvel:", ["Apartamento", "Casa", "Terreno", "Gleba"])
    perfil = st.sidebar.selectbox("Escolha um perfil:", ["Manual", "Apartamento Popular", "Médio Padrão", "Alto Padrão"])

    defaults = {
        "Manual": {"avaliacao": 0.0, "lance": 0.0, "desocupa": 0.0, "reforma": 0.0, "condo": 0.0, "iptu": 0.0, "venda": 0.0, "agua": 0.0, "luz": 0.0, "gas": 0.0},
        "Apartamento Popular": {"avaliacao": 250000.0, "lance": 160000.0, "desocupa": 8000.0, "reforma": 20000.0, "condo": 350.0, "iptu": 60.0, "venda": 245000.0, "agua": 60.0, "luz": 120.0, "gas": 45.0},
        "Médio Padrão": {"avaliacao": 750000.0, "lance": 450000.0, "desocupa": 5000.0, "reforma": 35000.0, "condo": 800.0, "iptu": 200.0, "venda": 700000.0, "agua": 90.0, "luz": 250.0, "gas": 85.0},
        "Alto Padrão": {"avaliacao": 2500000.0, "lance": 1300000.0, "desocupa": 0.0, "reforma": 120000.0, "condo": 2200.0, "iptu": 900.0, "venda": 2200000.0, "agua": 180.0, "luz": 650.0, "gas": 150.0}
    }
    d = defaults[perfil]

    # --- BLOCO 1: ARREMATAÇÃO ---
    with st.expander("💵 Arrematação", expanded=True):
        col_inp, col_mem = st.columns([3, 2])
        with col_inp:
            v_avaliacao = st.number_input("Valor de Avaliação (R$)", value=float(d["avaliacao"]))
            tipo_compra = st.radio("Pagamento:", ["À Vista", "Financiado"], horizontal=True)
            v_lance = st.number_input("Valor do Lance (R$)", value=float(d["lance"]))
            
            v_entrada, v_financiado, juros_mensal, v_prestacao = 0.0, 0.0, 0.0, 0.0
            if tipo_compra == "Financiado":
                v_entrada = st.number_input("Entrada (R$)", value=float(v_lance * 0.20))
                v_financiado = v_lance - v_entrada
                j_anual = st.number_input("Taxa Juros (% a.a.)", value=9.5)
                juros_mensal = (1 + j_anual/100)**(1/12) - 1
                v_prestacao = st.number_input("Prestação Mensal (R$)", value=0.0)
            else:
                v_entrada = v_lance

            taxas_docs = st.number_input("Leiloeiro/ITBI/Registro (R$)", value=float(v_lance * 0.08))
            desocupa = st.number_input("Desocupação (R$)", value=float(d["desocupa"]))
            total_b1 = v_entrada + taxas_docs + desocupa
        with col_mem: st.metric("Total Arrematação", format_brl(total_b1))

    # --- BLOCO 2: CUSTOS ---
    with st.expander("🔗 Custos Intermediários", expanded=True):
        col_inp2, col_mem2 = st.columns([3, 2])
        with col_inp2:
            reforma = st.number_input("Reforma (R$)", value=float(d["reforma"]))
            meses = st.number_input("Meses até a Venda", value=7)
            contas_mes = st.number_input("Água+Luz+Condo+IPTU+Gás (R$/mês)", value=float(d["agua"]+d["luz"]+d["condo"]+d["iptu"]+d["gas"]))
            total_contas = contas_mes * meses
            juros_obra = (v_prestacao * meses) if v_prestacao > 0 else (v_financiado * juros_mensal * meses)
            total_b2 = reforma + total_contas + juros_obra
        with col_mem2: st.metric("Total Intermediários", format_brl(total_b2))

    # --- BLOCO 3: VENDA ---
    with st.expander("🏷️ Venda e Lucro", expanded=True):
        col_v1, col_v2 = st.columns([3, 2])
        with col_v1:
            v_venda = st.number_input("Preço de Venda (R$)", value=float(d["venda"]))
            p_corretor = st.number_input("Comissão Corretor (%)", value=5.0)
            v_comis = v_venda * (p_corretor / 100)
            st.caption(f"Comissão Corretor: {format_brl(v_comis)}")
            
            p_imp = st.number_input("Imposto sobre Ganho (%)", value=15.0)
            
            invest_total = total_b1 + total_b2
            lucro_bruto = (v_venda - v_comis) - v_financiado - invest_total
            v_imp = max(0.0, lucro_bruto * (p_imp / 100))
            lucro_liq = lucro_bruto - v_imp
            roi = (lucro_liq / invest_total * 100) if invest_total > 0 else 0

        with col_v2:
            if lucro_liq >= 0:
                st.success(f"### Lucro: {format_brl(lucro_liq)}\n### ROI: {roi:.2f}%")
            else:
                st.error(f"### Prejuízo: {format_brl(lucro_liq)}\n### ROI: {roi:.2f}%")

    # --- BOTÃO PARA SALVAR SIMULAÇÃO ---
    if st.button("💾 Salvar Simulação na Tabela"):
        dados = {
            "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "Tipo": tipo_imovel,
            "Avaliacao": v_avaliacao,
            "Lance": v_lance,
            "Investimento Inicial": invest_total,
            "Lucro Liquido": lucro_liq,
            "ROI %": round(roi, 2)
        }
        salvar_dados(dados)
        st.toast("Simulação salva com sucesso!", icon="✅")

    # --- TABELA DE HISTÓRICO COM EXCLUSÃO INDIVIDUAL ---
    st.markdown("---")
    st.subheader("📜 Histórico de Simulações")
    arquivo_hist = "historico_simulacoes.csv"
    
    if os.path.exists(arquivo_hist):
        df_hist = pd.read_csv(arquivo_hist, sep=';', encoding='utf-8-sig')
        
        # O data_editor permite o ícone de lixeira (que remove a linha)
        # Ao clicar no ícone de lixeira ao lado do índice, a linha é marcada para deleção
        edited_df = st.data_editor(
            df_hist, 
            use_container_width=True, 
            num_rows="dynamic",
            key="historico_editor"
        )
        
        # Se o número de linhas mudar, salvamos o novo arquivo
        if len(edited_df) != len(df_hist):
            edited_df.to_csv(arquivo_hist, index=False, sep=';', encoding='utf-8-sig')
            st.rerun()

        # Botões de ação com alinhamento
        col_btn1, col_spacer, col_btn2 = st.columns([1, 6, 1])
        with col_btn1:
            # Botão de download CSV com separação correta por coluna (ponto e vírgula para Excel BR)
            df_download = formatar_csv_para_excel(edited_df)
            csv_download = df_download.to_csv(index=False, sep=';', encoding='utf-8-sig')
            st.download_button(
                label="📥 Download as CSV",
                data=csv_download,
                file_name=f"historico_simulacoes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        with col_btn2:
            # Botão para limpar histórico total
            if st.button("🗑️ Limpar Histórico"):
                os.remove(arquivo_hist)
                st.rerun()
    else:
        st.info("Nenhuma simulação salva ainda.")

    # --- RELATÓRIO EXCEL ---
    def exportar():
        output = io.BytesIO()
        try:
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                pd.DataFrame([{"Data": datetime.now(), "Tipo": tipo_imovel, "Lucro": lucro_liq, "ROI %": roi}]).to_excel(writer, index=False, sheet_name='Resumo')
                pd.DataFrame([
                    {"Categoria": "Arrematação (Entrada + Docs)", "Valor": total_b1},
                    {"Categoria": "Custos (Reforma + Manutenção)", "Valor": total_b2},
                    {"Categoria": "Comissão Corretor", "Valor": v_comis},
                    {"Categoria": "Imposto", "Valor": v_imp}
                ]).to_excel(writer, index=False, sheet_name='Detalhes')
            return output.getvalue()
        except:
            return None

    st.sidebar.markdown("---")
    st.sidebar.download_button("📥 BAIXAR EXCEL ÚNICO", exportar(), f"simulacao_{tipo_imovel}.xlsx")

if __name__ == "__main__":
    main()

