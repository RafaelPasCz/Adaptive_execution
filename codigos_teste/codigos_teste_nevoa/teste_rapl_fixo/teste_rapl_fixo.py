import sys
import requests
import time
import os
import cv2
import json
import pickle
import base64
import threading
from datetime import datetime

# --- Configurações ---

TEMPO_ESPERA = int(sys.argv[1])

print(f"Tempo de espera entre disparos: {TEMPO_ESPERA}")
ARQUIVO_SAIDA = f"resultados_fixo_{TEMPO_ESPERA}.csv"
NEVOA_IP = "10.81.24.151"
OPENFAAS_URL = f"http://{NEVOA_IP}:31112/function/crowdcount-yolo"
DATASET_PATH = "/root/teste_nevoa/dataset"

START_URL = f"http://{NEVOA_IP}:6000/start"
STOP_URL = f"http://{NEVOA_IP}:6000/stop"

fotos = sorted(os.listdir(DATASET_PATH))

# --- Variáveis Globais e Locks ---
faces_lock = threading.Lock()
total_faces_iteracao = 0 # Contador resetado a cada iteração principal

# --- Preparação do Arquivo CSV ---
# Agora o CSV registra o resumo da ITERAÇÃO, não de cada foto
if not os.path.exists(ARQUIVO_SAIDA):
    with open(ARQUIVO_SAIDA, 'w') as f:
        f.write("timestamp,iteracao,duracao_s,energia_mWh,total_faces_detectadas\n")

# --- Funções de Serialização ---
def serialize(imgpath):
    img = cv2.imread(imgpath)
    imgdata = pickle.dumps(img)
    imserial = {'image_data' : base64.b64encode(imgdata).decode('ascii')}
    return imserial

def construct_json(imserial):
    data = {'data' : imserial}
    json_data = json.dumps(data)
    return json_data

# --- Função da Thread (Simplificada) ---
def processar_foto_em_thread(foto_path, session):
    """
    Apenas processa a imagem e incrementa o contador de faces.
    NÃO mede energia individualmente.
    """
    global total_faces_iteracao
    
    try:
        # 1. Serialização
        imserial = serialize(foto_path)
        img_json = construct_json(imserial)

        # 2. Processa a função principal (Invisível ao medidor individual, mas capturado pelo global)
        response_openfass = session.post(OPENFAAS_URL, data=img_json)

        # 3. Extrai contagem de faces
        if '\n' in response_openfass.text.strip():
            texto_direita = response_openfass.text.strip().split('\n')[-1]
            faces_count = texto_direita
        else:
            faces_count = response_openfass.text

        faces = int(faces_count)

        # 4. Atualiza contagem global da iteração atual
        with faces_lock:
            total_faces_iteracao += faces

    except requests.exceptions.RequestException as e:
        print(f"Erro de HTTP processando {foto_path}: {e}")
    except Exception as e:
        print(f"Erro inesperado na thread: {e}")

# --- Loop Principal ---
print("Iniciando disparos em lote...")

with requests.Session() as session:
    for i in range(5):
        print("COMEÇANDO")
        with faces_lock:
            total_faces_iteracao = 0
        
        threads_da_iteracao = []
        # 1. Inicia Medição (Apenas se i > 1)
        # O warmup (i=0, i=1) roda sem medir para estabilizar o sistema
        if i > 1:
            try:
                response_start = session.post(START_URL)
                response_start.raise_for_status()
            except Exception as e:
                print(f"Erro ao iniciar medição: {e}")

        start_time_iteracao = time.monotonic()
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 2. Dispara todas as threads da iteração
        for foto in fotos:
            foto_completa = os.path.join(DATASET_PATH, foto)

            t = threading.Thread(
                target=processar_foto_em_thread,
                args=(foto_completa, session)
            )
            threads_da_iteracao.append(t)
            t.start()

            time.sleep(TEMPO_ESPERA)

        # 3. Aguarda TODAS as threads dessa iteração terminarem antes de parar a medição
        # Isso é crucial para pegar a energia de todo o processamento
        for t in threads_da_iteracao:
            t.join()

        end_time_iteracao = time.monotonic()
        duracao = end_time_iteracao - start_time_iteracao

        # 4. Para Medição e Salva (Apenas se i > 1 e se start funcionou)
        if i > 1:
            try:
                # Envia o ID para parar a medição correta
                response_energy = session.post(STOP_URL)
                response_energy.raise_for_status()
                
                data_resp = response_energy.json()
                energy = float(data_resp["data"]["consumed_cpu_mWh"])

                # Escrita no CSV
                with open(ARQUIVO_SAIDA, 'a') as f:
                    f.write(f"{timestamp_str},{i},{duracao:.4f},{energy},{total_faces_iteracao}\n")
                
                print(f"Iteração {i} salva: {energy} mWh, {total_faces_iteracao} faces em {duracao:.2f}s")

            except Exception as e:
                print(f"Erro ao finalizar medição ou salvar: {e}")
        else:
            print(f"Iteração {i} concluída (Warmup ou erro no start).")

print("Processo finalizado.")

