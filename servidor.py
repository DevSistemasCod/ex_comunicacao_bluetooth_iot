import bluetooth
from machine import Pin
from micropython import const
import time

# Constantes de eventos BLE
EVENTO_CENTRAL_CONECTOU = const(1)
EVENTO_CENTRAL_DESCONECTOU = const(2)
EVENTO_CENTRAL_ESCREVEU = const(3)

# Configuração do LED interno
LED = Pin(2, Pin.OUT)

# UUIDs do serviço UART
UUID_SERVICO_UART = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
UUID_TX = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")  # Notificação
UUID_RX = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")  # Escrita

# Variáveis globais para BLE
ble = None
conexao_atual = None
handle_tx = None
handle_rx = None

# Função para tratar comandos recebidos do central
def tratar_comando_recebido(conexao, handle_valor):
    global handle_rx

    # Verifica se o handle recebido é o RX esperado
    if handle_valor != handle_rx:
        return

    try:
        dados_recebidos = ble.gatts_read(handle_rx)
        if not dados_recebidos:
            return
        texto_recebido = dados_recebidos.decode().strip()
    except Exception as erro:
        print("Erro ao ler dados:", erro)
        return

    print("Comando recebido do central:", texto_recebido)

    # Processa o comando recebido
    if texto_recebido == "LED=1":
        LED.value(1)
        resposta = "OK LED LIGADO"
    elif texto_recebido == "LED=0":
        LED.value(0)
        resposta = "OK LED DESLIGADO"
    else:
        resposta = "ERRO COMANDO"

    # Envia resposta ao central
    try:
        ble.gatts_notify(conexao, handle_tx, resposta.encode('utf-8'))  # converte resposta em bytes
        print("Resposta enviada ao central:", resposta)
    except Exception as erro:
        print("Erro ao notificar central:", erro)

# Callback de eventos BLE
def eventos_ble(evento, dados):
    global conexao_atual

    if evento == EVENTO_CENTRAL_CONECTOU:
        conexao_atual, tipo_endereco, endereco = dados
        print("Central conectou! Handle da conexão:", conexao_atual)

    elif evento == EVENTO_CENTRAL_DESCONECTOU:
        conexao, tipo_endereco, endereco = dados
        print("Central desconectou. Handle da conexão:", conexao)
        conexao_atual = None
        iniciar_advertising()

    elif evento == EVENTO_CENTRAL_ESCREVEU:
        conexao, handle_valor = dados
        tratar_comando_recebido(conexao, handle_valor)

# Função para iniciar advertising BLE
def iniciar_advertising():
    nome_str = "ESP32_SERVER"
    nome_dispositivo = nome_str.encode('utf-8')  # converte string em bytes

    payload_advertising = bytearray()
    
    # Flags de advertising
    payload_advertising.extend(bytes((2, 1, 6)))  # mesma coisa que b"\x02\x01\x06"
    # Nome completo do dispositivo
    payload_advertising.extend(bytes((len(nome_dispositivo) + 1, 0x09)))
    payload_advertising.extend(nome_dispositivo)

    print("Iniciando advertising BLE...")
    ble.gap_advertise(100, payload_advertising)

# Função para inicializar BLE e serviço UART
def iniciar_ble():
    global ble, handle_tx, handle_rx

    ble = bluetooth.BLE()
    ble.active(True)
    ble.irq(eventos_ble)

    # Define serviço UART
    servico_uart = (
        UUID_SERVICO_UART,
        (
            (UUID_TX, bluetooth.FLAG_NOTIFY),
            (UUID_RX, bluetooth.FLAG_WRITE),
        ),
    )

    # Registra o serviço e obtém os handles
    ((handle_tx, handle_rx),) = ble.gatts_register_services((servico_uart,))
    print("Serviço UART registrado. TX handle:", handle_tx, "RX handle:", handle_rx)

    iniciar_advertising()


def main():
    iniciar_ble()
    while True:
        # Mantém o programa rodando
        time.sleep(1)


main()
