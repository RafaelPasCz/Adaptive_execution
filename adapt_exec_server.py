import requests
import json
import yaml
import time
from dataclasses import dataclass
from threading import Lock, Event, Thread 
from flask import Flask, request, jsonify

#classe para guardar informações da nuvem
@dataclass
class Cloud_layer:
    __slots__ = ("name", "layer", "faas_url")
    name     : str
    layer    : str
    faas_url : str


    def getfaas_url(self): return self.faas_url

    def getlayer(self)   : return self.layer

    def getname(self)    : return self.name

    def print_slots(self): 
        # função alternativa porque cloud não tem prometheus
        print("-------------------------------------------")
        print(f"name: {self.name}\n",
              f"layer: {self.layer}\n",
              f"faas_url: {self.faas_url}"
              ) 
        print("-------------------------------------------")


#classe para guardar informações de hosts na borda e nevoa
@dataclass
class Host_table_entry:
    __slots__ = ("name", "priority", "layer", "faas_url", "prometheus_api_url",
                 "max_cpu", "max_ram",
                 "cpu_use", "ram_use")


    #nome, camada e url de apis
    name               : str
    priority           : str
    layer              : str
    faas_url           : str
    prometheus_api_url : str
    #maximos definidos na configuração
    max_cpu            : float
    max_ram            : float 
    #atributos que serão atualizados na execução, e comparados com os maximos
    cpu_use            : float
    ram_use            : float


    def print_slots(self): #pra debugar
        print("-------------------------------------------")
        print(f"name: {self.name}\n",
              f"priority: {self.priority}\n",
              f"layer: {self.layer}\n",
              f"faas_url: {self.faas_url}\n",
              f"prometheus_api_url: {self.prometheus_api_url}\n",
              f"max_cpu: {self.max_cpu}\n",
              f"max_ram: {self.max_ram}\n",
              f"cpu_use: {self.cpu_use}\n",
              f"ram_use: {self.ram_use}"
              )
        print("-------------------------------------------")
        
    def getname(self):               return self.name

    def getpriority(self):           return self.priority

    def getlayer(self):              return self.layer

    def getfaas_url(self):           return self.faas_url

    def getprometheus_api_url(self): return self.prometheus_api_url

    def getmax_cpu(self):            return self.max_cpu

    def getmax_ram(self):            return self.max_ram

    def getcpu_use(self):            return self.cpu_use

    def getram_use(self):            return self.ram_use
    


def print_table(entry_list):
    for entry in entry_list:
        entry.print_slots()

# função para processar o arquivo de configuração
def parse_config(yaml_content):
    edge_fog_hosts_table = []


    yml_data = yaml.safe_load(yaml_content)
    
    refresh = yml_data.get('refresh_interval_secs')
    #carrega a seção de hosts da configuração
    hosts_dict = yml_data.get('hosts', {})
    for host, properties in hosts_dict.items():
        #para hosts da borda e névoa, com informações completas
        if (properties.get('layer')) != 'cloud':
            entry = Host_table_entry(
                name=host, 
                priority = properties.get('priority'),
                layer = properties.get('layer'), 
                faas_url = properties.get('faas_url'),
                prometheus_api_url = properties.get('prometheus_api_url'),
                max_cpu = properties.get('max_cpu_use'),
                max_ram = properties.get('max_ram_use'),
                cpu_use = 0,
                ram_use = 0,
            )
            edge_fog_hosts_table.append(entry)
        else:
            #host da nuvem não tem prometheus, então as informações são reduzidas
            cloud_host = Cloud_layer(
                name=host,
                layer=properties.get('layer'),
                faas_url=properties.get('faas_url')    
            )

    sorted_hosts = sorted(edge_fog_hosts_table, key=lambda host: host.getpriority() == 'low')
    return refresh, sorted_hosts, cloud_host


def find_best_faas(edge_fog_hosts_table, cloud_host, query_cpu, query_RAM):

        def is_host_available(host):
            cpu_ok = host.getcpu_use() < host.getmax_cpu()
            ram_ok = host.getram_use() < host.getmax_ram()
            #retorna True imedatamente se encontrar um host com CPU e RAM dentro dos limites
            return cpu_ok and ram_ok



        def update_metrics():
            for host in edge_fog_hosts_table:

                #recupera endereço da api do prometheus
                prometheus_api_url = host.getprometheus_api_url()

                try:

                    cpu_response = requests.get(prometheus_api_url, params={'query': query_cpu},timeout = 5)
                    ram_response = requests.get(prometheus_api_url, params={'query': query_RAM},timeout = 5)
                    #checa por erros de estatus code, caso teve alguma falha ao contatar o host
                    cpu_response.raise_for_status()
                    ram_response.raise_for_status()
                    #desempacota as respostas, e atualiza as informações
                    host.cpu_use = unpack_response(cpu_response)
                    host.ram_use = unpack_response(ram_response)

                except requests.exceptions.RequestException as e:

                    # Define um valor infinito para garantir que o host falho não seja escolhido
                    host.cpu_use = float('inf')
                    host.ram_use = float('inf')

        update_metrics()
        
        #pesquisa nos hosts ordenados
        for host in edge_fog_hosts_table:
            if is_host_available(host):
                #envia o primeiro host apropriado que encontrar
                return host.getfaas_url()
        # se não encontra nenhum host apropriado na borda/nevoa, envia a nuvem    
        return cloud_host.getfaas_url()
 

def unpack_response(response):

    response_content_json=json.loads(response.content)
    #a resposta vem como um json assim
    #{"status":"success","data":{"resultType":"vector","result":[{"metric":{"instance":"localhost:9001"},"value":[1759941647.139,"24.200000000003"]}]}}'

    response_value = float(response_content_json['data']['result'][0]['value'][1])

    return response_value


app = Flask(__name__)

# Variáveis globais
best_faas = ""
edge_fog_hosts_table = []
cloud_host = None
refresh_time = 0 
config_lock = Lock()
# Evento para sinalizar que a configuração foi recebida, para aguardar a configuração ser recebida
config_received_event = Event()
#metodo GET para recuperar o endereço, POST para enviar configuração
@app.route('/faas', methods=['GET', 'POST'])
def server_functionality():
    global best_faas, edge_fog_hosts_table, cloud_host, refresh_time

    if request.method == 'GET':
        # caso a configuração não esteja carregada, avisar que ela deve ser enviada
        if not config_received_event.is_set():
            return jsonify({"status": "aguardando", "message": "O servidor ainda nao recebeu uma configuração inicial."}), 503
        #caso contrario, devolve a melhor URL
        return jsonify({"best_faas_url": best_faas})

    if request.method == 'POST':
        #carrega o conteudo (arquivo de configuração)
        new_config_content = request.get_data(as_text=True)
        if not new_config_content:
            return jsonify({"error": "Corpo da requisicao esta vazio."}), 400
        
        try:
            #faz o parsing do conteúdo, identificando as camadas 
            new_refresh, new_table, new_cloud = parse_config(new_config_content)
            #altera as variáveis globais usando data_lock, pois são compartilhadas
            with config_lock:
                refresh_time = new_refresh
                edge_fog_hosts_table = new_table
                cloud_host = new_cloud
            

            #acionar o evento de configuração, caso ele ja não esteja iniciado
            #o servidor suporta mudanças de configuração enquanto roda, por isso essa seção
            if not config_received_event.is_set():
                config_received_event.set()

            return jsonify({"status": "sucesso", "message": "Configuracao carregada."}), 200

        except Exception as e:
            return jsonify({"error": "Erro ao processar a configuracao.", "details": str(e)}), 500

def run_server(host_url, port):
    app.run(host=host_url, port=port, use_reloader=False)


def start(host_url, port):
    global best_faas
    global edge_fog_hosts_table
    global cloud_host
    global refresh_time
    global config_lock
    global config_received_event

    #inicia o servidor Flask em uma thread separada
    server_thread = Thread(target=run_server, args=(host_url, port))
    server_thread.daemon = True
    server_thread.start()

    #para aguardar a configuração ser recebida
    config_received_event.wait() # A execução vai pausar aqui até o .set() ser chamado.


    #quando a configuração for recebida, a execução principal inicia
    query_cpu = "(1 - avg by (instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[15s]))) * 100" 
    query_RAM = "((avg_over_time(node_memory_MemTotal_bytes[15s]) - avg_over_time(node_memory_MemAvailable_bytes[15s]))/ avg_over_time(node_memory_MemTotal_bytes[15s])) * 100"
    while True:
        with config_lock:
            current_hosts = edge_fog_hosts_table
            current_cloud = cloud_host
            current_refresh = refresh_time
        
        best_faas = find_best_faas(current_hosts, current_cloud, query_cpu, query_RAM)
        
        time.sleep(current_refresh)