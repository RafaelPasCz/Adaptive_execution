import sys
import requests
import time
import os
import cv2
import json
import pickle
import base64
import threading
import serial  # Nova importação necessária
from datetime import datetime

# --- Configurações ---

TEMPO_ESPERA = int(sys.argv[1])
SERIAL_PORT = '/dev/ttyUSB0' # Porta do medidor
BAUDRATE = 115200

print(f"Tempo de espera entre disparos: {TEMPO_ESPERA}")
ARQUIVO_SAIDA = f"resultados_fixo_{TEMPO_ESPERA}.csv"
BORDA_IP = "10.81.24.31"
OPENFAAS_URL = f"http://{BORDA_IP}:8080/function/crowdcount-yolo"
DATASET_PATH = "/root/teste_nevoa/dataset"

fotos = sorted(os.listdir(DATASET_PATH))

# --- Variáveis Globais e Locks ---
faces_lock = threading.Lock()
total_faces_iteracao = 0 

# Controle da Serial
stop_serial = False
serial_data_lock = threading.Lock()
energy_shared_data = {"total_mWh": 0.0}

# --- Preparação do Arquivo CSV ---
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

# --- Função de Leitura Serial (Adaptada de processar_imagens_1r.py) ---
def read_serial_and_compute_energy(shared_data, lock, port, baudrate):
    global stop_serial
    try:
        with serial.Serial(port, baudrate, timeout=1) as ser:
            prev_time = None
            # Reseta a energia acumulada no início da thread
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
                                # Evita saltos negativos ou muito grandes caso o microcontrolador reinicie
                                if delta_ms > 0:
                                    energy_mWh = (power * delta_ms) / 3600000  # mWh
                                    with lock:
                                        shared_data["total_mWh"] += energy_mWh
                            
                            prev_time = timestamp
                    except ValueError:
                        continue
    except serial.SerialException as e:
        print(f"[Energy] Erro na porta serial: {e}")

# --- Função da Thread de Processamento ---
def processar_foto_em_thread(foto_path, session):
    global total_faces_iteracao
    try:
        imserial = serialize(foto_path)
        img_json = construct_json(imserial)
        
        # Timeout adicionado para evitar travamento eterno
        response_openfass = session.post(OPENFAAS_URL, data=img_json, timeout=60)

        if '\n' in response_openfass.text.strip():
            texto_direita = response_openfass.text.strip().split('\n')[-1]
            faces_count = texto_direita
        else:
            faces_count = response_openfass.text

        faces = int(faces_count)

        with faces_lock:
            total_faces_iteracao += faces

    except requests.exceptions.RequestException as e:
        print(f"Erro de HTTP processando {foto_path}: {e}")
    except Exception as e:
        print(f"Erro inesperado na thread: {e}")

# --- Loop Principal ---
print("Iniciando disparos em lote com medição serial local...")

with requests.Session() as session:
    for i in range(5):
        print(f"--- Iniciando Iteração {i} ---")
        
        with faces_lock:
            total_faces_iteracao = 0
        
        threads_da_iteracao = []
        thread_energia = None
        
        # 1. Inicia Medição Serial (Apenas se i > 1 para Warmup)
        if i > 1:
            stop_serial = False
            thread_energia = threading.Thread(
                target=read_serial_and_compute_energy, 
                args=(energy_shared_data, serial_data_lock, SERIAL_PORT, BAUDRATE)
            )
            thread_energia.start()
            # Pequeno delay para garantir que a serial abriu
            time.sleep(1) 

        start_time_iteracao = time.monotonic()
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 2. Dispara todas as threads da iteração
        for foto in fotos:
            foto_completa = os.path.join(DATASET_PATH, foto)
            t = threading.Thread(target=processar_foto_em_thread, args=(foto_completa, session))
            threads_da_iteracao.append(t)
            t.start()
            time.sleep(TEMPO_ESPERA)

        # 3. Aguarda processamento de imagem
        for t in threads_da_iteracao:
            t.join()

        end_time_iteracao = time.monotonic()
        duracao = end_time_iteracao - start_time_iteracao

        # 4. Finaliza Medição e Salva
        if i > 1 and thread_energia:
            stop_serial = True
            thread_energia.join() # Aguarda a thread de energia fechar o arquivo/porta
            
            # Recupera o valor acumulado
            with serial_data_lock:
                energy = energy_shared_data["total_mWh"]

            try:
                with open(ARQUIVO_SAIDA, 'a') as f:
                    f.write(f"{timestamp_str},{i},{duracao:.4f},{energy:.6f},{total_faces_iteracao}\n")
                
                print(f"Iteração {i} salva: {energy:.6f} mWh, {total_faces_iteracao} faces em {duracao:.2f}s")
            except Exception as e:
                print(f"Erro ao salvar arquivo: {e}")
        else:
            print(f"Iteração {i} concluída (Warmup).")

print("Processo finalizado.")
