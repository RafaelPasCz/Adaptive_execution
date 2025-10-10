# Trabalho de TCC: Execução adaptativa de funções serverless em dispositivos IoT e servidores
### A proposta desse trabalho é desenvolver uma camada capaz de determinar o local de execução de de uma função *serverless* de forma dinâmica, baseado em métricas de sistema
### O Software Prometheus, com o Node_exporter, é necessário para consultar as métricas de sistema dos diferentes dispositivos hospedeiros das 
### Este módulo foi desenvolvido com o framework *Serverless* de código aberto [OpenFaaS](https://github.com/openfaas), e sua distribuição [FaasD](https://github.com/openfaas/faasd) em mente, no entanto qualquer url de função com a estrutura \<URL>:<PORTA>/function/<NOME DA FUNÇãO> irá funcionar
### Os arquivos [teste_cliente.py](https://github.com/RafaelPasCz/Adaptive_execution/blob/main/teste_cliente.py) e [teste_servidor.py](https://github.com/RafaelPasCz/Adaptive_execution/blob/main/teste_servidor.py) mostram como utilizar, o servidor está configurado para rodar no *localhost*, porem pode funcionar em outro dispositivo

