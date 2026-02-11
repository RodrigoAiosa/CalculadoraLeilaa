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
from datetime import datetime

# Configuração da página
st.set_page_config(page_title="Calculadora de Viabilidade Leilão", layout="wide")

# --- FUNÇÕES DE AUXÍLIO ---
def format_brl(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def tratar_texto_caixa(df):
    """Limpa a sujeira de codificação das colunas da Caixa"""
    # Mapa de tradução de lixo para texto humano
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
    
    # Limpa nomes das colunas
    df.columns = [c.strip() for c in df.columns]
    for erro, correto in mapa_sujeira.items():
        df.columns = [c.replace(erro, correto) if erro in c else c for c in df.columns]
    
    # Limpa o conteúdo das células (apenas colunas de texto)
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

def robo_caixa():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    download_dir = os.path.join(base_dir, "temp_caixa")
    if not os.path.exists(download_dir): os.makedirs(download_dir)
    for f in glob.glob(os.path.join(download_dir, "*.csv")):
        try: os.remove(f)
        except: pass

    options = webdriver.ChromeOptions()
    prefs = {"download.default_directory": download_dir, "download.prompt_for_download": False}
    options.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(options=options)
    try:
        driver.get("https://venda-imoveis.caixa.gov.br/sistema/download-lista.asp")
        wait = WebDriverWait(driver, 15)
        dropdown = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="cmb_estado"]')))
        Select(dropdown).select_by_value("geral")
        wait.until(EC.element_to_be_clickable((By.ID, "btn_next1"))).click()

        if aguardar_download_concluido(download_dir):
            time.sleep(2)
            lista_arquivos = glob.glob(os.path.join(download_dir, "*.csv"))
            arquivo_recente = max(lista_arquivos, key=os.path.getctime)
            
            # Lê com encoding problemático e trata
            df = pd.read_csv(arquivo_recente, sep=';', encoding='ISO-8859-1', skiprows=2)
            df = tratar_texto_caixa(df)
            df.dropna(how='all', inplace=True)
            df['data_hora_inf'] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            
            # Salva limpo em UTF-8 com BOM (Excel entende na hora)
            csv_buffer = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
            if os.path.exists(arquivo_recente): os.remove(arquivo_recente)
            return csv_buffer, len(df)
    except Exception as e: return None, str(e)
    finally: driver.quit()
    return None, "Erro no processo."

def main():
    st.title("⚖️ Calculadora de Viabilidade Leilão - Profissional")

    # --- SIDEBAR ---
    st.sidebar.header("🚀 Perfil de Investimento")
    tipo_imovel = st.sidebar.selectbox("Selecione o tipo de imóvel:", ["Apartamento", "Casa", "Terreno", "Gleba"])
    perfil = st.sidebar.selectbox("Escolha um perfil:", ["Manual", "Apartamento Popular", "Médio Padrão", "Alto Padrão"])

    defaults = {
        "Manual": {"avaliacao": 0.0, "lance": 0.0, "cartorio": 0.0, "desocupa": 0.0, "reforma": 0.0, "condo": 0.0, "iptu": 0.0, "venda": 0.0, "agua": 0.0, "luz": 0.0, "gas": 0.0},
        "Apartamento Popular": {"avaliacao": 250000.0, "lance": 160000.0, "cartorio": 1200.0, "desocupa": 8000.0, "reforma": 20000.0, "condo": 350.0, "iptu": 60.0, "venda": 245000.0, "agua": 60.0, "luz": 120.0, "gas": 45.0},
        "Médio Padrão": {"avaliacao": 750000.0, "lance": 450000.0, "cartorio": 3000.0, "desocupa": 5000.0, "reforma": 35000.0, "condo": 800.0, "iptu": 200.0, "venda": 700000.0, "agua": 90.0, "luz": 250.0, "gas": 85.0},
        "Alto Padrão": {"avaliacao": 2500000.0, "lance": 1300000.0, "cartorio": 9000.0, "desocupa": 0.0, "reforma": 120000.0, "condo": 2200.0, "iptu": 900.0, "venda": 2200000.0, "agua": 180.0, "luz": 650.0, "gas": 150.0}
    }
    d = defaults[perfil]

    # --- BLOCO 0: DADOS CAIXA ---
    with st.expander("🏢 Extrair Lista da Caixa", expanded=False):
        if st.button("🚀 Iniciar Coleta e Limpeza"):
            with st.status("Tratando nomes de colunas e endereços...", expanded=True) as status:
                csv_data, res = robo_caixa()
                if csv_data:
                    status.update(label="Lista Tratada com Sucesso!", state="complete")
                    st.download_button("💾 Baixar Dados", csv_data, f"imovel_caixa_{datetime.now().strftime('%y%m%d_%H%M%S')}.csv", "text/csv")
                else: st.error(res)

    # --- BLOCO 1: ARREMATAÇÃO ---
    with st.expander("💵 Bloco 1: Arrematação", expanded=True):
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
    with st.expander("🔗 Bloco 2: Custos Intermediários", expanded=True):
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
    with st.expander("🏷️ Bloco 3: Venda e Lucro", expanded=True):
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

    # --- RELATÓRIO EXCEL ---
    def exportar():
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            pd.DataFrame([{"Data": datetime.now(), "Tipo": tipo_imovel, "Lucro": lucro_liq, "ROI %": roi}]).to_excel(writer, index=False, sheet_name='Resumo')
            pd.DataFrame([
                {"Categoria": "Arrematação (Entrada + Docs)", "Valor": total_b1},
                {"Categoria": "Custos (Reforma + Manutenção)", "Valor": total_b2},
                {"Categoria": "Comissão Corretor", "Valor": v_comis},
                {"Categoria": "Imposto", "Valor": v_imp}
            ]).to_excel(writer, index=False, sheet_name='Detalhes')
        return output.getvalue()

    st.sidebar.markdown("---")
    st.sidebar.download_button("📥 BAIXAR RELATÓRIO COMPLETO", exportar(), f"simulacao_{tipo_imovel}.xlsx")

if __name__ == "__main__":
    main()