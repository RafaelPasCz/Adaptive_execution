# Alteração importante: Importamos o cliente PADRÃO (sem energia embutida)
# Certifique-se de que o arquivo adapt_exec_client.py está na pasta Adaptive_execution
import adapt_exec_client as adapt_faas
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

print(f"Tempo de espera: {TEMPO_ESPERA}")

# URLs do Medidor (Controlado manualmente agora)
NEVOA_IP = "10.81.24.151"
START_URL = f"http://{NEVOA_IP}:6000/start"
STOP_URL = f"http://{NEVOA_IP}:6000/stop"

ARQUIVO_SAIDA = f"resultados_adaptativo_{TEMPO_ESPERA}.csv"
DATASET_PATH = "/root/teste_nevoa/dataset/"
ARQUIVO_CONFIG = "./config.yml"

# Configuração do Cliente Adaptativo

URL_BORDA = "http://10.81.24.31:8080/function/crowdcount-yolo"
URL_NEVOA = "http://10.81.24.151:31112/function/crowdcount-yolo"
URL_NUVEM = "http://34.39.213.167:30080/function/crowdcount-yolo"

ADAPT_SERVER_URL = "http://10.81.24.139:5000"

# Inicializa o cliente (Padrão, sem medição interna)
adapt_client = adapt_faas.Adaptive_FaaS(ADAPT_SERVER_URL, ARQUIVO_CONFIG)
response = adapt_client.send_config()
print(response.text)
time.sleep(11)
fotos = sorted(os.listdir(DATASET_PATH))

# --- Variáveis Globais e Locks ---
faces_lock = threading.Lock()
total_faces_iteracao = 0 # Será resetado a cada iteração
lista_faas = [] # append o faas escolhido
# --- Preparação do CSV ---
# Agora salvamos o resumo da iteração
if not os.path.exists(ARQUIVO_SAIDA):
    with open(ARQUIVO_SAIDA, 'w') as f:
        f.write("timestamp,iteracao,duracao_s,energia_mWh,total_faces,num_borda,num_nevoa,num_nuvem\n")

# --- Funções Auxiliares ---
def serialize(imgpath):
    img = cv2.imread(imgpath)
    imgdata = pickle.dumps(img)
    imserial = {'image_data' : base64.b64encode(imgdata).decode('ascii')}
    return imserial

def construct_json(imserial):
    data = {'data' : imserial}
    json_data = json.dumps(data)
    return json_data

# --- Função da Thread (Sem medição de energia individual) ---
def processar_foto_em_thread(foto_path):
    """
    Processa a foto usando o cliente adaptativo e soma as faces detectadas ao total global.
    """
    global total_faces_iteracao, lista_faas
    
    try:
        imserial = serialize(foto_path)
        img_json = construct_json(imserial)

        # O cliente padrão retorna: response, best_faas
        # (Não retorna energia, pois tiramos a versão ENERGY)
        response, best_faas = adapt_client.request("crowdcount-yolo", img_json, json=True, timeout=100)
        print(best_faas)
        # Processa resposta (contagem de faces)
        if '\n' in response.text.strip():
            faces = int(response.text.strip().split('\n')[-1])
        else:
            faces = int(response.text)
        print(best_faas)
        # Atualiza o contador global com segurança (Lock)
        with faces_lock:
            total_faces_iteracao += faces
            lista_faas.append(best_faas)


    except Exception as e:
        print(f"Erro processando {foto_path}: {e}")

# --- Loop Principal ---
print(f"Iniciando processamento acumulado. Saída em: {ARQUIVO_SAIDA}")

# Sessão para o medidor de energia
with requests.Session() as session_medidor:
    for i in range(5):
        print(f"--- Iniciando Iteração {i} ---")
        
        # Reset de variáveis da iteração
        with faces_lock:
            total_faces_iteracao = 0
        threads = []
        measurement_id = None
        
        # 1. Inicia Medição (Apenas se i > 1 para evitar Cold Start/Warmup)
        if i > 1:
            try:
                resp_start = session_medidor.post(START_URL)
                resp_start.raise_for_status()

            except Exception as e:
                print(f"Erro ao iniciar medição: {e}")

        start_time_iteracao = time.monotonic()
        timestamp_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#        print(fotos)
        # 2. Dispara Threads
        for foto in fotos:
            foto_completa = os.path.join(DATASET_PATH, foto)
            #print(foto_completa)
            t = threading.Thread(target=processar_foto_em_thread, args=(foto_completa,))
            threads.append(t)
            t.start()
            time.sleep(TEMPO_ESPERA)

        # 3. Aguarda todas as threads terminarem
        for t in threads:
            t.join()

        end_time_iteracao = time.monotonic()
        duracao = end_time_iteracao - start_time_iteracao

        # 4. Para Medição e Salva (Apenas se i > 1 e medição foi iniciada)
        if i > 1:
            try:
                # Envia STOP com o ID obtido no inicio
                resp_stop = session_medidor.post(STOP_URL)
                resp_stop.raise_for_status()
                
                # Recupera dados
                dados_energia = resp_stop.json()
                energia_mWh = float(dados_energia["data"]["consumed_cpu_mWh"])
                nevoa_count = 0
                borda_count = 0
                nuvem_count = 0
                
                for item in lista_faas:
                    if item == URL_BORDA:
                        borda_count += 1
                    elif item == URL_NEVOA:
                        nevoa_count += 1
                    elif item == URL_NUVEM:
                        nuvem_count += 1

                # Salva no CSV
                with open(ARQUIVO_SAIDA, 'a') as f:
                    # timestamp, iteracao, duracao, energia, total_faces, url_exemplo
                    # (url_exemplo é apenas ilustrativo aqui, pois pode variar no adaptativo)
                    f.write(f"{timestamp_now},{i},{duracao:.4f},{energia_mWh},{total_faces_iteracao},{borda_count},{nevoa_count},{nuvem_count}\n")

            except Exception as e:
                print(f"Erro ao finalizar medição ou salvar: {e}")
        else:
            print(f"Iteração {i} concluída (Warmup ou erro).")
            
        lista_faas = []
        nevoa_count = 0
        borda_count = 0
        nuvem_count = 0
    with open(ARQUIVO_SAIDA, 'a') as f:
        f.write("\n")

print("Processo finalizado.")

