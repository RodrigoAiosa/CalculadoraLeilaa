import streamlit as st
import pd as pd
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

# Configuração da página
st.set_page_config(page_title="Calculadora de Viabilidade Leilão", layout="wide")

def format_brl(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def tratar_texto_caixa(df):
    mapa_sujeira = {
        'NÂ° do imÃ³vel': 'N° do Imóvel',
        'NÂ° do imÃ³ve': 'N° do Imóvel',
        'EndereÃ§o': 'Endereço',
        'PreÃ§o': 'Preço',
        'Valor de avaliaÃ§Ã£o': 'Valor de Avaliação',
        'DescriÃ§Ã£o': 'Descrição',
        'Ã§Ã£o': 'ção', 'Ã³': 'ó', 'Ã¢': 'â'
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
        processando = any(f.endswith(".crdownload") or f.endswith(".tmp") for f in arquivos)
        if not processando and any(f.endswith(".csv") for f in arquivos):
            return True
        time.sleep(2)
        segundos += 2
    return False

def robo_caixa():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    download_dir = os.path.join(base_dir, "temp_caixa")
    if not os.path.exists(download_dir): os.makedirs(download_dir)
    
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new") # Headless novo para evitar bugs no Linux
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.binary_location = "/usr/bin/chromium" # OBRIGATÓRIO NO STREAMLIT CLOUD
    
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)
    
    try:
        # Tenta usar o binário do sistema instalado via packages.txt
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
        
        driver.get("https://venda-imoveis.caixa.gov.br/sistema/download-lista.asp")
        wait = WebDriverWait(driver, 30)
        dropdown = wait.until(EC.presence_of_element_located((By.ID, "cmb_estado")))
        Select(dropdown).select_by_value("geral")
        wait.until(EC.element_to_be_clickable((By.ID, "btn_next1"))).click()

        if aguardar_download_concluido(download_dir):
            time.sleep(2)
            lista_arquivos = glob.glob(os.path.join(download_dir, "*.csv"))
            arquivo_recente = max(lista_arquivos, key=os.path.getctime)
            df = pd.read_csv(arquivo_recente, sep=';', encoding='ISO-8859-1', skiprows=2)
            df = tratar_texto_caixa(df)
            df['data_hora_inf'] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            csv_buffer = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
            driver.quit()
            return csv_buffer, len(df)
    except Exception as e:
        if 'driver' in locals(): driver.quit()
        return None, f"Erro Fatal: {str(e)}"
    return None, "Erro desconhecido."

def main():
    st.title("⚖️ Calculadora de Viabilidade Leilão")

    # --- SIDEBAR ---
    st.sidebar.header("🚀 Perfil")
    tipo_imovel = st.sidebar.selectbox("Tipo de Imóvel:", ["Apartamento", "Casa", "Terreno", "Gleba"])
    perfil = st.sidebar.selectbox("Perfil:", ["Manual", "Apartamento Popular", "Médio Padrão", "Alto Padrão"])

    defaults = {
        "Manual": {"avaliacao": 0.0, "lance": 0.0, "reforma": 0.0, "condo": 0.0, "iptu": 0.0, "venda": 0.0, "agua": 0.0, "luz": 0.0, "gas": 0.0},
        "Apartamento Popular": {"avaliacao": 250000.0, "lance": 160000.0, "reforma": 20000.0, "condo": 350.0, "iptu": 60.0, "venda": 245000.0, "agua": 60.0, "luz": 120.0, "gas": 45.0}
    }
    d = defaults.get(perfil, defaults["Manual"])

    # --- COLETA ---
    with st.expander("🏢 Extrair Lista Caixa", expanded=False):
        if st.button("🚀 Iniciar Robô"):
            with st.spinner("Acessando a Caixa..."):
                csv_data, res = robo_caixa()
                if csv_data:
                    st.success("Lista Coletada e Limpa!")
                    st.download_button("💾 Baixar CSV Corrigido", csv_data, "caixa_limpo.csv", "text/csv")
                else: st.error(res)

    # --- CALCULADORA ---
    with st.expander("💵 1. Arrematação", expanded=True):
        c1, c2 = st.columns(2)
        v_avaliacao = c1.number_input("Avaliação (R$)", value=float(d["avaliacao"]))
        v_lance = c2.number_input("Lance (R$)", value=float(d["lance"]))
        tipo_pgto = st.radio("Pagamento:", ["À Vista", "Financiado"], horizontal=True)
        
        v_entrada = v_lance if tipo_pgto == "À Vista" else c1.number_input("Entrada (R$)", value=v_lance*0.2)
        v_finan = v_lance - v_entrada if tipo_pgto == "Financiado" else 0.0
        v_prest = c2.number_input("Prestação (R$)", value=0.0) if tipo_pgto == "Financiado" else 0.0
        
        taxas = st.number_input("Taxas/ITBI/Docs (R$)", value=v_lance*0.08)
        total_b1 = v_entrada + taxas

    with st.expander("🔗 2. Custos e Contas", expanded=True):
        reforma = st.number_input("Reforma (R$)", value=float(d["reforma"]))
        meses = st.number_input("Meses até Venda", value=7)
        contas_base = (st.number_input("Soma Mensal (Água+Luz+Cond+IPTU)", value=float(d["agua"]+d["luz"]+d["condo"]+d["iptu"])))
        total_b2 = reforma + (contas_base * meses) + (v_prest * meses)

    with st.expander("🏷️ 3. Venda e Resultado", expanded=True):
        v_venda = st.number_input("Preço de Venda (R$)", value=float(d["venda"]))
        p_comis = st.number_input("Comissão Corretor (%)", value=5.0)
        v_comis = v_venda * (p_comis/100)
        
        invest_bolso = total_b1 + total_b2
        lucro_bruto = (v_venda - v_comis) - v_finan - invest_bolso
        lucro_liq = lucro_bruto - max(0.0, lucro_bruto * 0.15)
        roi = (lucro_liq / invest_bolso * 100) if invest_bolso > 0 else 0
        
        if lucro_liq >= 0:
            st.success(f"### Lucro Líquido: {format_brl(lucro_liq)} | ROI: {roi:.2f}%")
        else:
            st.error(f"### Prejuízo: {format_brl(lucro_liq)} | ROI: {roi:.2f}%")

    # --- EXPORTAÇÃO ---
    def gerar_excel():
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            pd.DataFrame([{"Tipo": tipo_imovel, "Lucro": lucro_liq, "ROI %": roi}]).to_excel(writer, index=False, sheet_name='Resumo')
        return output.getvalue()

    st.sidebar.markdown("---")
    st.sidebar.download_button("📥 BAIXAR RELATÓRIO", gerar_excel(), f"{tipo_imovel}.xlsx")

if __name__ == "__main__":
    main()
