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

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Calculadora de Viabilidade Leilão", layout="wide", page_icon="⚖️")

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
        'Desconto': 'Desconto',
        'DescriÃ§Ã£o': 'Descrição',
        'Modalidade de venda': 'Modalidade de Venda',
        'avaliaÃ§Ã£o': 'Avaliação',
        'Ã§Ã£o': 'ção',
        'Ã³': 'ó'
    }
    df.columns = [c.strip() for c in df.columns]
    for erro, correto in mapa_sujeira.items():
        df.columns = [c.replace(erro, correto) if erro in c else c for c in df.columns]
    
    cols_texto = df.select_dtypes(include=['object']).columns
    for col in cols_texto:
        for erro, correto in mapa_sujeira.items():
            df[col] = df[col].astype(str).str.replace(erro, correto)
    return df

def aguardar_download_concluido(diretorio, timeout=150):
    segundos = 0
    while segundos < timeout:
        arquivos = os.listdir(diretorio)
        processando = any(f.endswith(".crdownload") or f.endswith(".tmp") for f in arquivos)
        arquivos_csv = [f for f in arquivos if f.endswith(".csv") and "tratada" not in f]
        if not processando and len(arquivos_csv) > 0:
            return True
        time.sleep(2)
        segundos += 2
    return False

# --- MOTOR DO ROBÔ (MANTIDO CONFORME SOLICITADO) ---
def robo_caixa():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    download_dir = os.path.join(base_dir, "temp_caixa")
    if not os.path.exists(download_dir): os.makedirs(download_dir)
    for f in glob.glob(os.path.join(download_dir, "*.csv")):
        try: os.remove(f)
        except: pass

    # Tenta localizar binários no Streamlit Cloud
    chrome_path = shutil.which("chromium") or shutil.which("google-chrome")
    options = webdriver.ChromeOptions()
    if chrome_path:
        options.binary_location = chrome_path
    
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    prefs = {"download.default_directory": download_dir, "download.prompt_for_download": False}
    options.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(options=options)
    try:
        driver.get("https://venda-imoveis.caixa.gov.br/sistema/download-lista.asp")
        wait = WebDriverWait(driver, 20)
        dropdown = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="cmb_estado"]')))
        Select(dropdown).select_by_value("geral")
        wait.until(EC.element_to_be_clickable((By.ID, "btn_next1"))).click()

        if aguardar_download_concluido(download_dir):
            time.sleep(2)
            lista_arquivos = glob.glob(os.path.join(download_dir, "*.csv"))
            arquivo_recente = max(lista_arquivos, key=os.path.getctime)
            
            df = pd.read_csv(arquivo_recente, sep=';', encoding='ISO-8859-1', skiprows=2)
            df = tratar_texto_caixa(df)
            df.dropna(how='all', inplace=True)
            df['data_hora_inf'] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            
            csv_buffer = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
            return csv_buffer, len(df)
    except Exception as e:
        return None, f"Erro no processo: {str(e)}"
    finally:
        driver.quit()
    return None, "Erro desconhecido."

# --- INTERFACE PRINCIPAL ---
def main():
    st.title("⚖️ Calculadora de Viabilidade Leilão - Profissional")

    # --- SIDEBAR: CONFIGURAÇÕES ---
    st.sidebar.header("🚀 Perfil de Investimento")
    tipo_imovel = st.sidebar.selectbox("Selecione o tipo de imóvel:", ["Apartamento", "Casa", "Terreno", "Gleba"])
    perfil = st.sidebar.selectbox("Escolha um perfil de custos:", ["Manual", "Apartamento Popular", "Médio Padrão", "Alto Padrão"])

    defaults = {
        "Manual": {"avaliacao": 0.0, "lance": 0.0, "desocupa": 0.0, "reforma": 0.0, "condo": 0.0, "iptu": 0.0, "venda": 0.0, "agua": 0.0, "luz": 0.0, "gas": 0.0},
        "Apartamento Popular": {"avaliacao": 250000.0, "lance": 160000.0, "desocupa": 5000.0, "reforma": 20000.0, "condo": 350.0, "iptu": 60.0, "venda": 245000.0, "agua": 60.0, "luz": 120.0, "gas": 45.0},
        "Médio Padrão": {"avaliacao": 750000.0, "lance": 450000.0, "desocupa": 5000.0, "reforma": 35000.0, "condo": 800.0, "iptu": 200.0, "venda": 700000.0, "agua": 90.0, "luz": 250.0, "gas": 85.0},
        "Alto Padrão": {"avaliacao": 2500000.0, "lance": 1300000.0, "desocupa": 0.0, "reforma": 120000.0, "condo": 2200.0, "iptu": 900.0, "venda": 2200000.0, "agua": 180.0, "luz": 650.0, "gas": 150.0}
    }
    d = defaults[perfil]

    # --- BLOCO 0: DADOS CAIXA ---
    with st.expander("🏢 Extrair Lista da Caixa", expanded=False):
        if st.button("🚀 Iniciar Coleta e Limpeza"):
            with st.status("O robô está acessando o portal da Caixa...", expanded=True) as status:
                csv_data, res = robo_caixa()
                if csv_data:
                    status.update(label="Lista Tratada com Sucesso!", state="complete")
                    st.download_button("💾 Baixar Dados Tratados", csv_data, f"caixa_lista_{datetime.now().strftime('%y%m%d')}.csv", "text/csv")
                else: st.error(res)

    # --- BLOCO 1: ARREMATAÇÃO ---
    with st.expander("💵 Bloco 1: Arrematação", expanded=True):
        col_inp, col_mem = st.columns([3, 2])
        with col_inp:
            v_avaliacao = st.number_input("Valor de Avaliação (R$)", value=float(d["avaliacao"]))
            tipo_compra = st.radio("Pagamento:", ["À Vista", "Financiado"], horizontal=True)
            v_lance = st.number_input("Valor do Lance (R$)", value=float(d["lance"]))
            
            v_entrada, v_financiado, v_prestacao = 0.0, 0.0, 0.0
            if tipo_compra == "Financiado":
                v_entrada = st.number_input("Entrada (R$)", value=float(v_lance * 0.20))
                v_financiado = v_lance - v_entrada
                v_prestacao = st.number_input("Valor da Prestação Mensal (R$)", value=0.0)
            else:
                v_entrada = v_lance

            taxas_docs = st.number_input("Leiloeiro/ITBI/Registro (R$)", value=float(v_lance * 0.08))
            desocupa = st.number_input("Custo Desocupação (R$)", value=float(d["desocupa"]))
            total_b1 = v_entrada + taxas_docs + desocupa
        with col_mem: st.metric("Investimento Inicial", format_brl(total_b1))

    # --- BLOCO 2: CUSTOS ---
    with st.expander("🔗 Bloco 2: Custos Intermediários", expanded=True):
        col_inp2, col_mem2 = st.columns([3, 2])
        with col_inp2:
            reforma = st.number_input("Verba Reforma (R$)", value=float(d["reforma"]))
            meses = st.number_input("Meses até a Revenda", value=7)
            contas_mes = st.number_input("Custo Fixo Mensal (Condo+IPTU+Luz...)", value=float(d["agua"]+d["luz"]+d["condo"]+d["iptu"]+d["gas"]))
            total_intermediario = reforma + (contas_mes * meses) + (v_prestacao * meses)
        with col_mem2: st.metric("Total de Custos", format_brl(total_intermediario))

    # --- BLOCO 3: VENDA ---
    with st.expander("🏷️ Bloco 3: Venda e Lucro", expanded=True):
        col_v1, col_v2 = st.columns([3, 2])
        with col_v1:
            v_venda = st.number_input("Preço de Venda Final (R$)", value=float(d["venda"]))
            p_corretor = st.number_input("Comissão Corretor (%)", value=5.0)
            v_comis = v_venda * (p_corretor / 100)
            
            invest_total_bolso = total_b1 + total_intermediario
            # Lucro bruto retira o saldo devedor do financiamento se houver
            lucro_bruto = (v_venda - v_comis) - v_financiado - invest_total_bolso
            v_imp = max(0.0, lucro_bruto * 0.15)
            lucro_liq = lucro_bruto - v_imp
            roi = (lucro_liq / invest_total_bolso * 100) if invest_total_bolso > 0 else 0

        with col_v2:
            st.metric("Lucro Líquido", format_brl(lucro_liq))
            st.metric("ROI sobre o Capital", f"{roi:.2f}%")
            if lucro_liq < 0: st.error("Atenção: Operação com Prejuízo!")

    # --- RELATÓRIO EXCEL ---
    def exportar_xlsx():
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            pd.DataFrame([{"Data": datetime.now().strftime("%d/%m/%Y"), "Tipo": tipo_imovel, "Lucro": lucro_liq, "ROI %": roi}]).to_excel(writer, index=False, sheet_name='Resumo')
            pd.DataFrame([
                {"Categoria": "Investimento Arrematação", "Valor": total_b1},
                {"Categoria": "Custos Manutenção/Reforma", "Valor": total_intermediario},
                {"Categoria": "Comissão Venda", "Valor": v_comis},
                {"Categoria": "Imposto sobre Ganho", "Valor": v_imp}
            ]).to_excel(writer, index=False, sheet_name='Detalhamento')
        return output.getvalue()

    st.sidebar.markdown("---")
    st.sidebar.download_button("📥 BAIXAR RELATÓRIO EXCEL", exportar_xlsx(), f"leilao_{tipo_imovel}.xlsx")

if __name__ == "__main__":
    main()
