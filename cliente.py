import bluetooth
from micropython import const
import time
import json

EVENTO_SCAN_RESULTADO = const(5)
EVENTO_SCAN_FINALIZADO = const(6)
EVENTO_CONECTADO = const(7)
EVENTO_DESCONECTADO = const(8)
EVENTO_SERVICO_ENCONTRADO = const(9)
EVENTO_SERVICO_CONCLUIDO = const(10)
EVENTO_CARACTERISTICA_ENCONTRADA = const(11)
EVENTO_CARACTERISTICA_CONCLUIDA = const(12)
EVENTO_NOTIFICACAO = const(18)

UUID_SERVICO = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
UUID_CARACTERISTICA = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")

NOME_ALVO = "ESP32-B-LED"

ble_global = None
tipo_endereco = None
endereco = None
handle_conexao = None
inicio_handle = None
fim_handle = None
handle_caracteristica = None

servico_encontrado = False
caracteristica_encontrada = False
scan_finalizado = False
conectado = False
servicos_concluidos = False
caracteristicas_concluidas = False

# Restaura todas as variáveis de controle para garantir
# que uma nova tentativa de conexão BLE comece do zero.
def resetar_estado():
    global tipo_endereco
    global endereco
    global handle_conexao
    global inicio_handle
    global fim_handle
    global handle_caracteristica
    global servico_encontrado
    global caracteristica_encontrada
    global scan_finalizado
    global conectado
    global servicos_concluidos
    global caracteristicas_concluidas

    # Reset das variáveis para estado inicial
    tipo_endereco = None
    endereco = None
    handle_conexao = None
    inicio_handle = None
    fim_handle = None
    handle_caracteristica = None
    servico_encontrado = False
    caracteristica_encontrada = False
    scan_finalizado = False
    conectado = False
    servicos_concluidos = False
    caracteristicas_concluidas = False


# Função auxiliar que percorre os bytes de advertising recebidos
# para tentar extrair o nome do dispositivo BLE.
# Usado durante o scan para identificar dispositivos pelo nome.
def extrair_nome(dados_adv):
    try:
        dados = bytes(dados_adv)
    except:
        dados = dados_adv

    i = 0
    nome = None

    # Cada estrutura de advertising é formada por: 
    # [tamanho][tipo][dados...]
    while i + 1 < len(dados):
        tamanho = dados[i]
        # Se o tamanho for zero, não há mais dados
        if tamanho == 0:
            break

        tipo = dados[i + 1]
        # 0x08 ou 0x09 → nome curto ou nome completo do dispositivo
        if tipo == 0x08 or tipo == 0x09:
            try:
                nome = dados[i + 2 : i + 1 + tamanho].decode("utf-8")
            except:
                nome = None
        
        # Avança para o próximo campo
        i = i + 1 + tamanho

    return nome

# Função callback que trata todos os eventos enviados
# pelo stack Bluetooth do ESP32 no modo cliente (gattc).
def evento_ble(evento, dados):
    global tipo_endereco
    global endereco
    global handle_conexao
    global inicio_handle
    global fim_handle
    global handle_caracteristica
    global servico_encontrado
    global caracteristica_encontrada
    global scan_finalizado
    global conectado
    global servicos_concluidos
    global caracteristicas_concluidas

    # Evento recebido quando um dispositivo BLE é detectado durante o scan
    if evento == EVENTO_SCAN_RESULTADO:
        t, a, adv_tipo, rssi, adv = dados
        nome = extrair_nome(adv)
        # Se o nome for o dispositivo desejado:
        if nome == NOME_ALVO:
            tipo_endereco = t
            endereco = bytes(a)
            # Para o scan imediatamente e sinaliza sucesso
            ble_global.gap_scan(None)
            scan_finalizado = True

    # Sinaliza que terminou o scan mesmo que nada tenha sido encontrado
    elif evento == EVENTO_SCAN_FINALIZADO:
        scan_finalizado = True

    # Quando a conexão GATT se estabelece com sucesso
    elif evento == EVENTO_CONECTADO:
        conn, t, a = dados
        handle_conexao = conn
        conectado = True
        # Inicia descoberta de serviços do servidor remoto
        ble_global.gattc_discover_services(handle_conexao)

    # Quando o dispositivo remoto desconecta
    elif evento == EVENTO_DESCONECTADO:
        conn, t, a = dados
        conectado = False
        handle_conexao = None

    # Serviço encontrado durante a fase de descoberta GATT
    elif evento == EVENTO_SERVICO_ENCONTRADO:
        conn, inicio, fim, uuid = dados
        
        # Se o serviço é o que procuramos (Nordic UART Service)
        if conn == handle_conexao and uuid == UUID_SERVICO:
            inicio_handle = inicio
            fim_handle = fim
            servico_encontrado = True

    # Quando termina a busca pelos serviços
    elif evento == EVENTO_SERVICO_CONCLUIDO:
        servicos_concluidos = True
        
        # Se o serviço correto foi achado, iniciamos busca pelas characteristics
        if servico_encontrado:
            ble_global.gattc_discover_characteristics(
                handle_conexao, inicio_handle, fim_handle
            )

    # Characteristic encontrada
    elif evento == EVENTO_CARACTERISTICA_ENCONTRADA:
        conn, def_h, val_h, props, uuid = dados
        if conn == handle_conexao and uuid == UUID_CARACTERISTICA:
            handle_caracteristica = val_h
            caracteristica_encontrada = True

    # Finalização do processo de busca de characteristics
    elif evento == EVENTO_CARACTERISTICA_CONCLUIDA:
        caracteristicas_concluidas = True

    # Notificação recebida do servidor BLE (callback assíncrono)
    elif evento == EVENTO_NOTIFICACAO:
        conn, val_h, dados_not = dados
        if conn == handle_conexao and val_h == handle_caracteristica:
            try:
                msg = dados_not.decode("utf-8")
            except:
                msg = str(dados_not)
            print("Notificação recebida:", msg)


def iniciar_ble():
    global ble_global
    ble_global = bluetooth.BLE()
    ble_global.active(True)
    ble_global.irq(evento_ble)


def procurar_e_conectar(tempo_ms=10000):
    resetar_estado()
    # Inicia o scan por 'tempo_ms' milissegundos
    ble_global.gap_scan(tempo_ms, 30000, 30000)

    # Aguarda o scan terminar
    instante_inicial = time.ticks_ms()
    while not scan_finalizado and time.ticks_diff(time.ticks_ms(), instante_inicial) < tempo_ms + 2000:
        time.sleep_ms(100)

    # Se nenhum dispositivo alvo foi encontrado
    if endereco is None:
        return False

    try:# Tenta conectar
        ble_global.gap_connect(tipo_endereco, endereco)
    except:
        return False

    # Aguarda conexão
    instante_inicial = time.ticks_ms()
    while not conectado and time.ticks_diff(time.ticks_ms(), instante_inicial) < 10000:
        time.sleep_ms(100)

    if not conectado:
        return False

    # Aguarda descoberta de serviços
    instante_inicial = time.ticks_ms()
    while not servicos_concluidos and time.ticks_diff(time.ticks_ms(), instante_inicial) < 10000:
        time.sleep_ms(100)

    if not servico_encontrado:
        return False

    # Aguarda descoberta de characteristics
    instante_inicial = time.ticks_ms()
    while not caracteristicas_concluidas and time.ticks_diff(time.ticks_ms(), instante_inicial) < 10000:
        time.sleep_ms(100)

    if not caracteristica_encontrada:
        return False

    return True


# Envia ao servidor BLE um JSON {"led": true/false}
# usando escrita GATT na characteristic descoberta.
def enviar_comando_led(valor):
    if not conectado:
        return False

    if handle_caracteristica is None:
        return False
    
    # Monta o JSON {"led": true/false}
    objeto = {"led": bool(valor)}
    dados = json.dumps(objeto)

    try:
        # Escreve na characteristic usando modo WRITE WITH RESPONSE (1)
        ble_global.gattc_write(
            handle_conexao,
            handle_caracteristica,
            dados.encode("utf-8"),
            1
        )
        return True
    except:
        return False


# Alterna o LED remoto entre ligado/desligado continuamente,
# enviando um novo comando a cada 5 segundos,
# até que a comunicação falhe.
def executar_loop_led():
    estado = False
    while True:
        estado = not estado # Alterna estado
        sucesso = enviar_comando_led(estado)
        
        # Se falhou (ex: desconexão), sai do loop
        if not sucesso:
            break
        time.sleep(5)


def main():
    iniciar_ble()
    ok = procurar_e_conectar()

    if ok:
        executar_loop_led()


if __name__ == "__main__":
    main()