from adapt_exec_client import Adaptive_FaaS 
import time
import json 
import pickle 
import cv2 
import base64 

def serialize(imgpath):
    img = cv2.imread(imgpath)
    imgdata = pickle.dumps(img)
    imserial = {'image_data' : base64.b64encode(imgdata).decode('ascii')}
    return imserial

def construct_json(imserial):
    data = {'data' : imserial}
    json_data = json.dumps(data)
    return json_data


ROOT = "/home/rafael/Desktop/quarto_ano/TCC"
SERVER_ADDRESS = "http://127.0.0.1:5000"
IMGPATH = ROOT + '/Dataset/frames/seq_000001.jpg'
    
    # Caminho para o arquivo de configuração YAML
CONFIG_FILE = "./config.yml"

try:
    #inicializa o modulo setando as configurações iniciais
    client = Adaptive_FaaS(server_url=SERVER_ADDRESS, config_file_path=CONFIG_FILE)
    #aqui as configurações são enviadas ao servidor, antes disso o servidor não retorna nada
    if client.send_config():
        print("\nAguardando o servidor processar a configuração...\n")
        # Pequena pausa para o servidor fazer o primeiro ciclo de verificação

        time.sleep(5) 
        imserial = serialize(IMGPATH)
        json_data = construct_json(imserial)

        #aqui é feita a requisição
        #function name
        while True:
            response = client.request(function_name="crowdcount-yolo", data = json_data, json=True, timeout=90)

            if '\n' in response.text.strip():
                print('entrou')
                texto_direita = response.text.strip().split('\n')[-1]
                print(texto_direita)
            else:
                print('nao entrou')
                print(response.text)
        

except ValueError as e:
    print(f"Erro: {e}")