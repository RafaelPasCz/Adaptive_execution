from adapt_exec_client import Adaptive_FaaS 
import time

SERVER_ADDRESS = "http://127.0.0.1:5000"
    
    # Caminho para o arquivo de configuração YAML
CONFIG_FILE = "config.yml"

try:
    #inicializa o modulo setando as configurações iniciais
    client = Adaptive_FaaS(server_url=SERVER_ADDRESS, config_file_path=CONFIG_FILE)
    #aqui as configurações são enviadas ao servidor, antes disso o servidor não retorna nada
    if client.send_config():
        print("\nAguardando o servidor processar a configuração...\n")
        # Pequena pausa para o servidor fazer o primeiro ciclo de verificação

        time.sleep(5) 

        texto = "teste"
        #aqui é feita a requisição
        #function name
        response = client.request(function_name="figlet", data = texto, text=True, timeout=5)
        print(response.text)

except ValueError as e:
    print(f"Erro: {e}")