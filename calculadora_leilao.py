import streamlit as st
import pandas as pd
import io
from datetime import datetime

# Configuração da página SCRIPT VALIDADO Ultima Atualização: 2026-02-01 23:18
st.set_page_config(
    page_title="Calculadora de Viabilidade Leilão", layout="wide")


def format_brl(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    st.title("⚖️ Calculadora de Viabilidade de Leilão Profissional")

    # --- SIDEBAR: PERFIL ---
    st.sidebar.header("🚀 Perfil de Investimento")
    tipo_imovel = st.sidebar.selectbox("Selecione o tipo de imóvel:", [
                                       "Apartamento", "Casa", "Terreno", "Gleba"])
    perfil = st.sidebar.selectbox("Escolha um perfil:", [
                                  "Manual", "Apartamento Popular", "Médio Padrão", "Alto Padrão"])

    defaults = {
        "Manual": {"avaliacao": 0.0, "lance": 0.0, "cartorio": 0.0, "desocupa": 0.0, "reforma": 0.0, "condo": 0.0, "iptu": 0.0, "venda": 0.0, "agua": 0.0, "luz": 0.0, "gas": 0.0},
        "Apartamento Popular": {"avaliacao": 250000.0, "lance": 160000.0, "cartorio": 1200.0, "desocupa": 8000.0, "reforma": 20000.0, "condo": 350.0, "iptu": 60.0, "venda": 245000.0, "agua": 60.0, "luz": 120.0, "gas": 45.0},
        "Médio Padrão": {"avaliacao": 750000.0, "lance": 450000.0, "cartorio": 3000.0, "desocupa": 5000.0, "reforma": 35000.0, "condo": 800.0, "iptu": 200.0, "venda": 700000.0, "agua": 90.0, "luz": 250.0, "gas": 85.0},
        "Alto Padrão": {"avaliacao": 2500000.0, "lance": 1300000.0, "cartorio": 9000.0, "desocupa": 0.0, "reforma": 120000.0, "condo": 2200.0, "iptu": 900.0, "venda": 2200000.0, "agua": 180.0, "luz": 650.0, "gas": 150.0}
    }
    d = defaults[perfil]

    # --- BLOCO 1: ARREMATAÇÃO ---
    with st.expander("💵 Arrematação", expanded=True):
        col_inp, col_mem = st.columns([3, 2])
        with col_inp:
            v_avaliacao = st.number_input(
                "Valor de Avaliação (R$)", value=float(d["avaliacao"]), step=1000.0)
            tipo_compra = st.radio("Forma de Pagamento:", [
                                   "À Vista", "Financiado"], horizontal=True)
            c1, c2 = st.columns(2)
            v_lance = c1.number_input(
                "Valor do Lance Total (R$)", value=float(d["lance"]), step=1000.0)

            p_entrada_calculada = 100.0
            v_prestacao, meses_financiamento, v_financiado, juros_mensal, juros_anual = 0.0, 0, 0.0, 0.0, 0.0

            if tipo_compra == "À Vista":
                desc_vista = c2.number_input("Desconto à Vista (%)", value=0.0)
                v_entrada = v_lance * (1 - desc_vista/100)
            else:
                desc_vista = 0.0
                v_entrada = c2.number_input(
                    "Valor da Entrada (R$)", value=float(v_lance * 0.20))
                p_entrada_calculada = (
                    v_entrada / v_lance * 100) if v_lance > 0 else 0
                v_financiado = v_lance - v_entrada
                juros_anual = c2.number_input(
                    "Taxa de Juros do Banco (% a.a.)", value=9.5)
                juros_mensal = (1 + juros_anual/100)**(1/12) - 1
                c1_f, c2_f = st.columns(2)
                v_prestacao = c1_f.number_input(
                    "Valor da Prestação (R$)", value=0.0, step=100.0)
                meses_financiamento = c2_f.number_input(
                    "Prazo do Financiamento (meses)", value=0, step=1)

            comis_leilao = c1.number_input(
                "Comissão do Leiloeiro (R$)", value=float(v_lance * 0.05))
            itbi = c2.number_input("ITBI (R$)", value=float(v_lance * 0.03))
            cartorio = c1.number_input(
                "Despesas de Cartório (R$)", value=float(d["cartorio"]))
            dividas = c2.number_input("Dívidas do Imóvel (R$)", value=0.0)
            desocupa = st.number_input(
                "Custos de Desocupação (R$)", value=float(d["desocupa"]))

        total_b1 = v_entrada + comis_leilao + itbi + cartorio + dividas + desocupa
        with col_mem:
            st.metric("TOTAL Arrematação", format_brl(total_b1))

    # --- BLOCO 2: CUSTOS INTERMEDIÁRIOS ---
    with st.expander("🔗 Custos Intermediários", expanded=True):
        col_inp2, col_mem2 = st.columns([3, 2])
        with col_inp2:
            c3, c4 = st.columns(2)
            reforma = c3.number_input(
                "Reforma (R$)", value=float(d["reforma"]))
            prazo_venda = c4.number_input("Prazo até a Venda (meses)", value=7)
            condo_m = c3.number_input(
                "Condomínio Mensal (R$)", value=float(d["condo"]))
            iptu_m = c4.number_input(
                "IPTU Mensal (R$)", value=float(d["iptu"]))
            agua_m = c3.number_input(
                "Água Mensal (R$)", value=float(d["agua"]))
            luz_m = c4.number_input("Luz Mensal (R$)", value=float(d["luz"]))
            gas_m = st.number_input("Gás Mensal (R$)", value=float(d["gas"]))

        custo_juros_periodo = (v_prestacao * prazo_venda) if v_prestacao > 0 else (
            v_financiado * juros_mensal * prazo_venda)
        total_manutencao_periodo = (
            condo_m + iptu_m + agua_m + luz_m + gas_m) * prazo_venda
        total_b2 = reforma + total_manutencao_periodo + custo_juros_periodo
        with col_mem2:
            st.metric("TOTAL Custos Intermediários", format_brl(total_b2))

    # --- BLOCO 3: VENDA ---
    with st.expander("🏷️ Venda", expanded=True):
        v_venda = st.number_input(
            "Valor de Venda (R$)", value=float(d["venda"]))
        comis_cor_perc = 0.05
        comis_cor = v_venda * comis_cor_perc
        imp_p = st.number_input("Imposto sobre Lucro (%)", value=15.0)
        v_venda_liq = v_venda - comis_cor
        invest_bolso = total_b1 + total_b2
        lucro_bruto = v_venda_liq - v_financiado - invest_bolso
        v_imp = max(0.0, lucro_bruto * (imp_p/100))
        total_b3 = comis_cor + v_imp
        lucro_liq = lucro_bruto - v_imp
        roi = (lucro_liq / invest_bolso * 100) if invest_bolso > 0 else 0
        st.success(
            f"### Lucro Líquido: {format_brl(lucro_liq)} | ROI: {roi:.2f}%")

    st.markdown("---")

    # --- ABA 1: SIMULAÇÃO ATUAL ---
    desc_salvar = round(((1 - (v_lance / v_avaliacao)) *
                        100), 2) if v_avaliacao > 0 else 0
    nova_linha = pd.DataFrame([{
        "Data/Hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "Tipo Imóvel": tipo_imovel,
        "Valor Avaliação": v_avaliacao,
        "Desconto s/ Avaliação %": desc_salvar,
        "Perfil": perfil,
        "Forma Pagto": tipo_compra,
        "Lance Total": v_lance,
        "Desc. Vista %": desc_vista,
        "Entrada": v_entrada,
        "Perc. Entrada %": round(p_entrada_calculada, 2),
        "Valor Financiado": v_financiado,
        "Prestação": v_prestacao,
        "Prazo Financiamento (Meses)": meses_financiamento,
        "Juros a.a. %": juros_anual,
        "Comissão Leiloeiro": comis_leilao,
        "ITBI": itbi,
        "Cartório": cartorio,
        "Dívidas Imóvel": dividas,
        "Custos Desocupação": desocupa,
        "TOTAL BLOCO 1": total_b1,
        "Reforma": reforma,
        "Prazo Venda (Meses)": prazo_venda,
        "Condomínio Mensal": condo_m,
        "IPTU Mensal": iptu_m,
        "Água Mensal": agua_m,
        "Luz Mensal": luz_m,
        "Gás Mensal": gas_m,
        "Custo Juros/Prestação Período": custo_juros_periodo,
        "TOTAL BLOCO 2": total_b2,
        "Venda Bruta": v_venda,
        "Comissão Corretor": comis_cor,
        "Imposto Lucro (IR)": v_imp,
        "TOTAL BLOCO 3": total_b3,
        "INVESTIMENTO TOTAL (BOLSO)": invest_bolso,
        "LUCRO LÍQUIDO FINAL": lucro_liq,
        "ROI %": roi
    }])

    # --- ABA 2: ANÁLISE DE RISCO (LANCE) ---
    cenarios_lance = []
    if v_lance > 0:
        for i in range(11):
            fator = 1 + (i * 0.05)
            l_cen = v_lance * fator
            e_cen = l_cen * (1 - desc_vista /
                             100) if tipo_compra == "À Vista" else v_entrada
            fin_cen = l_cen - e_cen
            b1_cen = e_cen + (l_cen * 0.05) + (l_cen * 0.03) + \
                cartorio + dividas + desocupa
            j_cen = (v_prestacao * prazo_venda) if v_prestacao > 0 else (fin_cen *
                                                                         juros_mensal * prazo_venda)
            total_inv = b1_cen + reforma + total_manutencao_periodo + j_cen
            luc_b = v_venda_liq - fin_cen - total_inv
            v_i = max(0.0, luc_b * (imp_p/100))
            luc_l = luc_b - v_i
            roi_c = (luc_l / total_inv * 100) if total_inv > 0 else 0
            cenarios_lance.append({"Cenário": f"Lance +{i*5}%", "Valor do Lance": l_cen, "Investimento de Bolso": total_inv,
                                  "Lucro Líquido": luc_l, "ROI %": round(roi_c, 2), "Status": "POSITIVO" if luc_l > 0 else "NEGATIVO"})
    df_risco = pd.DataFrame(cenarios_lance)

    # --- ABA 3: DETALHES FINANCEIROS ---
    df_detalhes = pd.DataFrame()
    if tipo_compra == "Financiado":
        detalhes_data = [
            {"Categoria": "FINANCIAMENTO",
                "Item": "Valor Financiado", "Valor": v_financiado},
            {"Categoria": "FINANCIAMENTO",
                "Item": "Taxa Juros Anual (%)", "Valor": juros_anual},
            {"Categoria": "FINANCIAMENTO", "Item": "Custo Juros no Período",
                "Valor": custo_juros_periodo},
            {"Categoria": "CUSTOS MENSAIS", "Item": "Condomínio Total",
                "Valor": condo_m * prazo_venda},
            {"Categoria": "CUSTOS MENSAIS", "Item": "IPTU Total",
                "Valor": iptu_m * prazo_venda},
            {"Categoria": "CUSTOS MENSAIS", "Item": "Água Total",
                "Valor": agua_m * prazo_venda},
            {"Categoria": "CUSTOS MENSAIS", "Item": "Luz Total",
                "Valor": luz_m * prazo_venda},
            {"Categoria": "CUSTOS MENSAIS", "Item": "Gás Total",
                "Valor": gas_m * prazo_venda},
            {"Categoria": "RESUMO", "Item": "Manutenção Total",
                "Valor": total_manutencao_periodo},
            {"Categoria": "RESUMO",
                "Item": "Prazo Venda (Meses)", "Valor": prazo_venda}
        ]
        df_detalhes = pd.DataFrame(detalhes_data)

    # --- ABA 4: ANÁLISE DE MERCADO (VARIAÇÃO VENDA) ---
    variacoes = [0.10, 0.05, 0, -0.05, -0.10, -0.15, -0.20]
    cenarios_venda = []
    for var in variacoes:
        v_venda_var = v_venda * (1 + var)
        comis_var = v_venda_var * comis_cor_perc
        v_venda_liq_var = v_venda_var - comis_var
        luc_bruto_var = v_venda_liq_var - v_financiado - invest_bolso
        v_imp_var = max(0.0, luc_bruto_var * (imp_p/100))
        luc_liq_var = luc_bruto_var - v_imp_var
        roi_var = (luc_liq_var / invest_bolso * 100) if invest_bolso > 0 else 0
        cenarios_venda.append({
            "Variação Mercado": f"{int(var*100)}%",
            "Novo Valor Venda": v_venda_var,
            "Lucro Líquido": luc_liq_var,
            "ROI %": round(roi_var, 2),
            "Status": "VIÁVEL" if roi_var >= 15 else ("RISCO" if roi_var > 0 else "PREJUÍZO")
        })
    df_mercado = pd.DataFrame(cenarios_venda)

    # --- EXPORTAÇÃO ---
    def gerar_excel_final():
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            nova_linha.to_excel(writer, index=False,
                                sheet_name='Simulacao_Atual')
            df_risco.to_excel(writer, index=False,
                              sheet_name='Analise_de_Risco')
            df_mercado.to_excel(writer, index=False,
                                sheet_name='Analise_de_Mercado')
            if not df_detalhes.empty:
                df_detalhes.to_excel(writer, index=False,
                                     sheet_name='Detalhes_Financeiros')

            workbook = writer.book
            green = workbook.add_format(
                {'bg_color': '#C6EFCE', 'font_color': '#006100'})
            red = workbook.add_format(
                {'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
            yellow = workbook.add_format(
                {'bg_color': '#FFEB9C', 'font_color': '#9C6500'})

            # Formatação Risco
            ws_risco = writer.sheets['Analise_de_Risco']
            ws_risco.conditional_format(
                'E2:E12', {'type': 'cell', 'criteria': '<', 'value': 0, 'format': red})
            ws_risco.conditional_format(
                'E2:E12', {'type': 'cell', 'criteria': '>=', 'value': 0, 'format': green})

            # Formatação Mercado
            ws_mercado = writer.sheets['Analise_de_Mercado']
            ws_mercado.conditional_format(
                'D2:D8', {'type': 'cell', 'criteria': '<', 'value': 0, 'format': red})
            ws_mercado.conditional_format('D2:D8', {
                                          'type': 'cell', 'criteria': 'between', 'left': 0, 'right': 15, 'format': yellow})
            ws_mercado.conditional_format(
                'D2:D8', {'type': 'cell', 'criteria': '>=', 'value': 15, 'format': green})

        return output.getvalue()

    st.download_button(
        label="📥 Baixar Relatório Estratégico",
        data=gerar_excel_final(),
        file_name=f"relatorio_estrategico_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        on_click=st.toast,
        args=("Relatório completo com Análise de Mercado gerado!",)
    )


if __name__ == "__main__":
    main()
