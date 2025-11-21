import requests
import json
import yaml
import time
from dataclasses import dataclass
from threading import Lock, Event, Thread
from flask import Flask, request, jsonify

# Classe para guardar informações da nuvem
@dataclass
class Cloud_layer:
    __slots__ = ("name", "layer", "faas_urls")
    name      : str
    layer     : str
    faas_urls : list

    def getfaas_urls(self): return self.faas_urls
    def getlayer(self)    : return self.layer
    def getname(self)     : return self.name

# Classe para guardar informações de hosts na borda e nevoa
@dataclass
class Host_table_entry:
    __slots__ = ("name", "priority", "layer", "faas_urls", "prometheus_api_url",
                 "max_cpu", "max_ram", "min_interval",
                 "cpu_use", "ram_use", "last_use_ts")

    name               : str
    priority           : str
    layer              : str
    faas_urls          : list
    prometheus_api_url : str
    max_cpu            : float
    max_ram            : float
    min_interval       : float
    cpu_use            : float
    ram_use            : float
    last_use_ts        : float

    def getname(self):               return self.name
    def getpriority(self):           return self.priority
    def getlayer(self):              return self.layer
    def getfaas_urls(self):          return self.faas_urls
    def getprometheus_api_url(self): return self.prometheus_api_url
    def getmax_cpu(self):            return self.max_cpu
    def getmax_ram(self):            return self.max_ram
    def getcpu_use(self):            return self.cpu_use
    def getram_use(self):            return self.ram_use


def parse_config(yaml_content):
    edge_fog_hosts_table = []
    cloud_host = None

    yml_data = yaml.safe_load(yaml_content)
    refresh = yml_data.get('refresh_interval_secs')
    hosts_dict = yml_data.get('hosts', {})
    
    for host, properties in hosts_dict.items():
        if (properties.get('layer')) != 'cloud':
            entry = Host_table_entry(
                name=host,
                priority=properties.get('priority'),
                layer=properties.get('layer'),
                faas_urls=properties.get('faas_urls'),
                prometheus_api_url=properties.get('prometheus_api_url'),
                max_cpu=properties.get('max_cpu_use'),
                max_ram=properties.get('max_ram_use'),
                min_interval=properties.get('min_req_interval_secs', 0),
                cpu_use=0,
                ram_use=0,
                last_use_ts=0 
            )
            edge_fog_hosts_table.append(entry)
        else:
            cloud_host = Cloud_layer(
                name=host,
                layer=properties.get('layer'),
                faas_urls=properties.get('faas_urls')
            )

    sorted_hosts = sorted(edge_fog_hosts_table, key=lambda host: host.getpriority() == 'low')
    return refresh, sorted_hosts, cloud_host


def unpack_response(response):
    try:
        response_content_json = json.loads(response.content)
        response_value = float(response_content_json['data']['result'][0]['value'][1])
    except (KeyError, IndexError, json.JSONDecodeError):
        return float('inf')
    return response_value




# Função que apenas coleta métricas (Lenta, roda na thread)
def update_metrics_routine(hosts_table, query_cpu, query_ram):
    for host in hosts_table:
        prometheus_api_url = host.getprometheus_api_url()
        try:
            cpu_response = requests.get(prometheus_api_url, params={'query': query_cpu}, timeout=5)
            ram_response = requests.get(prometheus_api_url, params={'query': query_ram}, timeout=5)
            cpu_response.raise_for_status()
            ram_response.raise_for_status()
            
            host.cpu_use = unpack_response(cpu_response)
            host.ram_use = unpack_response(ram_response)
        except requests.exceptions.RequestException:
            host.cpu_use = float('inf')
            host.ram_use = float('inf')

# Função de decisão (Rápida, roda a cada request)
def select_best_host(edge_fog_hosts_table, cloud_host, function_name):
    
    def get_url_for_function(host, func_name):
        for url in host.getfaas_urls():
            if url.endswith(f"/{func_name}"):
                return url
        return None

    # Percorre a lista (já ordenada por prioridade)
    for host in edge_fog_hosts_table:
        url = get_url_for_function(host, function_name)
        if not url:
            continue # Host não tem essa função

        # Verifica métricas (já atualizadas pela thread)
        cpu_ok = host.cpu_use < host.max_cpu
        ram_ok = host.ram_use < host.max_ram
        
        # Verifica tempo AGORA (Crucial para sua correção)
        now = time.time()
        time_ok = (now - host.last_use_ts) >= host.min_interval

        if cpu_ok and ram_ok and time_ok:
            host.last_use_ts = now # Marca uso IMEDIATAMENTE
            return url

    # Fallback para nuvem
    if cloud_host:
        cloud_url = get_url_for_function(cloud_host, function_name)
        if cloud_url:
            return cloud_url
            
    return None

def get_all_function_names(edge_fog_hosts, cloud_host):
    all_urls = []
    for host in edge_fog_hosts:
        all_urls.extend(host.getfaas_urls())
    if cloud_host:
        all_urls.extend(cloud_host.getfaas_urls())
    func_names = {url.split('/')[-1] for url in all_urls}
    return list(func_names)


app = Flask(__name__)

# Variáveis globais
edge_fog_hosts_table = []
cloud_host = None
refresh_time = 15
# Lock para proteger a tabela de hosts (Thread escreve CPU/RAM, Flask lê e escreve Timestamp)
data_lock = Lock() 
config_received_event = Event()
all_functions = []

@app.route('/faas', methods=['GET', 'POST'])
def server_functionality():
    global edge_fog_hosts_table, cloud_host, refresh_time, all_functions

    if request.method == 'GET':
        if not config_received_event.is_set():
            return jsonify({"status": "aguardando", "message": "Configuração pendente."}), 503

        function_name = request.args.get('function_name')
        if not function_name:
            return jsonify({"error": "Parametro 'function_name' obrigatorio."}), 400

        best_url = None
        with data_lock:
            best_url = select_best_host(edge_fog_hosts_table, cloud_host, function_name)

        if best_url:
            return jsonify({"function_name": function_name, "best_faas_url": best_url})
        else:
            return jsonify({"error": "Nenhum host disponivel."}), 404

    if request.method == 'POST':
        new_config_content = request.get_data(as_text=True)
        if not new_config_content:
            return jsonify({"error": "Configuração vazia."}), 400

        try:
            new_refresh, new_table, new_cloud = parse_config(new_config_content)
            
            with data_lock:
                refresh_time = new_refresh
                edge_fog_hosts_table = new_table
                cloud_host = new_cloud
                all_functions = get_all_function_names(new_table, new_cloud)

            if not config_received_event.is_set():
                config_received_event.set()

            return jsonify({"status": "sucesso"}), 200

        except Exception as e:
            print(f"Erro config: {e}")
            return jsonify({"error": str(e)}), 500

def run_server(host_url, port):
    app.run(host=host_url, port=port, use_reloader=False)

def start(host_url, port):
    global edge_fog_hosts_table
    global refresh_time
    
    # Inicia thread do servidor Flask
    server_thread = Thread(target=run_server, args=(host_url, port))
    server_thread.daemon = True
    server_thread.start()

    print(f"Servidor iniciado em {host_url}:{port}. Aguardando configuração...")
    config_received_event.wait() 

    # Queries Prometheus
    query_cpu = "(1 - avg by (instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[15s]))) * 100"
    query_RAM = "((avg_over_time(node_memory_MemTotal_bytes[15s]) - avg_over_time(node_memory_MemAvailable_bytes[15s]))/ avg_over_time(node_memory_MemTotal_bytes[15s])) * 100"
    
    while True:
        # Copia tempo de refresh e referências para não travar o Lock durante a request de rede
        with data_lock:
            current_refresh = refresh_time
            # Não precisamos copiar a lista inteira, pois vamos modificar os atributos internos dos objetos
            # e queremos que isso reflita globalmente. Mas para iterar com segurança, usamos a ref local.
            hosts_ref = edge_fog_hosts_table 
        
        # Faz as requisições de rede (Lento) SEM o Lock, para não travar o cliente
        update_metrics_routine(hosts_ref, query_cpu, query_RAM)
        
        time.sleep(current_refresh)