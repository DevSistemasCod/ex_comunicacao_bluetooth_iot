import bluetooth
from micropython import const
import time

# Constantes de eventos BLE 
EVENTO_SCAN_RESULTADO            = const(5)
EVENTO_SCAN_COMPLETO             = const(6)
EVENTO_CONEXAO_PERIFERICO        = const(7)
EVENTO_DESCONEXAO_PERIFERICO     = const(8)
EVENTO_SERVICO_ENCONTRADO        = const(9)
EVENTO_CARACTERISTICA_ENCONTRADA = const(11)
EVENTO_ESCRITA_CONCLUIDA         = const(17)
EVENTO_NOTIFICACAO_RECEBIDA      = const(18)

# UUIDs do serviço UART (NUS) e características
UUID_SERVICO_UART = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
UUID_TX_UART      = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")  # Notify (server -> client)
UUID_RX_UART      = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")  # Write  (client -> server)

# Objeto BLE global
bluetooth_central = None

# Dados do dispositivo alvo (servidor)
nome_alvo = b"ESP32_SERVER"
tipo_endereco_alvo = None
endereco_alvo = None

# Dados de conexão e handles
handle_conexao = None
inicio_servico_uart = None
fim_servico_uart = None
handle_caracteristica_tx = None
handle_caracteristica_rx = None

# Flags de estado
esta_conectado = False
servico_uart_encontrado = False
caracteristicas_uart_encontradas = False



# Lê os dados de advertising e tenta extrair o 'Complete Local Name' (código 0x09).
# retorna o nome como bytes ou None se não encontrar.
def decodificar_nome_dispositivo(dados_advertising):
    indice = 0
    tamanho_dados = len(dados_advertising)

    while indice + 1 < tamanho_dados:
        comprimento = dados_advertising[indice]
        if comprimento == 0:
            # Sem mais campos
            break

        tipo_campo = dados_advertising[indice + 1]

        # 0x09 = Complete Local Name
        if tipo_campo == 0x09:
            inicio_nome = indice + 2
            fim_nome = indice + 1 + comprimento
            return dados_advertising[inicio_nome:fim_nome]

        # Avança para o próximo campo
        indice = indice + 1 + comprimento

    return None



# Trata eventos de resultado de scan.
# Verifica se o dispositivo encontrado tem o nome alvo e, se tiver, para o scan e tenta conectar.
def tratar_evento_scan_resultado(dados_evento):
    global tipo_endereco_alvo, endereco_alvo

    tipo_endereco, endereco, tipo_adv, rssi, dados_advertising = dados_evento

    nome_dispositivo = decodificar_nome_dispositivo(dados_advertising)
    if nome_dispositivo is None:
        nome_dispositivo = b""

    if nome_dispositivo == nome_alvo and endereco_alvo is None:
        print("Encontrado dispositivo alvo:", nome_dispositivo, "RSSI:", rssi)

        tipo_endereco_alvo = tipo_endereco
        endereco_alvo = bytes(endereco)

        # Para o scan e inicia a conexão
        bluetooth_central.gap_scan(None)
        print("Iniciando conexão com o servidor...")
        bluetooth_central.gap_connect(tipo_endereco_alvo, endereco_alvo)


# Evento disparado quando a conexão com o servidor BLE é estabelecida.
# Guarda o handle da conexão e inicia a descoberta de serviços.
def tratar_evento_conexao_periferico(dados_evento):
    global handle_conexao, esta_conectado

    handle_conexao_recebido, tipo_endereco, endereco = dados_evento
    handle_conexao = handle_conexao_recebido
    esta_conectado = True

    print("Conectado ao servidor. Handle da conexão:", handle_conexao)

    # Inicia descoberta de serviços deste periférico
    bluetooth_central.gattc_discover_services(handle_conexao)



# Evento disparado quando ocorre uma desconexão do servidor.
def tratar_evento_desconexao_periferico(dados_evento):
    global esta_conectado

    handle_conexao_desconectada, tipo_endereco, endereco = dados_evento
    print("Desconectado do servidor. Handle:", handle_conexao_desconectada)
    esta_conectado = False


# Evento disparado para cada serviço encontrado durante gattc_discover_services.
# Verifica se o serviço é o UART (NUS) que queremos.
def tratar_evento_servico_encontrado(dados_evento):
    global inicio_servico_uart, fim_servico_uart, servico_uart_encontrado

    handle_conexao_evento, start_handle, end_handle, uuid_servico = dados_evento

    if uuid_servico == UUID_SERVICO_UART:
        inicio_servico_uart = start_handle
        fim_servico_uart = end_handle
        servico_uart_encontrado = True
        print("Serviço UART encontrado. Intervalo de handles:", inicio_servico_uart, "-", fim_servico_uart)

        # descobrimos as características dentro do intervalo deste serviço
        bluetooth_central.gattc_discover_characteristics(
            handle_conexao_evento, inicio_servico_uart, fim_servico_uart
        )


# Evento disparado para cada característica encontrada no serviço.
# Se for TX ou RX de UART, guarda os handles.
def tratar_evento_caracteristica_encontrada(dados_evento):
    global handle_caracteristica_tx, handle_caracteristica_rx, caracteristicas_uart_encontradas

    handle_conexao_evento, def_handle, valor_handle, propriedades, uuid_caracteristica = dados_evento

    if uuid_caracteristica == UUID_TX_UART:
        handle_caracteristica_tx = valor_handle
        print("Característica TX (notify) encontrada. Handle:", handle_caracteristica_tx)

    if uuid_caracteristica == UUID_RX_UART:
        handle_caracteristica_rx = valor_handle
        print("Característica RX (write) encontrada. Handle:", handle_caracteristica_rx)

    if handle_caracteristica_tx is not None and handle_caracteristica_rx is not None:
        caracteristicas_uart_encontradas = True
        print("Ambas características UART (TX e RX) foram encontradas.")
        # Após encontrarmos as duas, habilitamos notificações
        habilitar_notificacoes_uart()


# Evento disparado quando uma escrita GATTC foi concluída.
# Apenas mostramos no console por fins didáticos.
def tratar_evento_escrita_concluida(dados_evento):
    handle_conexao_evento, valor_handle, status = dados_evento
    print("Escrita concluída no handle", valor_handle, "Status:", status)


# Evento disparado quando o servidor envia uma notificação (notify) em TX.
# Mostra os dados recebidos.
def tratar_evento_notificacao(dados_evento):
    handle_conexao_evento, valor_handle, dados = dados_evento
    print("Notificação recebida do servidor. Handle:", valor_handle, "Dados:", dados)



# Função central de tratamento de eventos BLE.
# recebe os eventos e encaminha para a funcionalidade específica.
def ble_irq(evento, dados_evento):
    if evento == EVENTO_SCAN_RESULTADO:
        tratar_evento_scan_resultado(dados_evento)

    elif evento == EVENTO_SCAN_COMPLETO:
        print("Scan completo.")

    elif evento == EVENTO_CONEXAO_PERIFERICO:
        tratar_evento_conexao_periferico(dados_evento)

    elif evento == EVENTO_DESCONEXAO_PERIFERICO:
        tratar_evento_desconexao_periferico(dados_evento)

    elif evento == EVENTO_SERVICO_ENCONTRADO:
        tratar_evento_servico_encontrado(dados_evento)

    elif evento == EVENTO_CARACTERISTICA_ENCONTRADA:
        tratar_evento_caracteristica_encontrada(dados_evento)

    elif evento == EVENTO_ESCRITA_CONCLUIDA:
        tratar_evento_escrita_concluida(dados_evento)

    elif evento == EVENTO_NOTIFICACAO_RECEBIDA:
        tratar_evento_notificacao(dados_evento)

    else:
        # Para fins didáticos, mostramos se surgir algum evento não tratado.
        print("Evento BLE não tratado. Código:", evento, "Dados:", dados_evento)



# Inicializa o módulo BLE em modo central (cliente).
def inicializar_bluetooth():
    global bluetooth_central

    bluetooth_central = bluetooth.BLE()
    bluetooth_central.active(True)
    bluetooth_central.irq(ble_irq)
    print("Módulo BLE inicializado como CENTRAL (cliente).")



# Inicia o processo de scan para encontrar o dispositivo alvo pelo nome.
def iniciar_scan():
    intervalo_ms = 30000  # tempo total de scan em ms
    janela_ms = 30000     # janela de scan em ms
    print("Iniciando scan em busca do dispositivo com nome:", nome_alvo)
    bluetooth_central.gap_scan(intervalo_ms, 30000, 30000)



# Habilita notificações na característica TX do serviço UART.
# Isso é feito escrevendo no descritor CCCD (handle da TX + 1).
def habilitar_notificacoes_uart():
    if handle_conexao is None:
        print("Não há conexão ativa. Não é possível habilitar notificações.")
        return

    if handle_caracteristica_tx is None:
        print("Handle da característica TX é None. Não é possível habilitar notificações.")
        return

    # Normalmente, o descritor CCCD fica em handle_caracteristica_tx + 1
    handle_descritor_cccd = handle_caracteristica_tx + 1

    # Valor b'\x01\x00' = habilitar notificações
    valor_notificacao_ativada = b"\x01\x00"

    print("Habilitando notificações no descritor (CCCD) handle:", handle_descritor_cccd)
    bluetooth_central.gattc_write(handle_conexao, handle_descritor_cccd, valor_notificacao_ativada, 1)


# Envia uma mensagem de bytes para o servidor usando a característica RX.
def enviar_mensagem_uart(mensagem_bytes):
    if handle_conexao is None:
        print("Não há conexão ativa. Não é possível enviar mensagem.")
        return

    if handle_caracteristica_rx is None:
        print("Handle da característica RX é None. Não é possível enviar mensagem.")
        return

    print("Enviando mensagem ao servidor:", mensagem_bytes)
    bluetooth_central.gattc_write(handle_conexao, handle_caracteristica_rx, mensagem_bytes, 0)



# Laço principal que alterna comandos LED=1 e LED=0 para o servidor,
# esperando alguns segundos entre cada envio.
def ciclo_principal_envio_comandos():
    estado_led = 0

    while True:
        if estado_led == 0:
            enviar_mensagem_uart(b"LED=1")
            estado_led = 1
        else:
            enviar_mensagem_uart(b"LED=0")
            estado_led = 0

        time.sleep(3)


    
# Aguarda até que a conexão seja estabelecida e as características UART sejam encontradas,
# ou até atingir o timeout fornecido.
def aguardar_conexao_e_caracteristicas(timeout_segundos=30):
    tempo_decorrido = 0
    while tempo_decorrido < timeout_segundos:
        if esta_conectado and caracteristicas_uart_encontradas:
            print("Conexão estabelecida e características UART prontas para uso.")
            return True

        time.sleep(1)
        tempo_decorrido = tempo_decorrido + 1

    print("Timeout ao aguardar conexão ou descoberta de características.")
    return False


# Função que coordena todo o fluxo do cliente BLE UART:
def executar_cliente_uart():
    inicializar_bluetooth()
    iniciar_scan()

    pronto_para_usar = aguardar_conexao_e_caracteristicas(timeout_segundos=30)

    if pronto_para_usar:
        ciclo_principal_envio_comandos()
    else:
        print("Não foi possível preparar a comunicação UART BLE. Encerrando cliente.")



executar_cliente_uart()
