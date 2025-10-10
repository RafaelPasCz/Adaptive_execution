from adapt_exec_client import Adaptive_FaaS    # URL do servidor de adaptação (onde o 'adapt_exec_server.py' está rodando)


SERVER_ADDRESS = "http://127.0.0.1:5000"
    
    # Caminho para o arquivo de configuração YAML
CONFIG_FILE = "config.yml"

try:
        # 1. Inicializa o cliente com as informações necessárias
    client = Adaptive_FaaS(server_url=SERVER_ADDRESS, config_file_path=CONFIG_FILE)

        # 2. Envia a configuração para o servidor (geralmente feito apenas uma vez no início)
    if client.send_config():
        print("\nAguardando o servidor processar a configuração...\n")
        # Pequena pausa para o servidor fazer o primeiro ciclo de verificação
        import time
        time.sleep(5) 

        # 3. Solicita a melhor URL para uma função específica (ex: 'function_name')
        print("Requisitando a melhor URL para a função: 'function_name'")
        best_url = client.request(function_name="function_name",data = 0)

        if best_url:
            print(f"\n[SUCESSO] URL recebida: {best_url}")
                # Aqui você usaria a 'best_url' para invocar sua função FaaS
                # Exemplo: requests.post(best_url, data={'key': 'value'})
        else:
            print("\n[FALHA] Não foi possível obter uma URL para a função.")

except ValueError as e:
    print(f"Erro na inicialização: {e}")