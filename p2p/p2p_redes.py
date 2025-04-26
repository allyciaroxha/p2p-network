import socket
import threading
import time
import pickle
import os

encerrarPrograma = False

#nó da rede
class Node:
    def __init__(self, node_id, node_address):
        self.node_id = node_id
        self.node_address = node_address
        self.data = {}
        self.lista_nodes = []
        self.multicast_group = '224.1.1.1'
        self.multicast_port = 9876
        self.discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.discovery_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(self.multicast_group) + socket.inet_aton('0.0.0.0'))
        self.discovery_socket.bind(('', self.multicast_port))
        #armazenar arquivos
        self.private_directory = os.path.join(os.getcwd(), 'private_data')
        if not os.path.exists(self.private_directory):
            os.makedirs(self.private_directory)
		
    #envia mensagens de descoberta
    def _send_discovery_message(self):
        # Send discovery message to the multicast group
        known_nodes = ",".join([f"{node_id}:{ip}" for node_id, ip in self.lista_nodes])
        while encerrarPrograma == False:
            message = f"DISCOVER|{self.node_id}|{known_nodes}"
            self.discovery_socket.sendto(message.encode(), (self.multicast_group, self.multicast_port))
            time.sleep(2)

    #escuta mensagens de descoberta e atualiza a lista de peers
    def _listen_for_discovery(self):
        while encerrarPrograma == False:
            data, addr = self.discovery_socket.recvfrom(1024)
            message = data.decode()
            discovery_node_id = message.split("|")[1]
            discovered_node = PrimitiveNode(discovery_node_id, addr[0])
            if message.startswith("DISCOVER") and message.split("|")[1] != self.node_id and discovered_node not in self.lista_nodes:
               
                if addr[0] in [peer.node_address for peer in self.lista_nodes]:
                    continue

                print(f"Nó {discovery_node_id} descoberto no endereço {addr[0]}")
                self.lista_nodes.append(discovered_node)

    def showPeers(self):
        if not self.lista_nodes:
            print('Nenhum peer conectado a rede')
            return
        
        i = 1
        for peer in self.lista_nodes:
            print(f'Peer {i}\n ID: {peer.node_id}\n Endereco: {peer.node_address}')
            print()
            i += 1

    def readFile(self, filename):
        try:
            with open(os.path.join(self.private_directory, f'{filename}.txt'), 'r+') as file:
                text_lines = file.readlines()
            return text_lines
        except FileNotFoundError:
            print('Arquivo nao encontrado')
            return False
        except Exception as e:
            print(f'Erro ao ler o arquivo: {e}')
            return False

    #enviar arquivos
    def sendFile(self, filename, address):
        try:
            text_lines = self.readFile(filename)
            if text_lines is False:
                return

            # Criação socket UDP para enviar uma mensagem de controle - Utilização do socket UDP por N motivos
            control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            control_message = ('Enviando arquivo', 'FILE')
            b_control = pickle.dumps(control_message)
            control_socket.sendto(b_control, (address, 55556))

            time.sleep(5)

            # Criação do socket TCP para fazer o envio do arquivo - Utilizando o socket TCP para garantir a entrega do arquivo etc
            file_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            file_socket.connect((address, 55555))

            blob = (filename, 'FILE')
            buffered_blob = pickle.dumps(blob)
            file_socket.send(buffered_blob)

            if not text_lines:
                return

            for line in text_lines:
                blob = (line, 'FILE')
                buffered_blob = pickle.dumps(blob)
                file_socket.send(buffered_blob)
                print(f'Enviando: {line}')
                time.sleep(0.1)

            blob = ('COMPLETE', 'FILE')
            buffered_blob = pickle.dumps(blob)
            file_socket.send(buffered_blob)

            print('Transferência de arquivo completa')
            file_socket.close()
            control_socket.close()
        except Exception as e:
            print(f'Erro ao enviar arquivo: {e}')

    #recebimento de arquivos
    def receiveFile(self):
        server_address = '0.0.0.0'
        server_port = 55555

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((server_address, server_port))
        
        server.listen(5)

        client_socket, client_address = server.accept()
    
        text = list()

        while True:
            data = client_socket.recv(1024)

            if not data:
                break

            debuffered_data = pickle.loads(data)
            message_text = debuffered_data[0]

            if message_text == 'COMPLETE':
                break
            text.append(message_text)

        server.close()
        return text

    def buildFile(self, text_list):
        filename = text_list[0]
        with open(os.path.join(self.private_directory, f'{filename}.txt'), 'w+') as file:
            for line in text_list[1:]:
                file.write(line)

    def requestFile(self, filename, address):
        request_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        blob = (filename, 'REQUEST')
        buffered_blob = pickle.dumps(blob)

        request_socket.sendto(buffered_blob, (address, 55556))

        request_socket.settimeout(5)  #set a timeout for waiting for a response

        try:
            data, addr = request_socket.recvfrom(1024)
            extensive_data = pickle.loads(data)
            message = extensive_data[0]
            code = extensive_data[1]

            if code == 'ERROR':
                print(f"Peer {addr[0]} não tem o arquivo '{filename}'")
            else:
                print(f"Recebido: {message}")
        except socket.timeout:
            print("Não recebeu uma resposta a tempo")

        request_socket.close()


    #recebimento de mensagens
    def receive_messages(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(('0.0.0.0', 55556))

        while encerrarPrograma == False:
            data, addr = server.recvfrom(1024)
            
            extensive_data = pickle.loads(data)

            message = extensive_data[0]
            code = extensive_data[1]

            print(f"Mensagem recebida de {addr}: {message}")

            ip_address = addr[0]

            if code == 'FILE':
                file = self.receiveFile()
                self.buildFile(file)

            if code == 'REQUEST':
                try:
                    file = self.readFile(message)
                    if file == False:
                        error_message = ('Não tenho o arquivo solicitado', 'ERROR')
                        buffered_error = pickle.dumps(error_message)
                        server.sendto(buffered_error, addr)
                    else:
                        self.sendFile(message, address=ip_address)
                except Exception as e:
                    print(f'{self.node_id}: Não tenho o arquivo')
                    continue

            if code == 'DISCONNECTING':
                for peer in self.lista_nodes:
                    if peer.node_address == ip_address:
                        self.lista_nodes.remove(peer)

    #envio de mensagens
    def send_message(self, dest_id, message, code):
        dest_ip = None

        dest_port = 55556  

        for peer in self.lista_nodes:
            if dest_id == peer.node_id:
                dest_ip = peer.node_address

        #configurar o socket UDP para enviar mensagens
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        blob = (message, code)
        buffered_blob = pickle.dumps(blob)

        #enviar mensagem para o destino
        if dest_ip is not None:
            #enviar mensagem para o destino
            client.sendto(buffered_blob, (dest_ip, dest_port))
        else:
            print(f"Peer de destino nao encontrado")

    def exitNetwork(self):
        if not self.lista_nodes:
            return
        
        for peer in self.lista_nodes:
            self.send_message(peer.node_id, f'Peer {self.node_id} está saindo da rede', 'DISCONNECTING')

#nó descoberto pela rede
class PrimitiveNode:
    def __init__(self, node_id, node_address):
        self.node_id = node_id
        self.node_address = node_address

#MAIN
if __name__ == "__main__":
    id = str(input("Digite um ID: "))
    address = socket.gethostbyname(socket.gethostname())
    new_node = Node(id, address)
    
    broadcasting_thread = threading.Thread(target=new_node._send_discovery_message)
    broadcasting_thread.start()

    discovery_thread = threading.Thread(target=new_node._listen_for_discovery)
    discovery_thread.start()
    
    receiver_thread = threading.Thread(target=new_node.receive_messages)
    receiver_thread.start() 

    while True:
        print('----- MENU -----')
        print('1 - Enviar Mensagem')
        print('2 - Enviar Arquivo')
        print('3 - Mostrar Peers')
        print('4 - Pedir Arquivo')
        print('5 - Sair da Rede')

        option = input('Digite uma opcao: ')
        print()

        if option == '1':
            id_send = input('Digite o id do recebedor: ')
            message = input('Digite a mensagem: ')
            print()

            new_node.send_message(id_send, message, 'MESSAGE')
            continue 

        if option == '2':
            send_id = input('Digite o id: ')
            nome_arquivo = input('Digite o nome do arquivo: ')

            for peer in new_node.lista_nodes:
                if send_id == peer.node_id:
                    new_node.sendFile(nome_arquivo, peer.node_address)
                    
            continue

        if option == '3':
            new_node.showPeers()
            continue

        if option == '4':
            filename = input('Digite o nome do arquivo: ')
            try:
                with open(os.path.join('private_data', f'{filename}.txt'), 'r+') as file:
                    text_lines = file.readlines()
                print('Arquivo solicitado ja existe.') 
            except:
                for peer in new_node.lista_nodes:
                    new_node.requestFile(filename, peer.node_address)

        if option == '5':
            new_node.exitNetwork()
            encerrarPrograma = True
            broadcasting_thread.join()
            discovery_thread.join()
            receiver_thread.join()
            break
        