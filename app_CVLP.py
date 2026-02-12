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
        # Lê usando encoding utf-8-sig para não quebrar acentos
        df_antigo = pd.read_csv(arquivo, sep=';', encoding='utf-8-sig')
        df_final = pd.concat([df_antigo, df_novo], ignore_index=True)
    else:
        df_final = df_novo
        
    # Salva com Ponto e Vírgula e encoding específico para Excel não bugar acentos
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
        return None, "Erro: Binários não encontrados."

    options = webdriver.ChromeOptions()
    options.binary_location = chrome_path
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    prefs = {"download.default_directory": download_dir, "download.prompt_for_download": False}
    options.add_experimental_option("prefs", prefs)
    
    driver = None
    try:
        service = Service(executable_path=driver_path)
        driver = webdriver.Chrome(service=service, options=options)
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
                time.sleep(2)
                df = pd.read_csv(arquivos[0], sep=';', encoding='ISO-8859-1', skiprows=2)
                df = tratar_texto_caixa(df)
                csv_data = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
                driver.quit()
                return csv_data, len(df)
            time.sleep(2)
    except Exception as e:
        if driver: driver.quit()
        return None, f"Erro: {str(e)}"
    return None, "Tempo esgotado."

# --- INTERFACE PRINCIPAL ---
def main():
    caminho_logo = "logo.jpg"
    if os.path.exists(caminho_logo):
        st.sidebar.image(caminho_logo, use_container_width=True)

    st.title("⚖️ Calculadora de Viabilidade Leilão")

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

    # --- INPUTS (SIMPLIFICADO PARA O SCRIPT) ---
    with st.expander("💵 Valores", expanded=True):
        v_avaliacao = st.number_input("Valor de Avaliação (R$)", value=float(d["avaliacao"]))
        v_lance = st.number_input("Valor do Lance (R$)", value=float(d["lance"]))
        invest_total = v_lance * 1.1 # Exemplo
        lucro_liq = (v_avaliacao - invest_total)
        roi = (lucro_liq / invest_total * 100) if invest_total > 0 else 0

    # --- SALVAR ---
    if st.button("💾 Salvar Simulação na Tabela"):
        dados = {
            "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "Tipo": tipo_imovel,
            "Avaliação": v_avaliacao,
            "Lance": v_lance,
            "Investimento Inicial": invest_total,
            "Lucro Líquido": lucro_liq,
            "ROI %": round(roi, 2)
        }
        salvar_dados(dados)
        st.toast("Salvo!", icon="✅")

    # --- HISTÓRICO ---
    st.markdown("---")
    st.subheader("📜 Histórico de Simulações")
    arquivo_hist = "historico_simulacoes.csv"
    
    if os.path.exists(arquivo_hist):
        df_hist = pd.read_csv(arquivo_hist, sep=';', encoding='utf-8-sig')
        
        # 1. REMOVE O BOTÃO DE DOWNLOAD NATIVO (QUE É O QUE BUGAVA TUDO)
        # 2. ADICIONA O ÍCONE DE LIXEIRA NA ESQUERDA PARA EXCLUIR LINHAS
        edited_df = st.data_editor(
            df_hist, 
            use_container_width=True, 
            num_rows="dynamic",
            key="historico_editor",
            column_config={
                "Data": st.column_config.TextColumn(disabled=True),
            }
        )
        
        # Se você deletar uma linha na tabela, ele salva o arquivo de novo
        if len(edited_df) != len(df_hist):
            edited_df.to_csv(arquivo_hist, index=False, sep=';', encoding='utf-8-sig')
            st.rerun()

        # BOTÃO DE DOWNLOAD QUE REALMENTE FUNCIONA NO EXCEL BRASIL
        st.write("Para baixar sem erros de colunas ou acentos, use o botão abaixo:")
        csv_excel = edited_df.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
        st.download_button(
            label="📥 Baixar Histórico para Excel",
            data=csv_excel,
            file_name=f"historico_leilao_{datetime.now().strftime('%d_%m_%Y')}.csv",
            mime="text/csv",
        )

        if st.button("🗑️ Limpar Tudo"):
            os.remove(arquivo_hist)
            st.rerun()
    else:
        st.info("Sem dados.")

if __name__ == "__main__":
    main()

