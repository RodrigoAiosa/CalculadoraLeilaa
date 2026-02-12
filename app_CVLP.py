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

def preparar_para_excel_br(df):
    """Força a conversão de todos os pontos decimais para vírgulas em todas as colunas numéricas."""
    df_br = df.copy()
    for col in df_br.columns:
        # Se a coluna for numérica, converte para string trocando . por ,
        if pd.api.types.is_numeric_dtype(df_br[col]):
            df_br[col] = df_br[col].apply(lambda x: str(x).replace('.', ','))
    return df_br

def tratar_texto_caixa(df):
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
    return df

# --- FUNÇÃO PARA SALVAR DADOS ---
def salvar_dados(nova_simulacao):
    arquivo = "historico_simulacoes.csv"
    df_novo = pd.DataFrame([nova_simulacao])
    
    if os.path.exists(arquivo):
        # Lê o que já existe (usamos sep=; e decimal=, para consistência)
        df_antigo = pd.read_csv(arquivo, sep=';', decimal=',', encoding='utf-8-sig')
        df_final = pd.concat([df_antigo, df_novo], ignore_index=True)
    else:
        df_final = df_novo
        
    # SALVAMENTO CRÍTICO: sep=; decimal=, encoding=utf-8-sig
    df_final.to_csv(arquivo, index=False, sep=';', decimal=',', encoding='utf-8-sig')
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

    options = webdriver.ChromeOptions()
    options.binary_location = chrome_path
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    
    prefs = {"download.default_directory": download_dir, "download.prompt_for_download": False}
    options.add_experimental_option("prefs", prefs)
    
    driver = None
    try:
        service = Service(executable_path=driver_path)
        driver = webdriver.Chrome(service=service, options=options)
        driver.get("https://venda-imoveis.caixa.gov.br/sistema/download-lista.asp")
        wait = WebDriverWait(driver, 25)
        Select(wait.until(EC.presence_of_element_located((By.ID, "cmb_estado")))).select_by_value("geral")
        driver.execute_script("arguments[0].click();", wait.until(EC.element_to_be_clickable((By.ID, "btn_next1"))))

        timeout = 90
        start = time.time()
        while time.time() - start < timeout:
            arquivos = glob.glob(os.path.join(download_dir, "*.csv"))
            if arquivos:
                time.sleep(2)
                df = pd.read_csv(arquivos[0], sep=';', encoding='ISO-8859-1', skiprows=2)
                df = tratar_texto_caixa(df)
                # Exporta para a interface do Streamlit corrigido
                csv_data = df.to_csv(index=False, sep=';', decimal=',', encoding='utf-8-sig')
                driver.quit()
                return csv_data, len(df)
            time.sleep(2)
    except Exception as e:
        if driver: driver.quit()
        return None, f"Erro: {str(e)}"
    return None, "Tempo esgotado."

# --- INTERFACE ---
def main():
    st.title("⚖️ Calculadora de Viabilidade Leilão")

    # PERFIL
    tipo_imovel = st.sidebar.selectbox("Tipo:", ["Apartamento", "Casa", "Terreno"])
    v_avaliacao = st.number_input("Avaliação (R$)", value=250000.0)
    v_lance = st.number_input("Lance (R$)", value=150000.0)
    
    lucro_liq = v_avaliacao - v_lance
    roi = (lucro_liq / v_lance * 100) if v_lance > 0 else 0

    if st.button("💾 Salvar na Tabela"):
        dados = {
            "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "Tipo": tipo_imovel,
            "Avaliação": v_avaliacao,
            "Lance": v_lance,
            "Lucro Líquido": lucro_liq,
            "ROI %": round(roi, 2)
        }
        salvar_dados(dados)
        st.success("Salvo!")

    st.markdown("---")
    st.subheader("📜 Histórico")
    arquivo_hist = "historico_simulacoes.csv"
    
    if os.path.exists(arquivo_hist):
        # Carrega os dados
        df_hist = pd.read_csv(arquivo_hist, sep=';', decimal=',', encoding='utf-8-sig')
        
        # Exibe editor
        edited_df = st.data_editor(df_hist, use_container_width=True, num_rows="dynamic")
        
        if len(edited_df) != len(df_hist):
            edited_df.to_csv(arquivo_hist, index=False, sep=';', decimal=',', encoding='utf-8-sig')
            st.rerun()

        # BOTÃO DE DOWNLOAD FINAL (A SOLUÇÃO)
        # Transformamos todos os números em strings com vírgula ANTES de baixar
        df_para_baixar = preparar_para_excel_br(edited_df)
        
        st.download_button(
            label="📥 BAIXAR EXCEL",
            data=df_para_baixar.to_csv(index=False, sep=';', encoding='utf-8-sig'),
            file_name=f"historico_leilao_corrigido.csv",
            mime="text/csv",
        )
    else:
        st.info("Histórico vazio.")

if __name__ == "__main__":
    main()
