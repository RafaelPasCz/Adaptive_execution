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
    __slots__ = ("name", "layer", "faas_urls", "min_req_interval", "last_usage_ts")
    name             : str
    layer            : str
    faas_urls        : list
    min_req_interval : float # Novo parametro
    last_usage_ts    : float # Novo parametro para controle de tempo


    def getfaas_urls(self): return self.faas_urls
    def getlayer(self)    : return self.layer
    def getname(self)     : return self.name

    def print_slots(self):
        print("-------------------------------------------")
        print(f"name: {self.name}\n",
              f"layer: {self.layer}\n",
              f"min_req_interval: {self.min_req_interval}\n",
              f"faas_urls: {self.faas_urls}"
              )
        print("-------------------------------------------")


# Classe para guardar informações de hosts na borda e nevoa
@dataclass
class Host_table_entry:
    __slots__ = ("name", "priority", "layer", "faas_urls", "prometheus_api_url",
                 "max_cpu", "max_ram", "min_req_interval",
                 "cpu_use", "ram_use", "last_usage_ts")

    # Nome, camada e url de apis
    name               : str
    priority           : str
    layer              : str
    faas_urls          : list
    prometheus_api_url : str
    # Máximos e Minimos definidos na configuração
    max_cpu            : float
    max_ram            : float
    min_req_interval   : float # Novo parametro
    # Atributos que serão atualizados na execução
    cpu_use            : float
    ram_use            : float
    last_usage_ts      : float # Novo parametro (timestamp da ultima escolha)


    def print_slots(self): 
        print("-------------------------------------------")
        print(f"name: {self.name}\n",
              f"priority: {self.priority}\n",
              f"layer: {self.layer}\n",
              f"faas_urls: {self.faas_urls}\n",
              f"prometheus_api_url: {self.prometheus_api_url}\n",
              f"max_cpu: {self.max_cpu}\n",
              f"max_ram: {self.max_ram}\n",
              f"min_req_interval: {self.min_req_interval}\n",
              f"cpu_use: {self.cpu_use}\n",
              f"ram_use: {self.ram_use}\n",
              f"last_usage_ts: {self.last_usage_ts}"
              )
        print("-------------------------------------------")

    def getname(self):               return self.name
    def getpriority(self):           return self.priority
    def getlayer(self):              return self.layer
    def getfaas_urls(self):          return self.faas_urls
    def getprometheus_api_url(self): return self.prometheus_api_url
    def getmax_cpu(self):            return self.max_cpu
    def getmax_ram(self):            return self.max_ram
    def getcpu_use(self):            return self.cpu_use
    def getram_use(self):            return self.ram_use


def print_table(entry_list):
    for entry in entry_list:
        entry.print_slots()

# Função para processar o arquivo de configuração
def parse_config(yaml_content):
    edge_fog_hosts_table = []
    cloud_host = None

    yml_data = yaml.safe_load(yaml_content)

    refresh = yml_data.get('refresh_interval_secs')
    hosts_dict = yml_data.get('hosts', {})
    
    for host, properties in hosts_dict.items():
        # Pega o intervalo minimo, se não existir, assume 0
        min_interval = properties.get('min_request_interval', 0)

        if (properties.get('layer')) != 'cloud':
            entry = Host_table_entry(
                name=host,
                priority=properties.get('priority'),
                layer=properties.get('layer'),
                faas_urls=properties.get('faas_urls'),
                prometheus_api_url=properties.get('prometheus_api_url'),
                max_cpu=properties.get('max_cpu_use'),
                max_ram=properties.get('max_ram_use'),
                min_req_interval=min_interval,
                cpu_use=0,
                ram_use=0,
                last_usage_ts=0 # Inicia com 0 para estar disponível imediatamente
            )
            edge_fog_hosts_table.append(entry)
        else:
            cloud_host = Cloud_layer(
                name=host,
                layer=properties.get('layer'),
                faas_urls=properties.get('faas_urls'),
                min_req_interval=min_interval,
                last_usage_ts=0
            )

    sorted_hosts = sorted(edge_fog_hosts_table, key=lambda host: host.getpriority() == 'low')
    return refresh, sorted_hosts, cloud_host


def find_best_faas(edge_fog_hosts_table, cloud_host, query_cpu, query_RAM, function_name):

    def get_url_for_function(host, func_name):
        for url in host.getfaas_urls():
            if url.endswith(f"/{func_name}"):
                return url
        return None

    def is_host_available(host):
        # 1. Verifica se o host tem a função
        if not get_url_for_function(host, function_name):
            return False
        
        # 2. Verifica tempo (Intervalo Minimo)
        current_time = time.time()
        if (current_time - host.last_usage_ts) < host.min_req_interval:
            return False

        # 3. Verifica Recursos (CPU e RAM) - Apenas para Fog/Edge que tem limites definidos
        # Cloud_layer não tem método getcpu_use, então tratamos diferente se necessário,
        # mas aqui 'host' é sempre da lista edge_fog_hosts_table
        cpu_ok = host.getcpu_use() < host.getmax_cpu()
        ram_ok = host.getram_use() < host.getmax_ram()
        
        return cpu_ok and ram_ok

    def update_metrics():
        for host in edge_fog_hosts_table:
            prometheus_api_url = host.getprometheus_api_url()
            try:
                cpu_response = requests.get(prometheus_api_url, params={'query': query_cpu}, timeout=5)
                ram_response = requests.get(prometheus_api_url, params={'query': query_RAM}, timeout=5)
                cpu_response.raise_for_status()
                ram_response.raise_for_status()
                host.cpu_use = unpack_response(cpu_response)
                host.ram_use = unpack_response(ram_response)
            except requests.exceptions.RequestException as e:
                host.cpu_use = float('inf')
                host.ram_use = float('inf')

    # Atualiza metricas antes de decidir
    update_metrics()

    # Pesquisa nos hosts ordenados (Edge/Fog)
    for host in edge_fog_hosts_table:
        if is_host_available(host):
            # Se escolheu este host, atualiza o timestamp de uso
            host.last_usage_ts = time.time()
            return get_url_for_function(host, function_name)
    
    # Se não encontra nenhum host apropriado na borda/nevoa, checa a nuvem
    cloud_url = get_url_for_function(cloud_host, function_name)
    if cloud_url:
        # Verifica o tempo também para a nuvem (opcional, mas consistente com o código)
        if (time.time() - cloud_host.last_usage_ts) >= cloud_host.min_req_interval:
            cloud_host.last_usage_ts = time.time()
            return cloud_url
        # Se a nuvem também estiver no intervalo de espera (raro), retornaria None ou forçaria o uso.
        # Aqui mantive a logica de retornar None se estiver no cooldown, 
        # mas você pode remover o 'if' acima se quiser que a nuvem seja o fallback incondicional.
    
    return None


def unpack_response(response):
    response_content_json = json.loads(response.content)
    try:
        response_value = float(response_content_json['data']['result'][0]['value'][1])
        return response_value
    except (KeyError, IndexError):
        return 0.0

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
best_faas_urls = {}
all_functions = []
edge_fog_hosts_table = []
cloud_host = None
refresh_time = 0
config_lock = Lock()
config_received_event = Event()

@app.route('/faas', methods=['GET', 'POST'])
def server_functionality():
    global best_faas_urls, edge_fog_hosts_table, cloud_host, refresh_time, all_functions

    if request.method == 'GET':
        if not config_received_event.is_set():
            return jsonify({"status": "aguardando", "message": "O servidor ainda nao recebeu uma configuração inicial."}), 503

        function_name = request.args.get('function_name')
        if not function_name:
            return jsonify({"error": "O parametro 'function_name' e obrigatorio."}), 400

        best_url = best_faas_urls.get(function_name)
        if best_url:
            return jsonify({"function_name": function_name, "best_faas_url": best_url})
        else:
            return jsonify({"error": f"Nenhum host disponivel ou a funcao '{function_name}' nao foi encontrada."}), 404

    if request.method == 'POST':
        new_config_content = request.get_data(as_text=True)
        if not new_config_content:
            return jsonify({"error": "Corpo da requisicao esta vazio."}), 400

        try:
            new_refresh, new_table, new_cloud = parse_config(new_config_content)
            with config_lock:
                refresh_time = new_refresh
                edge_fog_hosts_table = new_table
                cloud_host = new_cloud
                all_functions = get_all_function_names(new_table, new_cloud)

            if not config_received_event.is_set():
                config_received_event.set()

            return jsonify({"status": "sucesso", "message": "Configuracao carregada."}), 200

        except Exception as e:
            return jsonify({"error": "Erro ao processar a configuracao.", "details": str(e)}), 500

def run_server(host_url, port):
    app.run(host=host_url, port=port, use_reloader=False)


def start(host_url, port):
    global best_faas_urls
    global edge_fog_hosts_table
    global cloud_host
    global refresh_time
    global config_lock
    global config_received_event
    global all_functions

    server_thread = Thread(target=run_server, args=(host_url, port))
    server_thread.daemon = True
    server_thread.start()

    config_received_event.wait()

    query_cpu = "(1 - avg by (instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[15s]))) * 100"
    query_RAM = "((avg_over_time(node_memory_MemTotal_bytes[15s]) - avg_over_time(node_memory_MemAvailable_bytes[15s]))/ avg_over_time(node_memory_MemTotal_bytes[15s])) * 100"
    
    while True:
        with config_lock:
            current_hosts = edge_fog_hosts_table
            current_cloud = cloud_host
            current_refresh = refresh_time
            current_functions = all_functions

        temp_best_urls = {}
        # Nota: Se tiver muitas funções, a ordem de iteração aqui pode privilegiar 
        # a primeira função a pegar o host 'descansado'.
        for func in current_functions:
            best_url = find_best_faas(current_hosts, current_cloud, query_cpu, query_RAM, func)
            temp_best_urls[func] = best_url
        
        best_faas_urls = temp_best_urls
        
        time.sleep(current_refresh)