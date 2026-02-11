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

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Calculadora Viabilidade Leilão Profissional", layout="wide")

# --- FUNÇÕES DE UTILIDADE ---
def format_brl(valor):
    """Formata valores numéricos para o padrão monetário brasileiro."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def tratar_texto_caixa(df):
    """Corrige os erros de codificação (ISO-8859-1 para UTF-8) comuns nos CSVs da Caixa."""
    mapa_sujeira = {
        'NÂ° do imÃ³vel': 'N° do Imóvel',
        'NÂ° do imÃ³ve': 'N° do Imóvel',
        'EndereÃ§o': 'Endereço',
        'PreÃ§o': 'Preço',
        'Valor de avaliaÃ§Ã£o': 'Valor de Avaliação',
        'DescriÃ§Ã£o': 'Descrição',
        'Ã§Ã£o': 'ção', 'Ã³': 'ó', 'Ã¢': 'â', 'Ã©': 'é', 'Ãº': 'ú', 'Ã': 'á'
    }
    # Limpa nomes das colunas
    df.columns = [c.strip() for c in df.columns]
    for erro, correto in mapa_sujeira.items():
        df.columns = [c.replace(erro, correto) if erro in c else c for c in df.columns]
    
    # Limpa o conteúdo das células de texto
    cols_obj = df.select_dtypes(include=['object']).columns
    for col in cols_obj:
        for erro, correto in mapa_sujeira.items():
            df[col] = df[col].astype(str).str.replace(erro, correto)
    return df

# --- MOTOR DE SCRAPING (ROBÓ CAIXA) ---
def robo_caixa():
    download_dir = os.path.join(os.getcwd(), "temp_caixa")
    if not os.path.exists(download_dir): 
        os.makedirs(download_dir)
    
    # Limpa arquivos antigos na pasta temporária
    for f in glob.glob(os.path.join(download_dir, "*.csv")):
        try: os.remove(f)
        except: pass

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # Define o local do binário no Streamlit Cloud (Linux)
    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"

    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)
    
    # Utiliza o driver instalado via packages.txt
    service = Service("/usr/bin/chromedriver")
    
    driver = None
    try:
        driver = webdriver.Chrome(service=service, options=options)
        driver.get("https://venda-imoveis.caixa.gov.br/sistema/download-lista.asp")
        
        wait = WebDriverWait(driver, 30)
        
        # Seleciona a opção "Geral" no dropdown de estados
        dropdown = wait.until(EC.presence_of_element_located((By.ID, "cmb_estado")))
        Select(dropdown).select_by_value("geral")
        
        # Clique no botão via JavaScript para evitar erros de renderização headless
        btn = wait.until(EC.element_to_be_clickable((By.ID, "btn_next1")))
        driver.execute_script("arguments[0].click();", btn)

        # Monitoramento do download
        timeout = 60
        inicio = time.time()
        while time.time() - inicio < timeout:
            arquivos = glob.glob(os.path.join(download_dir, "*.csv"))
            if arquivos:
                time.sleep(2) # Pausa técnica para fechamento do arquivo pelo OS
                df = pd.read_csv(arquivos[0], sep=';', encoding='ISO-8859-1', skiprows=2)
                df = tratar_texto_caixa(df)
                df['data_hora_inf'] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                
                csv_buffer = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
                driver.quit()
                return csv_buffer, len(df)
            time.sleep(2)
            
    except Exception as e:
        if driver: driver.quit()
        return None, f"Erro no Servidor: {str(e)}"
    
    return None, "O arquivo da Caixa não foi gerado a tempo."

# --- INTERFACE PRINCIPAL ---
def main():
    st.title("⚖️ Calculadora de Viabilidade de Leilão Profissional")

    # --- SIDEBAR: CONFIGURAÇÕES ---
    st.sidebar.header("🚀 Perfil de Investimento")
    tipo_imovel = st.sidebar.selectbox("Tipo de Imóvel:", ["Apartamento", "Casa", "Terreno", "Gleba"])
    perfil = st.sidebar.selectbox("Perfil de Custos:", ["Manual", "Popular", "Médio Padrão", "Alto Padrão"])

    # Valores padrão por perfil
    defaults = {
        "Manual": {"avaliacao": 0.0, "lance": 0.0, "reforma": 0.0, "venda": 0.0, "contas": 0.0},
        "Popular": {"avaliacao": 220000.0, "lance": 130000.0, "reforma": 15000.0, "venda": 210000.0, "contas": 500.0},
        "Médio Padrão": {"avaliacao": 750000.0, "lance": 450000.0, "reforma": 45000.0, "venda": 720000.0, "contas": 1200.0},
        "Alto Padrão": {"avaliacao": 2500000.0, "lance": 1400000.0, "reforma": 150000.0, "venda": 2300000.0, "contas": 3500.0}
    }
    d = defaults.get(perfil)

    # --- BLOCO 0: DADOS DA CAIXA ---
    with st.expander("🏢 Coleta de Dados Automatizada (Caixa)", expanded=False):
        st.write("Extrai a lista geral de imóveis da Caixa Econômica Federal e corrige erros de texto.")
        if st.button("🚀 Iniciar Robô de Coleta"):
            with st.spinner("Navegando no portal da Caixa..."):
                csv_data, resultado = robo_caixa()
                if csv_data:
                    st.success(f"Sucesso! {resultado} imóveis processados e limpos.")
                    st.download_button("💾 Baixar Lista Caixa (CSV)", csv_data, f"caixa_lista_{datetime.now().strftime('%d_%m')}.csv", "text/csv")
                else:
                    st.error(resultado)

    # --- BLOCO 1: ARREMATAÇÃO E LANCE ---
    with st.expander("💵 1. Arrematação e Entrada", expanded=True):
        col1, col2 = st.columns(2)
        v_avaliacao = col1.number_input("Valor de Avaliação (R$)", value=float(d["avaliacao"]))
        v_lance = col2.number_input("Valor do Lance (R$)", value=float(d["lance"]))
        
        tipo_pgto = st.radio("Forma de Pagamento:", ["À Vista", "Financiado"], horizontal=True)
        
        if tipo_pgto == "Financiado":
            v_entrada = st.number_input("Valor de Entrada (R$)", value=v_lance * 0.2)
            v_financiado = v_lance - v_entrada
            v_prestacao = st.number_input("Valor da Prestação Mensal (R$)", value=0.0)
        else:
            v_entrada = v_lance
            v_financiado = 0.0
            v_prestacao = 0.0

        taxas_docs = st.number_input("Custos de Escritura/ITBI/Leiloeiro (R$)", value=v_lance * 0.08)
        total_bloco1 = v_entrada + taxas_docs

    # --- BLOCO 2: CUSTOS DE MANUTENÇÃO ---
    with st.expander("🔗 2. Reformas e Custos Fixos", expanded=True):
        col3, col4 = st.columns(2)
        v_reforma = col3.number_input("Verba para Reforma (R$)", value=float(d["reforma"]))
        v_meses = col4.number_input("Meses até a Venda", value=7)
        v_custos_fixos = st.number_input("Soma Mensal (Condomínio + IPTU + Água/Luz)", value=float(d["contas"]))
        
        total_manutencao = (v_custos_fixos * v_meses) + (v_prestacao * v_meses)
        total_bloco2 = v_reforma + total_manutencao

    # --- BLOCO 3: VENDA E ROI ---
    with st.expander("🏷️ 3. Venda e Resultado Final", expanded=True):
        col5, col6 = st.columns(2)
        v_venda = col5.number_input("Preço Estimado de Venda (R$)", value=float(d["venda"]))
        p_comissao = col6.number_input("Comissão do Corretor (%)", value=5.0)
        v_comissao = v_venda * (p_comissao / 100)
        
        investimento_bolso = total_bloco1 + total_bloco2
        # Lucro Bruto = (Venda - Comissão) - (Dívida do Financiamento) - (Tudo que saiu do bolso)
        lucro_bruto = (v_venda - v_comissao) - v_financiado - investimento_bolso
        
        # Imposto de Renda (estimativa de 15% sobre o lucro)
        v_ir = max(0.0, lucro_bruto * 0.15)
        lucro_liquido = lucro_bruto - v_ir
        roi = (lucro_liquido / investimento_bolso * 100) if investimento_bolso > 0 else 0

        st.divider()
        if lucro_liquido >= 0:
            st.success(f"### Lucro Líquido: {format_brl(lucro_liquido)} | ROI: {roi:.2f}%")
        else:
            st.error(f"### Prejuízo Estimado: {format_brl(lucro_liquido)} | ROI: {roi:.2f}%")

    # --- EXPORTAÇÃO PARA EXCEL ---
    def gerar_excel():
        output = io.BytesIO()
        try:
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # Aba Resumo
                df_resumo = pd.DataFrame([{
                    "Tipo": tipo_imovel,
                    "Perfil": perfil,
                    "Investimento": investimento_bolso,
                    "Lucro Líquido": lucro_liquido,
                    "ROI %": f"{roi:.2f}%"
                }])
                df_resumo.to_excel(writer, index=False, sheet_name='Resumo')
                
                # Aba Detalhes
                df_detalhes = pd.DataFrame([
                    {"Item": "Valor de Arrematação", "Valor": v_lance},
                    {"Item": "Total que saiu do Bolso", "Valor": investimento_bolso},
                    {"Item": "Custo Reforma", "Valor": v_reforma},
                    {"Item": "Comissão Corretor", "Valor": v_comissao},
                    {"Item": "Imposto de Renda (Est.)", "Valor": v_ir}
                ])
                df_detalhes.to_excel(writer, index=False, sheet_name='Detalhamento de Custos')
            return output.getvalue()
        except Exception as e:
            return str(e).encode()

    st.sidebar.markdown("---")
    st.sidebar.download_button(
        label="📥 BAIXAR RELATÓRIO COMPLETO",
        data=gerar_excel(),
        file_name=f"viabilidade_{tipo_imovel.lower()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == "__main__":
    main()
