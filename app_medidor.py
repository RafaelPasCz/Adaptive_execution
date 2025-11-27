import time
import sys
import os
import threading
from flask import Flask, jsonify, request

RAPL_PATH = "/sys/class/powercap/intel-rapl:0/energy_uj"
ARQUIVO_SAIDA = './saida.csv'

MAX_INT_32 = 4294967296

app = Flask(__name__)

measurement_data = {
    "active": False,      
    "total_uj": 0,        
    "start_time": 0,       
    "last_reading": 0,    
    "thread": None         
}

def read_rapl_energy(path):
    try:
        with open(path, 'r') as f:
            return int(f.read().strip())
    except Exception as e:
        print(f"[ERRO] Falha ao ler RAPL: {e}")
        return 0

def monitor_energy():

    global measurement_data
    
    
    while measurement_data["active"]:
        current_reading = read_rapl_energy(RAPL_PATH)
        last_reading = measurement_data["last_reading"]
        

        delta = current_reading - last_reading
        

        if delta < 0:
            print(f"[AVISO] Overflow detectado! Corrigindo...")
            delta += MAX_INT_32
            
        measurement_data["total_uj"] += delta
        measurement_data["last_reading"] = current_reading
        
        time.sleep(1.0)
        
    print("[THREAD] Monitoramento parado.")

@app.route('/start', methods=['POST'])
def start_measurement():
    global measurement_data
    
    if measurement_data["active"]:
         return jsonify({"status": "erro", "message": "Medição já está em andamento."}), 400

    try:
        initial_reading = read_rapl_energy(RAPL_PATH)
        measurement_data["total_uj"] = 0
        measurement_data["last_reading"] = initial_reading
        measurement_data["start_time"] = time.monotonic()
        measurement_data["active"] = True
        
        t = threading.Thread(target=monitor_energy, daemon=True)
        measurement_data["thread"] = t
        t.start()
        
        print(f"[LOG] Medição iniciada. Leitura base: {initial_reading}")
        return jsonify({"status": "sucesso", "message": "Medição iniciada com sampling."})

    except Exception as e:
        return jsonify({"status": "erro", "message": str(e)}), 500


@app.route('/stop', methods=['POST'])
def stop_measurement():
    global measurement_data
    
    if not measurement_data["active"]:
        return jsonify({"status": "erro", "message": "Nenhuma medição em andamento."}), 400

    try:
        measurement_data["active"] = False
        
        if measurement_data["thread"]:
            measurement_data["thread"].join()

        end_time = time.monotonic()
        final_reading = read_rapl_energy(RAPL_PATH)
        last_thread_reading = measurement_data["last_reading"]
        
        delta_final = final_reading - last_thread_reading
        if delta_final < 0: delta_final += MAX_INT_32
        
        measurement_data["total_uj"] += delta_final

        consumed_uj = measurement_data["total_uj"]
        start_time = measurement_data["start_time"]
        
        elapsed_sec = end_time - start_time
        consumed_j = consumed_uj / 1_000_000.0
        
        avg_cpu_power_w = 0.0
        if elapsed_sec > 0:
            avg_cpu_power_w = consumed_j / elapsed_sec
        
        consumed_cpu_mWh = consumed_j / 3.6

        print(f"[LOG] Finalizado. Tempo: {elapsed_sec:.2f}s, Energia: {consumed_cpu_mWh:.4f} mWh")
        
        if not os.path.exists(ARQUIVO_SAIDA):
             with open(ARQUIVO_SAIDA, "x") as f:
                 f.write("start_time,end_time,elapsed_sec,consumed_cpu_mWh\n")

        with open(ARQUIVO_SAIDA, "a") as f:
             f.write(f"{start_time},{end_time},{elapsed_sec},{consumed_cpu_mWh}\n")
        
        print(f"elaspsed_sec: {elapsed_sec}, consumed_cpu_mWh: {consumed_cpu_mWh}")

        return jsonify({
            "status": "sucesso", 
            "message": "Medição finalizada.",
            "data" : { 
                "elapsed_sec" : elapsed_sec, 
                "consumed_cpu_mWh" : consumed_cpu_mWh,
                "avg_power_W": avg_cpu_power_w
            }
        }), 200

    except Exception as e:
        print(str(e))
        return jsonify({"status": "erro", "message": str(e)}), 500

# --- Main ---

if __name__ == "__main__":
    if not os.path.exists(RAPL_PATH):
        print(f"Erro Crítico: O caminho '{RAPL_PATH}' não existe.", file=sys.stderr)
        sys.exit(1)
        
    print(f"Servidor rAPL com SAMPLING iniciado.")
    print(f"Lendo de: {RAPL_PATH}")
    app.run(host="0.0.0.0", port=6000, debug=False)

