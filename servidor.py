import bluetooth
from machine import Pin
from micropython import const
import json
import time

_EVENTO_CONECTADO = const(1)
_EVENTO_DESCONECTADO = const(2)
_EVENTO_ESCRITA = const(3)

UUID_SERVICO = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
UUID_CARACTERISTICA = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")


#Flags de configuração da característica BLE:
# documentação https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-54/out/en/host/generic-attribute-profile--gatt-.html
# veja a tabela em  3.3.1.1. Characteristic Properties
FLAG_LEITURA = const(0x0002)
FLAG_ESCRITA = const(0x0008)
FLAG_NOTIFICACAO = const(0x0010)

conexoes = set()
ble_global = None
handle_caracteristica = None
led_interno = None
nome_dispositivo_ble = "ESP32-B-LED"


def iniciar_led():
    global led_interno
    led_interno = Pin(2, Pin.OUT)


def ligar_led(valor):
    if valor:
        led_interno.value(1)
    else:
        led_interno.value(0)


def registrar_servicos():
    global ble_global
    global handle_caracteristica
    # Cria uma tupla que define a característica BLE: 
    # - UUID da característica 
    # - Permissões combinadas com OR (leitura, escrita e notificação)
    caracteristica = (
        UUID_CARACTERISTICA,
        FLAG_LEITURA | FLAG_ESCRITA | FLAG_NOTIFICACAO
    )
    
    # Cria uma tupla representando o serviço BLE contendo a característica acima
    servico = (
        UUID_SERVICO,
        (caracteristica,)
    )
    
    # Registra o serviço no stack BLE do ESP32 e recebe 
    # os "handles" criados
    handles = ble_global.gatts_register_services((servico,))
    
    # Guarda o handle da característica para 
    #leitura/escrita/notificação posterior
    handle_caracteristica = handles[0][0]


def montar_payload_advertising():
    # Converte o nome do dispositivo BLE para bytes
    nome_bytes = nome_dispositivo_ble.encode("utf-8")
    
    # Campo de Advertising do tipo "Complete Local Name" 
    # documentação https://docs.silabs.com/bluetooth/6.2.0/bluetooth-fundamentals-advertising-scanning/advertising-data-basics
    campo_nome = bytes((len(nome_bytes) + 1, 0x09)) + nome_bytes
    try:
        uuid_bytes = UUID_SERVICO.uuid
    except:
        uuid_bytes = bytes(UUID_SERVICO)
    # Campo de Advertising do tipo "Complete List of 128-bit UUIDs"
    # documentação https://community.silabs.com/s/article/kba-bt-0201-bluetooth-advertising-data-basics?language=en_US
    campo_uuid = bytes((len(uuid_bytes) + 1, 0x07)) + uuid_bytes

    # # Retorna os dois campos concatenados para enviar no advertising BLE
    return campo_nome + campo_uuid


def iniciar_advertising():
    global ble_global
    payload = montar_payload_advertising()
    # - 500000 define o intervalo (em microssegundos) entre anúncios 
    # - adv_data envia os dados criados para o advertising
    ble_global.gap_advertise(500000, adv_data=payload)


def enviar_resposta_ble(obj_resposta):
    global ble_global
    global conexoes
    global handle_caracteristica

    # Converte o dicionário Python para JSON em texto 
    # e depois para bytes para poder enviar via BLE 
    resposta = json.dumps(obj_resposta).encode("utf-8")
    
    # Grava a resposta internamente na characteristic do servidor GATT
    ble_global.gatts_write(handle_caracteristica, resposta)

    # Para cada conexão ativa registrada, 
    # envia uma notificação BLE com a mesma resposta
    for conexao in conexoes:
        ble_global.gatts_notify(conexao, handle_caracteristica, resposta)


def interpretar_json_e_controlar_led(texto_json):
    try:
        # Converte o texto recebido via BLE de JSON para um objeto Python (dicionário)
        objeto = json.loads(texto_json)
    except:
        enviar_resposta_ble({"status": "ERROR", "detail": "JSON inválido"})
        return

    # Verifica se o JSON possui o campo "led"
    if "led" in objeto:
        valor_led = objeto["led"]
        # O campo "led" precisa ser um valor booleano True/False
        if isinstance(valor_led, bool):
            ligar_led(valor_led)
            # Envia uma confirmação de sucesso de volta ao cliente
            enviar_resposta_ble({"status": "OK", "led": valor_led})
        else:
            # Se o campo existir mas não for booleano, envia erro
            enviar_resposta_ble({"status": "ERROR", "detail": "Campo led inválido"})
    else:
        # Se o campo "led" não existir no JSON, envia erro
        enviar_resposta_ble({"status": "ERROR", "detail": "Campo led ausente"})


def tratar_evento_conectado(dados):
    # O evento BLE passa uma tupla com informações da conexão.
    conexao, _, _ = dados
    # Adiciona o ID da conexão ao conjunto de conexões ativas
    conexoes.add(conexao)


def tratar_evento_desconectado(dados):
    # O evento de desconexão também recebe uma tupla.
    # O primeiro elemento é o ID da conexão que acabou de desconectar.
    conexao, _, _ = dados
    
    # Se essa conexão estava registrada como ativa, removemos do conjunto
    if conexao in conexoes:
        conexoes.remove(conexao)
    iniciar_advertising()


def tratar_evento_escrita(dados):
    global ble_global
    global handle_caracteristica
    
    # O evento de escrita passa: (ID da conexão, handle da característica)
    conexao, handle = dados

    # Verifica se a escrita foi na característica que estamos monitorando
    if handle == handle_caracteristica:
        # Lê os dados brutos escritos pelo cliente BLE
        bruto = ble_global.gatts_read(handle_caracteristica)
        try:
            # Converte os bytes recebidos em texto UTF-8
            texto = bruto.decode("utf-8")
        except:
            return
        # Interpreta o JSON recebido e executa a ação (ligar/desligar LED)  
        interpretar_json_e_controlar_led(texto)


def callback_eventos_ble(evento, dados):
    # Função callback registrada no BLE para tratar eventos de conexão,
    # desconexão e escrita em características.
    # O Bluetooth chama automaticamente essa função sempre que 
    # algo relevante ocorre.

    # Se o evento indica uma conexão BLE bem-sucedida:
    if evento == _EVENTO_CONECTADO:
        tratar_evento_conectado(dados)
    
    else:
        # Se o evento indica que um cliente desconectou:
        if evento == _EVENTO_DESCONECTADO:
            tratar_evento_desconectado(dados)
        else:
            # Se um cliente escreveu dados na characteristic:
            if evento == _EVENTO_ESCRITA:
                tratar_evento_escrita(dados)


def iniciar_ble():
    global ble_global
    ble_global = bluetooth.BLE()
    ble_global.active(True)
    ble_global.irq(callback_eventos_ble)


def configurar_servidor_ble():
    iniciar_led()
    registrar_servicos()
    iniciar_advertising()


def executar_loop_servidor():
    try:
        while True:
            time.sleep(1) # Evita uso desnecessário de CPU
            # com esse sleep, o loop só acorda de vez em quando para permitir 
            # que o Python siga rodando, mas sem ocupar o processador 
            # o tempo inteiro.
            # aqui o sleep() reduz o consumo de energia
    except KeyboardInterrupt:
        # Caso o usuário interrompa manualmente (CTRL+C),
        # interrompe a publicidade BLE e desativa a interface
        ble_global.gap_advertise(None)
        ble_global.active(False)


def main():
    iniciar_ble()
    configurar_servidor_ble()
    executar_loop_servidor()


if __name__ == "__main__":
    main()