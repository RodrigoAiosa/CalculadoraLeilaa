import streamlit as st
import pandas as pd  # CORRIGIDO: O nome correto é pandas
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

# --- FUNÇÕES DE AUXÍLIO ---
def format_brl(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def tratar_texto_caixa(df):
    """Limpa a sujeira de codificação das colunas da Caixa"""
    mapa_sujeira = {
        'NÂ° do imÃ³vel': 'N° do Imóvel',
        'NÂ° do imÃ³ve': 'N° do Imóvel',
        'EndereÃ§o': 'Endereço',
        'PreÃ§o': 'Preço',
        'Valor de avaliaÃ§Ã£o': 'Valor de Avaliação',
        'DescriÃ§Ã£o': 'Descrição',
        'Ã§Ã£o': 'ção', 'Ã³': 'ó', 'Ã¢': 'â', 'Ã©': 'é'
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
    
    # Limpa arquivos antigos
    for f in glob.glob(os.path.join(download_dir, "*.csv")):
        try: os.remove(f)
        except: pass

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    # IMPORTANTE: No Streamlit Cloud o binário do Chromium fica aqui:
    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
    
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)
    
    try:
        # Tenta usar o driver do sistema (instalado pelo packages.txt)
        if os.path.exists("/usr/bin/chromedriver"):
            service = Service("/usr/bin/chromedriver")
        else:
            service = Service(ChromeDriverManager().install())
            
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
        return None, f"Erro no Robô: {str(e)}"
    return None, "Falha ao baixar arquivo."

def main():
    st.title("⚖️ Calculadora de Viabilidade Leilão Profissional")

    # --- SIDEBAR ---
    st.sidebar.header("🚀 Configurações")
    tipo_imovel = st.sidebar.selectbox("Tipo de Imóvel:", ["Apartamento", "Casa", "Terreno", "Gleba"])
    perfil = st.sidebar.selectbox("Perfil de Custos:", ["Manual", "Apartamento Popular", "Médio Padrão", "Alto Padrão"])

    defaults = {
        "Manual": {"avaliacao": 0.0, "lance": 0.0, "reforma": 0.0, "condo": 0.0, "iptu": 0.0, "venda": 0.0, "agua": 0.0, "luz": 0.0, "gas": 0.0},
        "Apartamento Popular": {"avaliacao": 250000.0, "lance": 160000.0, "reforma": 20000.0, "condo": 350.0, "iptu": 60.0, "venda": 245000.0, "agua": 60.0, "luz": 120.0, "gas": 45.0},
        "Médio Padrão": {"avaliacao": 750000.0, "lance": 450000.0, "reforma": 35000.0, "condo": 800.0, "iptu": 200.0, "venda": 700000.0, "agua": 90.0, "luz": 250.0, "gas": 85.0}
    }
    d = defaults.get(perfil, defaults["Manual"])

    # --- BLOCO 0: DADOS CAIXA ---
    with st.expander("🏢 Extrair Lista da Caixa", expanded=False):
        if st.button("🚀 Iniciar Coleta Automática"):
            with st.spinner("Conectando ao site da Caixa..."):
                csv_data, res = robo_caixa()
                if csv_data:
                    st.success(f"Sucesso! {res} imóveis encontrados.")
                    st.download_button("💾 Baixar CSV Limpo", csv_data, "caixa_limpo.csv", "text/csv")
                else: st.error(res)

    # --- BLOCO 1: ARREMATAÇÃO ---
    with st.expander("💵 1. Arrematação", expanded=True):
        col_inp, col_mem = st.columns([3, 2])
        with col_inp:
            v_avaliacao = st.number_input("Valor de Avaliação (R$)", value=float(d["avaliacao"]))
            tipo_pgto = st.radio("Forma de Pagamento:", ["À Vista", "Financiado"], horizontal=True)
            v_lance = st.number_input("Valor do Lance Ofertado (R$)", value=float(d["lance"]))
            
            v_entrada = v_lance if tipo_pgto == "À Vista" else st.number_input("Valor de Entrada (R$)", value=v_lance*0.2)
            v_finan = v_lance - v_entrada if tipo_pgto == "Financiado" else 0.0
            v_prest = st.number_input("Prestação Mensal (R$)", value=0.0) if tipo_pgto == "Financiado" else 0.0
            
            taxas = st.number_input("Taxas (Leiloeiro 5% + ITBI + Registro)", value=v_lance*0.08)
            total_b1 = v_entrada + taxas
        with col_mem: st.metric("Subtotal Arrematação", format_brl(total_b1))

    # --- BLOCO 2: CUSTOS ---
    with st.expander("🔗 2. Custos Intermediários", expanded=True):
        col_inp2, col_mem2 = st.columns([3, 2])
        with col_inp2:
            reforma = st.number_input("Verba para Reforma (R$)", value=float(d["reforma"]))
            meses = st.number_input("Meses Estimados até a Venda", value=7)
            contas_mensais = st.number_input("Contas (Água+Luz+Condo+IPTU)", value=float(d["agua"]+d["luz"]+d["condo"]+d["iptu"]))
            total_contas = contas_mensais * meses
            custo_financeiro = v_prest * meses
            total_b2 = reforma + total_contas + custo_financeiro
        with col_mem2: st.metric("Subtotal Intermediários", format_brl(total_b2))

    # --- BLOCO 3: VENDA ---
    with st.expander("🏷️ 3. Venda e Resultado Final", expanded=True):
        col_v1, col_v2 = st.columns([3, 2])
        with col_v1:
            v_venda = st.number_input("Preço de Venda Final (R$)", value=float(d["venda"]))
            p_comis = st.number_input("Comissão do Corretor (%)", value=5.0)
            v_comis = v_venda * (p_comis/100)
            
            p_imp = st.number_input("Imposto de Renda (%)", value=15.0)
            
            invest_total = total_b1 + total_b2
            lucro_bruto = (v_venda - v_comis) - v_finan - invest_total
            v_imp = max(0.0, lucro_bruto * (p_imp/100))
            lucro_liq = lucro_bruto - v_imp
            roi = (lucro_liq / invest_total * 100) if invest_total > 0 else 0

        with col_v2:
            msg = f"### Lucro Líquido: {format_brl(lucro_liq)} | ROI: {roi:.2f}%"
            if lucro_liq >= 0: st.success(msg)
            else: st.error(msg)

    # --- EXPORTAÇÃO ---
    def gerar_excel():
        output = io.BytesIO()
        df_resumo = pd.DataFrame([{"Data": datetime.now().strftime("%d/%m/%Y"), "Tipo": tipo_imovel, "Lucro": lucro_liq, "ROI %": roi}])
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_resumo.to_excel(writer, index=False, sheet_name='Resumo')
        return output.getvalue()

    st.sidebar.markdown("---")
    st.sidebar.download_button("📥 BAIXAR RELATÓRIO EXCEL", gerar_excel(), f"simulacao_{tipo_imovel}.xlsx")

if __name__ == "__main__":
    main()
