from adapt_exec_client import Adaptive_FaaS
import time

adapt = Adaptive_FaaS(server_url = 'http://127.0.0.1:5000/faas',config_file_path = './config.yml')
adapt.send_config()

for i in range(10): 
    best_url = adapt.request()
    print(best_url)
    time.sleep(10)
