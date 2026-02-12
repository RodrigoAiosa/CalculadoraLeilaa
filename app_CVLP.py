import cv2
import pandas as pd
import os
import numpy as np
from ultralytics import YOLO
import supervision as sv
from datetime import datetime
import tkinter as tk
from tkinter import simpledialog

# --- VARIÁVEIS GLOBAIS ---
pontos_temporarios = []
todas_as_zonas_pontos = []
nomes_das_zonas = []
fator_x, fator_y = 1.0, 1.0

def obter_resolucao_monitor():
    try:
        root = tk.Tk()
        l, a = root.winfo_screenwidth(), root.winfo_screenheight()
        root.destroy()
        return l, a
    except:
        return 1280, 720 # Fallback para servidores sem monitor

def pedir_nome_zona():
    root = tk.Tk()
    root.withdraw()
    # Largura ajustada para exibir o título completo 'Nova Área'
    prompt = " " * 60 + "\nDigite o nome desta zona de carga:"
    nome = simpledialog.askstring("Nova Área", prompt, 
                                  initialvalue=f"Area_{len(todas_as_zonas_pontos)+1}")
    root.destroy()
    return nome if nome else f"Area_{len(todas_as_zonas_pontos)+1}"

def clique_mouse(event, x, y, flags, param):
    global pontos_temporarios, todas_as_zonas_pontos, nomes_das_zonas, fator_x, fator_y
    if event == cv2.EVENT_LBUTTONDOWN:
        x_real, y_real = int(x / fator_x), int(y / fator_y)
        if len(pontos_temporarios) >= 3:
            p_ini = pontos_temporarios[0]
            if np.sqrt((x_real - p_ini[0])**2 + (y_real - p_ini[1])**2) < 20:
                todas_as_zonas_pontos.append(np.array(pontos_temporarios))
                nomes_das_zonas.append(pedir_nome_zona())
                pontos_temporarios = []
                return
        pontos_temporarios.append([x_real, y_real])

def carregar_persistente():
    arquivo = r"C:\Users\aiosa\OneDrive\Clientes\Suzano\relatorio_doc.xlsx"
    contagens = {nome: 0 for nome in nomes_das_zonas}
    if os.path.exists(arquivo):
        try:
            df = pd.read_excel(arquivo, sheet_name='Relatório Detalhado')
            for nome in nomes_das_zonas:
                ultimo = df[df['Area'] == nome]['Total Acumulado'].tail(1).values
                if len(ultimo) > 0: contagens[nome] = int(ultimo[0])
        except: pass
    return contagens

def processar_v16_streamlit_ready():
    global fator_x, fator_y, pontos_temporarios, todas_as_zonas_pontos, nomes_das_zonas
    
    pasta = r"C:\Users\aiosa\OneDrive\Clientes\Suzano\video_base"
    if not os.path.exists(pasta):
        print("Erro: Pasta de vídeos não encontrada.")
        return
        
    arquivos = [f for f in os.listdir(pasta) if f.lower().endswith(('.mp4', '.avi'))]
    if not arquivos: return
    caminho_in = os.path.join(pasta, arquivos[0])

    cap = cv2.VideoCapture(caminho_in)
    fps = cap.get(cv2.CAP_PROP_FPS)
    ret, frame_ref = cap.read()
    if not ret: return

    l_mon, a_mon = obter_resolucao_monitor()
    l_vid, a_vid = int(cap.get(3)), int(cap.get(4))
    fator_x, fator_y = l_mon / l_vid, a_mon / a_vid

    # --- ETAPA DE MARCAÇÃO ---
    cv2.namedWindow("Marcacao", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("Marcacao", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.setMouseCallback("Marcacao", clique_mouse)

    while True:
        frame_draw = cv2.resize(frame_ref.copy(), (l_mon, a_mon))
        for i, z in enumerate(todas_as_zonas_pontos):
            pts = np.array([[int(p[0]*fator_x), int(p[1]*fator_y)] for p in z])
            cv2.polylines(frame_draw, [pts], True, (0, 255, 0), 2)
        if pontos_temporarios:
            pts = np.array([[int(p[0]*fator_x), int(p[1]*fator_y)] for p in pontos_temporarios])
            cv2.polylines(frame_draw, [pts], False, (255, 255, 0), 2)
        cv2.imshow("Marcacao", frame_draw)
        if cv2.waitKey(1) & 0xFF == ord('q'): break
    cv2.destroyAllWindows()

    contagem_sessao = [carregar_persistente().get(nome, 0) for nome in nomes_das_zonas]
    
    model = YOLO('yolov8n.pt') 
    backSub = cv2.createBackgroundSubtractorMOG2(history=1200, varThreshold=50, detectShadows=True)
    zonas = [sv.PolygonZone(polygon=p) for p in todas_as_zonas_pontos]
    anotadores_zona = [sv.PolygonZoneAnnotator(zone=z, color=sv.Color.GREEN, thickness=2) for z in zonas]
    zona_ocupada = [False for _ in zonas]

    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    path_out = os.path.join(r"C:\Users\aiosa\OneDrive\Clientes\Suzano", f"resultado_{ts}.mp4")
    out = cv2.VideoWriter(path_out, cv2.VideoWriter_fourcc(*'mp4v'), fps, (l_vid, a_vid))

    ultimo_seg_log = -1

    while cap.isOpened():
        frame_id = cap.get(cv2.CAP_PROP_POS_FRAMES)
        ret, frame = cap.read()
        if not ret: break

        segundo_atual = int(frame_id / fps)
        results = model(frame, verbose=False, conf=0.45)[0]
        pessoas_boxes = results.boxes.xyxy.cpu().numpy()[np.where(results.boxes.cls.cpu().numpy() == 0)[0]]

        fg_mask = backSub.apply(frame)
        _, fg_mask = cv2.threshold(fg_mask, 220, 255, cv2.THRESH_BINARY)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))

        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections_list = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 15000: continue 
            
            x, y, w, h = cv2.boundingRect(cnt)
            centro_obj = (x + w//2, y + h//2)
            
            # BLOQUEIO REFORÇADO: Raio de 120px para ignorar pessoas com panos
            perto_de_pessoa = False
            for p_box in pessoas_boxes:
                margem_exclusao = [p_box[0]-120, p_box[1]-120, p_box[2]+120, p_box[3]+120]
                if (margem_exclusao[0] < centro_obj[0] < margem_exclusao[2]) and \
                   (margem_exclusao[1] < centro_obj[1] < margem_exclusao[3]):
                    perto_de_pessoa = True; break
            
            if not perto_de_pessoa:
                detections_list.append([x, y, x+w, y+h])
                cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)

        det_final = sv.Detections(xyxy=np.array(detections_list)) if detections_list else sv.Detections.empty()

        # Barra Cinza de Acompanhamento
        cv2.rectangle(frame, (0, 0), (l_vid, 50), (220, 220, 220), -1)
        tempo_str = f"Tempo: {segundo_atual // 60:02d}:{segundo_atual % 60:02d}"
        texto_topo = tempo_str + " | "

        for i, zona in enumerate(zonas):
            mask = zona.trigger(detections=det_final)
            if np.any(mask) and not zona_ocupada[i]:
                contagem_sessao[i] += 70 # Métrica Suzano
                zona_ocupada[i] = True
            elif not np.any(mask):
                zona_ocupada[i] = False

            frame = anotadores_zona[i].annotate(scene=frame)
            texto_topo += f"{nomes_das_zonas[i]}: {contagem_sessao[i]} | "
            
        if segundo_atual > ultimo_seg_log:
            print(f"[ACOMPANHAMENTO] {tempo_str} -> {texto_topo.split('|', 1)[1].strip()}")
            ultimo_seg_log = segundo_atual

        cv2.putText(frame, texto_topo, (25, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
        out.write(frame)
        cv2.imshow("Monitoramento - V16", cv2.resize(frame, (l_mon, a_mon)))
        if cv2.waitKey(1) & 0xFF == ord('q'): break

    cap.release()
    out.release()
    cv2.destroyAllWindows()
    
    # Salvar e preservar dados
    dados = [{'Data': datetime.now().strftime("%d/%m/%Y %H:%M"), 'Area': n, 'Total Acumulado': contagem_sessao[i]} 
             for i, n in enumerate(nomes_das_zonas)]
    salvar_excel_final(dados)

def salvar_excel_final(dados):
    arquivo = r"C:\Users\aiosa\OneDrive\Clientes\Suzano\relatorio_doc.xlsx"
    df_novo = pd.DataFrame(dados)
    if os.path.exists(arquivo):
        with pd.ExcelWriter(arquivo, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
            try:
                df_antigo = pd.read_excel(arquivo, sheet_name='Relatório Detalhado')
                pd.concat([df_antigo, df_novo], ignore_index=True).to_excel(writer, sheet_name='Relatório Detalhado', index=False)
            except: df_novo.to_excel(writer, sheet_name='Relatório Detalhado', index=False)
    else: df_novo.to_excel(arquivo, sheet_name='Relatório Detalhado', index=False)

if __name__ == "__main__":
    processar_v16_streamlit_ready()
