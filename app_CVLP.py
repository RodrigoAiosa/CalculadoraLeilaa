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
            df[col] = df[col].astype(str).str.replace(erro, correto)
    return df

# --- MOTOR DE SCRAPING (MANTIDO CONFORME SOLICITADO) ---
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
    st.title("⚖️ Calculadora de Viabilidade Leilão")

    # --- SIDEBAR ---
    st.sidebar.header("⚙️ Configurações")
    tipo_imovel = st.sidebar.selectbox("Tipo de Imóvel:", ["Casa", "Apartamento", "Terreno", "Gleba"])
    perfil = st.sidebar.selectbox("Perfil de Custos:", ["Manual", "Popular", "Médio Padrão", "Alto Padrão"])

    defaults = {
        "Manual": {"avaliacao": 0.0, "lance": 0.0, "reforma": 0.0, "venda": 0.0, "fixos": 0.0},
        "Popular": {"avaliacao": 250000.0, "lance": 150000.0, "reforma": 15000.0, "venda": 240000.0, "fixos": 600.0},
        "Médio Padrão": {"avaliacao": 700000.0, "lance": 420000.0, "reforma": 40000.0, "venda": 680000.0, "fixos": 1500.0},
        "Alto Padrão": {"avaliacao": 2000000.0, "lance": 1200000.0, "reforma": 120000.0, "venda": 1900000.0, "fixos": 4000.0}
    }
    d = defaults.get(perfil)

    # --- BLOCO 0: EXTRAÇÃO (BOTÃO MANTIDO) ---
    with st.expander("🏢 Obter Lista da Caixa Econômica", expanded=False):
        if st.button("🚀 Rodar Robô de Coleta"):
            with st.status("Extraindo dados...", expanded=True) as status:
                csv, qtd = robo_caixa()
                if csv:
                    status.update(label="Coleta Finalizada!", state="complete")
                    st.download_button("💾 Baixar CSV da Caixa", csv, "lista_caixa.csv", "text/csv")
                else:
                    status.update(label="Falha na Coleta", state="error")
                    st.error(qtd)

    # --- BLOCO 1: ARREMATAÇÃO ---
    st.subheader("📊 Simulação Financeira")
    with st.expander("💵 Bloco 1: Arrematação", expanded=True):
        col1, col2 = st.columns(2)
        v_avaliacao = col1.number_input("Avaliação de Mercado (R$)", value=float(d["avaliacao"]))
        v_lance = col2.number_input("Valor do Lance (R$)", value=float(d["lance"]))
        
        tipo_pgto = st.radio("Pagamento:", ["À Vista", "Financiado"], horizontal=True)
        
        if tipo_pgto == "Financiado":
            v_entrada = st.number_input("Entrada (R$)", value=v_lance * 0.2)
            v_finan = v_lance - v_entrada
            v_mensal = st.number_input("Parcela Mensal (R$)", value=0.0)
        else:
            v_entrada = v_lance
            v_finan = 0.0
            v_mensal = 0.0
            
        taxas_docs = st.number_input("ITBI / Escritura / Registro / Leiloeiro (R$)", value=v_lance * 0.08)
        total_b1 = v_entrada + taxas_docs

    # --- BLOCO 2: CUSTOS INTERMEDIÁRIOS ---
    with st.expander("🔗 Bloco 2: Custos Intermediários", expanded=True):
        col3, col4 = st.columns(2)
        reforma = col3.number_input("Custo de Reforma (R$)", value=float(d["reforma"]))
        meses = col4.number_input("Meses até Venda (Hold)", value=7)
        custo_fixo_mensal = st.number_input("Custos Fixos/mês (Cond+IPTU+Luz)", value=float(d["fixos"]))
        
        total_manutencao = (custo_fixo_mensal * meses) + (v_mensal * meses)
        total_b2 = reforma + total_manutencao

    # --- BLOCO 3: VENDA E RESULTADO ---
    with st.expander("🏷️ Bloco 3: Venda e Lucro", expanded=True):
        v_venda = st.number_input("Preço de Venda Final (R$)", value=float(d["venda"]))
        comis_corretor = st.number_input("Comissão Corretor (%)", value=5.0) / 100
        v_comis = v_venda * comis_corretor
        
        invest_total_bolso = total_b1 + total_b2
        # Lucro Bruto deduzindo o saldo devedor do financiamento
        lucro_bruto = (v_venda - v_comis) - v_finan - invest_total_bolso
        v_ir = max(0.0, lucro_bruto * 0.15)
        lucro_liquido = lucro_bruto - v_ir
        roi = (lucro_liquido / invest_total_bolso * 100) if invest_total_bolso > 0 else 0

        st.divider()
        res1, res2, res3 = st.columns(3)
        res1.metric("Total Investido (Do Bolso)", format_brl(invest_total_bolso))
        res2.metric("Lucro Líquido Real", format_brl(lucro_liquido), delta=f"{roi:.2f}% ROI")
        res3.write(f"**Imposto de Renda Est.:** {format_brl(v_ir)}")

    # --- EXPORTAÇÃO ---
    def gerar_excel():
        output = io.BytesIO()
        try:
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df = pd.DataFrame([{
                    "Data": datetime.now().strftime("%d/%m/%Y"),
                    "Tipo": tipo_imovel,
                    "Lance": v_lance,
                    "Investido": invest_total_bolso,
                    "Venda": v_venda,
                    "Lucro Líquido": lucro_liquido,
                    "ROI %": f"{roi:.2f}%"
                }])
                df.to_excel(writer, index=False, sheet_name='Simulacao')
            return output.getvalue()
        except:
            return None

    st.sidebar.markdown("---")
    excel_data = gerar_excel()
    if excel_data:
        st.sidebar.download_button("📥 Baixar Relatório Excel", excel_data, f"leilao_{tipo_imovel}.xlsx")

if __name__ == "__main__":
    main()
