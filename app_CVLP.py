import streamlit as st
import pandas as pd
import io
import os
import time
import glob
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

# Configuração da página
st.set_page_config(page_title="Calculadora de Viabilidade Leilão", layout="wide")

def format_brl(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def tratar_texto_caixa(df):
    mapa_sujeira = {
        'NÂ° do imÃ³vel': 'N° do Imóvel', 'NÂ° do imÃ³ve': 'N° do Imóvel',
        'EndereÃ§o': 'Endereço', 'PreÃ§o': 'Preço',
        'Valor de avaliaÃ§Ã£o': 'Valor de Avaliação', 'DescriÃ§Ã£o': 'Descrição',
        'Ã§Ã£o': 'ção', 'Ã³': 'ó', 'Ã¢': 'â', 'Ã©': 'é', 'Ãº': 'ú', 'Ã': 'á'
    }
    df.columns = [c.strip() for c in df.columns]
    for erro, correto in mapa_sujeira.items():
        df.columns = [c.replace(erro, correto) if erro in c else c for c in df.columns]
    cols_obj = df.select_dtypes(include=['object']).columns
    for col in cols_obj:
        for erro, correto in mapa_sujeira.items():
            df[col] = df[col].astype(str).str.replace(erro, correto)
    return df

def aguardar_download_concluido(diretorio, timeout=150):
    segundos = 0
    while segundos < timeout:
        arquivos = os.listdir(diretorio)
        if any(f.endswith(".csv") for f in arquivos) and not any(f.endswith(".crdownload") for f in arquivos):
            return True
        time.sleep(2)
        segundos += 2
    return False

def robo_caixa():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    download_dir = os.path.join(base_dir, "temp_caixa")
    if not os.path.exists(download_dir): os.makedirs(download_dir)
    for f in glob.glob(os.path.join(download_dir, "*.csv")):
        try: os.remove(f)
        except: pass

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--remote-debugging-port=9222")
    
    # Se estiver no Streamlit Cloud, o binário costuma estar aqui
    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"

    prefs = {"download.default_directory": download_dir, "download.prompt_for_download": False}
    options.add_experimental_option("prefs", prefs)
    
    driver = None
    try:
        # Tenta Chromedriver do sistema ou baixa automaticamente
        if os.path.exists("/usr/bin/chromedriver"):
            service = Service("/usr/bin/chromedriver")
        else:
            service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
            
        driver = webdriver.Chrome(service=service, options=options)
        driver.get("https://venda-imoveis.caixa.gov.br/sistema/download-lista.asp")
        
        wait = WebDriverWait(driver, 40)
        dropdown = wait.until(EC.presence_of_element_located((By.ID, "cmb_estado")))
        Select(dropdown).select_by_value("geral")
        
        # Clique via JavaScript para evitar problemas de interceptação no Linux
        btn = wait.until(EC.element_to_be_clickable((By.ID, "btn_next1")))
        driver.execute_script("arguments[0].click();", btn)

        if aguardar_download_concluido(download_dir):
            time.sleep(3)
            lista_arquivos = glob.glob(os.path.join(download_dir, "*.csv"))
            arquivo_recente = max(lista_arquivos, key=os.path.getctime)
            df = pd.read_csv(arquivo_recente, sep=';', encoding='ISO-8859-1', skiprows=2)
            df = tratar_texto_caixa(df)
            df['data_hora_inf'] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            csv_buffer = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
            driver.quit()
            return csv_buffer, len(df)
            
    except Exception as e:
        if driver: driver.quit()
        return None, f"Erro detalhado: {str(e)}"
    
    return None, "O download não foi detectado a tempo."

def main():
    st.title("⚖️ Calculadora de Viabilidade Leilão Profissional")

    # --- SIDEBAR ---
    st.sidebar.header("🚀 Configurações")
    tipo_imovel = st.sidebar.selectbox("Tipo de Imóvel:", ["Apartamento", "Casa", "Terreno", "Gleba"])
    perfil = st.sidebar.selectbox("Perfil de Custos:", ["Manual", "Apartamento Popular", "Médio Padrão", "Alto Padrão"])

    defaults = {
        "Manual": {"avaliacao": 0.0, "lance": 0.0, "reforma": 0.0, "venda": 0.0, "fixos": 0.0},
        "Apartamento Popular": {"avaliacao": 250000.0, "lance": 160000.0, "reforma": 20000.0, "venda": 245000.0, "fixos": 600.0}
    }
    d = defaults.get(perfil, defaults["Manual"])

    # --- BLOCO 0: DADOS CAIXA ---
    with st.expander("🏢 Extrair Lista da Caixa", expanded=False):
        if st.button("🚀 Iniciar Coleta"):
            with st.spinner("O Robô está navegando na Caixa..."):
                csv_data, res = robo_caixa()
                if csv_data:
                    st.success(f"Concluído! {res} imóveis encontrados.")
                    st.download_button("💾 Baixar CSV Limpo", csv_data, "caixa_limpo.csv", "text/csv")
                else: st.error(res)

    # --- CÁLCULOS RÁPIDOS ---
    with st.container():
        c1, c2 = st.columns(2)
        v_lance = c1.number_input("Valor do Lance (R$)", value=float(d["lance"]))
        v_venda = c2.number_input("Valor de Venda (R$)", value=float(d["venda"]))
        
        taxas = v_lance * 0.08 # ITBI + Leiloeiro + Docs
        reforma = st.number_input("Reforma (R$)", value=float(d["reforma"]))
        p_comis = st.number_input("Comissão Corretor (%)", value=5.0)
        v_comis = v_venda * (p_comis/100)
        
        invest = v_lance + taxas + reforma
        lucro = (v_venda - v_comis) - invest
        roi = (lucro / invest * 100) if invest > 0 else 0
        
        st.divider()
        if lucro >= 0: st.success(f"### Lucro Estimado: {format_brl(lucro)} | ROI: {roi:.2f}%")
        else: st.error(f"### Prejuízo Estimado: {format_brl(lucro)} | ROI: {roi:.2f}%")

    # --- RELATÓRIO ---
    def gerar_excel():
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            pd.DataFrame([{"Tipo": tipo_imovel, "Lance": v_lance, "Lucro": lucro}]).to_excel(writer, index=False)
        return output.getvalue()

    st.sidebar.download_button("📥 BAIXAR RELATÓRIO", gerar_excel(), f"simulacao_{tipo_imovel}.xlsx")

if __name__ == "__main__":
    main()
