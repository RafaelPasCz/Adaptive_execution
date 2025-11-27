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
import serial # Nova importação
from datetime import datetime

# --- Configurações ---

TEMPO_ESPERA = int(sys.argv[1])
SERIAL_PORT = '/dev/ttyUSB0'
BAUDRATE = 115200

print(f"Tempo de espera: {TEMPO_ESPERA}")

ARQUIVO_SAIDA = f"resultados_adaptativo_{TEMPO_ESPERA}.csv"
DATASET_PATH = "/root/teste_nevoa/dataset/"
ARQUIVO_CONFIG = "./config.yml"

# Configuração do Cliente Adaptativo
URL_BORDA = "http://10.81.24.31:8080/function/crowdcount-yolo"
URL_NEVOA = "http://10.81.24.151:31112/function/crowdcount-yolo"
URL_NUVEM = "http://34.39.213.167:30080/function/crowdcount-yolo"

ADAPT_SERVER_URL = "http://10.81.24.139:5000"

# Inicializa o cliente
adapt_client = adapt_faas.Adaptive_FaaS(ADAPT_SERVER_URL, ARQUIVO_CONFIG)
response = adapt_client.send_config()
print(response.text)
time.sleep(11)
fotos = sorted(os.listdir(DATASET_PATH))

# --- Variáveis Globais e Locks ---
faces_lock = threading.Lock()
total_faces_iteracao = 0
lista_faas = []

# Controle da Serial
stop_serial = False
serial_data_lock = threading.Lock()
energy_shared_data = {"total_mWh": 0.0}

# --- Preparação do CSV ---
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

# --- Função de Leitura Serial (Igual ao script anterior) ---
def read_serial_and_compute_energy(shared_data, lock, port, baudrate):
    global stop_serial
    try:
        with serial.Serial(port, baudrate, timeout=1) as ser:
            prev_time = None
            with lock:
                shared_data["total_mWh"] = 0.0
            
            print(f"[Energy] Iniciando leitura na porta {port}...")
            
            while not stop_serial:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    try:
                        parts = line.split(";")
                        if len(parts) >= 3:
                            timestamp_str, current_str, voltage_str = parts[0], parts[1], parts[2]
                            timestamp = int(timestamp_str)
                            current = float(current_str)
                            voltage = float(voltage_str)
                            power = current * voltage  # mW

                            if prev_time is not None:
                                delta_ms = timestamp - prev_time
                                if delta_ms > 0:
                                    energy_mWh = (power * delta_ms) / 3600000
                                    with lock:
                                        shared_data["total_mWh"] += energy_mWh
                            
                            prev_time = timestamp
                    except ValueError:
                        continue
    except serial.SerialException as e:
        print(f"[Energy] Erro na porta serial: {e}")


# --- Função da Thread de Processamento ---
def processar_foto_em_thread(foto_path):
    global total_faces_iteracao, lista_faas
    try:
        imserial = serialize(foto_path)
        img_json = construct_json(imserial)

        response, best_faas = adapt_client.request("crowdcount-yolo", img_json, json=True, timeout=100)
        
        if '\n' in response.text.strip():
            faces = int(response.text.strip().split('\n')[-1])
        else:
            faces = int(response.text)
        
        with faces_lock:
            total_faces_iteracao += faces
            lista_faas.append(best_faas)

    except Exception as e:
        print(f"Erro processando {foto_path}: {e}")

# --- Loop Principal ---
print(f"Iniciando processamento acumulado adaptativo com medição serial. Saída em: {ARQUIVO_SAIDA}")

# Como o adapt_client gerencia requests internamente, usamos requests.Session apenas se for necessário,
# mas aqui o loop principal controla a estrutura.
for i in range(5):
    print(f"--- Iniciando Iteração {i} ---")
    
    # Reset de variáveis da iteração
    with faces_lock:
        total_faces_iteracao = 0
        lista_faas = [] # Limpa a lista da iteração anterior
    
    threads = []
    thread_energia = None
    
    # 1. Inicia Medição Serial (se i > 1)
    if i > 1:
        stop_serial = False
        thread_energia = threading.Thread(
            target=read_serial_and_compute_energy, 
            args=(energy_shared_data, serial_data_lock, SERIAL_PORT, BAUDRATE)
        )
        thread_energia.start()
        time.sleep(1)

    start_time_iteracao = time.monotonic()
    timestamp_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 2. Dispara Threads
    for foto in fotos:
        foto_completa = os.path.join(DATASET_PATH, foto)
        t = threading.Thread(target=processar_foto_em_thread, args=(foto_completa,))
        threads.append(t)
        t.start()
        time.sleep(TEMPO_ESPERA)

    # 3. Aguarda todas as threads terminarem
    for t in threads:
        t.join()

    end_time_iteracao = time.monotonic()
    duracao = end_time_iteracao - start_time_iteracao

    # 4. Para Medição e Salva
    if i > 1 and thread_energia:
        stop_serial = True
        thread_energia.join()
        
        with serial_data_lock:
            energia_mWh = energy_shared_data["total_mWh"]
                
        for item in lista_faas:
            if item == URL_BORDA:
                borda_count += 1
            elif item == URL_NEVOA:
                nevoa_count += 1
            elif item == URL_NUVEM:
                nuvem_count += 1

        try:
            with open(ARQUIVO_SAIDA, 'a') as f:
                f.write(f"{timestamp_now},{i},{duracao:.4f},{energia_mWh:.6f},{total_faces_iteracao},{borda_count},{nevoa_count},{nuvem_count}\n")
            print(f"Iteração {i} salva. Energia: {energia_mWh:.4f} mWh.")
        except Exception as e:
            print(f"Erro ao salvar: {e}")
    else:
        print(f"Iteração {i} concluída (Warmup).")
    
    nevoa_count = 0
    borda_count = 0
    nuvem_count = 0
    lista_faas = []
    # Garante separação visual no CSV se necessário, ou apenas segue
    # No código original havia um write('\n') ao final de tudo, mantemos fora do loop se quiser.

print("Processo finalizado.")
