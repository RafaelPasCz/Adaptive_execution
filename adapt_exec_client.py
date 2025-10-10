import requests
import json

class Adaptive_FaaS():
    server_url : str
    config_file_path : str
    initialized : bool = False

    def __init__(self, server_url, config_file_path):
            
        if server_url == None:
            print("Erro: url do servidor não definida\n", 
                  "uso: Adaptive_FaaS.initialize(<url do hospedeiro>,<caminho do arquivo de configuração>)")
            return None
            
        if config_file_path == None:   
            print("Erro: caminho do arquivo de configuração não definido\n", 
                  "uso: Adaptive_FaaS.initialize(<url do hospedeiro>,<caminho do arquivo de configuração>)")
            return None

        #define os valores passados na inicialização
        self.server_url = server_url
        self.config_file_path = config_file_path
        self.initialized = True
        return None
    
    def send_config(self):
        if self.server_url == None:
            print("Erro: url do servidor não definida\n", 
                  "uso: Adaptive_FaaS.initialize(<url do hospedeiro>,<caminho do arquivo de configuração>)")
            return False
            
        if self.config_file_path == None:   
            print("Erro: caminho do arquivo de configuração não definido\n", 
                  "uso: Adaptive_FaaS.initialize(<url do hospedeiro>,<caminho do arquivo de configuração>)")
            return False
                     
        headers = { 'Content-Type' :'text/plain' }

        try:
            with open(self.config_file_path, 'r') as file: 
                config = file.read()

            response = requests.post(self.server_url, data=config, headers=headers, timeout=5)
            response.raise_for_status()
        
        except FileNotFoundError:
            print(f"\n[ERRO] O arquivo de configuração '{self.config_file_path}' não foi encontrado.")
            return False
        except requests.exceptions.RequestException as e:
            print(f"\n[ERRO] Falha ao conectar com o servidor: {e}")
            return False
        except Exception as e:
            print(f"\n[ERRO] Ocorreu um erro inesperado: {e}")
            return False
        
        if response.status_code == 200:
            return True
        
        else:
            print("Erro desconhecido")
            return False
        
    def getserver_url(self): return self.server_url

    def get_config_file_path(self): return self.config_file_path

    def request(self):

        def consult():
            response = requests.get(self.server_url)
            response_json = json.loads(response.content)
            return response_json["best_faas_url"]        
            
        if not self.initialized:
            print("Erro: Modulo não inicializado, use intialize(<url do hospedeiro>,<caminho do arquivo de configuração>) para inicializar)\n", 
            "em seguida, send_config() para enviar a configuração para o hospedeiro")
        
        best_url = consult()
        return best_url

