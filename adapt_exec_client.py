import requests
import json

class Adaptive_FaaS():
    server_url : str
    config_file_path : str
    initialized : bool = False

    def __init__(self, server_url, config_file_path):
            
        if not server_url: #se não tiver url de servidor
            print("Erro: url do servidor não definida\n", 
                  "uso: Adaptive_FaaS(<url do hospedeiro>, <caminho do arquivo de configuração>)")
            raise ValueError("A URL do servidor não pode ser nula.")
            
        if not config_file_path:   
            print("Erro: caminho do arquivo de configuração não definido\n", 
                  "uso: Adaptive_FaaS(<url do hospedeiro>, <caminho do arquivo de configuração>)")
            raise ValueError("O caminho do arquivo de configuração não pode ser nulo.")

        # Define os valores passados na inicialização
        self.server_url = server_url
        self.config_file_path = config_file_path
        self.initialized = True
    
    def send_config(self):
        """
        Lê o arquivo de configuração e o envia para o servidor via POST.
        Retorna True em caso de sucesso, False em caso de falha.
        """
        if not self.initialized:
            print("[ERRO] A classe Adaptive_FaaS não foi inicializada corretamente.")
            return False
                     
        headers = { 'Content-Type' :'text/plain' }

        try:
            with open(self.config_file_path, 'r') as file: 
                config = file.read()

            # Garante que a URL base para POST e GET seja a mesma
            post_url = f"{self.server_url}/faas" if not self.server_url.endswith('/faas') else self.server_url
            response = requests.post(post_url, data=config, headers=headers, timeout=5)
            response.raise_for_status() # Lança uma exceção para status de erro (4xx ou 5xx)
        
        except FileNotFoundError:
            print(f"\n[ERRO] O arquivo de configuração '{self.config_file_path}' não foi encontrado.")
            return False
        except requests.exceptions.RequestException as e:
            print(f"\n[ERRO] Falha ao conectar com o servidor: {e}")
            return False
        except Exception as e:
            print(f"\n[ERRO] Ocorreu um erro inesperado: {e}")
            return False
        
        print("[INFO] Configuração enviada com sucesso para o servidor.")
        return True
        
    def get_server_url(self): 
        return self.server_url

    def get_config_file_path(self): 
        return self.config_file_path

    def request(self, function_name, data):
    
    #   Solicita ao servidor a melhor URL de FaaS para a função especificada pelo cliente.
    #   Retorna a URL em caso de sucesso, ou None em caso de erro.
        
        if not self.initialized:
            print("Erro: Modulo não inicializado, use Adaptive_FaaS(<url do hospedeiro>, <caminho do arquivo de configuração>) para inicializar)\n", 
                  "e em seguida, send_config() para enviar a configuração para o hospedeiro")
            return None

        if not function_name:
            print("[ERRO] O nome da função (function_name) é obrigatório.")
            return None

        try:
            # Constrói a URL para a requisição GET, adicionando o nome da função requisitada
            get_url = f"{self.server_url}/faas" if not self.server_url.endswith('/faas') else self.server_url
            
            response = requests.get(get_url, params={'function_name' : function_name}, timeout=5)
            response.raise_for_status() # Verifica se houve erros na requisição

            response_json = response.json()
            best_faas = response_json.get("best_faas_url")
            return best_faas #temporário, até a lógica da requisição estiver pronta

        except requests.exceptions.HTTPError as e:
            # Erros específicos da resposta do servidor (como 404 - Not Found)
            print(f"\n[ERRO] O servidor retornou um erro: {e.response.status_code} {e.response.reason}")
            print(f"   Detalhes: {e.response.text}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"\n[ERRO] Falha ao consultar o servidor: {e}")
            return None
        except json.JSONDecodeError:
            print("\n[ERRO] Falha ao decodificar a resposta JSON do servidor.")
            return None
        except Exception as e:
            print(f"\n[ERRO] Um erro inesperado ocorreu durante a requisição: {e}")
            return None
        
        params = {'data' : data}
        requests.get(best_faas,params=params)
        #lógica com data
