"""P2P tracker"""

from socket import *
import threading
import struct
import json
from time import time, localtime, strftime


serverPort = 12000
serverSocket = socket(AF_INET, SOCK_STREAM)
serverSocket.bind(('', serverPort))
serverSocket.listen(10)

flock = threading.Lock()
plock = threading.Lock()
thread_list = []
sthread_list = []

fileList = {}
peerList = {"peers": []}
logs = []


def logger(log: str, level='Info'):
    logtime = strftime('%Y-%m-%d %H:%M:%S', localtime(time()))
    logs.append(f"[{level}][{logtime}] {log}")


def send_yes(psocket, addr):
    try:
        psocket.send(struct.pack("!cI", b'Y', 5))
    except:
        closed_by_peer(psocket, addr)


def send_no(psocket, addr):
    try:
        psocket.send(struct.pack("!cI", b'N', 5))
    except:
        closed_by_peer(psocket, addr)


def recv_data(psocket) -> tuple:
    recvBytes = psocket.recv(2048)
    header = struct.unpack("!cI", recvBytes[:5])
    body = recvBytes[5:].decode()
    return (header, body)


def peer_on(psocket, addr, chatport):
    send_yes(psocket, addr)
    with plock:
        peerList["peers"].append((addr[0], int(chatport)))
    logger(f"Connection from {addr[0]}:{addr[1]}.")


def peer_off(psocket, addr):
    send_yes(psocket, addr)
    psocket.close()
    try:
        with plock:
            plist = peerList["peers"]
            for i in range(len(plist)):
                if plist[i][0] == addr[0]:
                    del plist[i]
                    log = f"Delete peerinfo of {addr}."
                    logger(log)
            #peerList["peers"].remove(addr)
            del_flist(psocket, addr, all=True)
    except:
        log = f"Delete peerinfo of {addr} failed."
        logger(log, level='Error')
    logger(f"Connection from {addr[0]}:{addr[1]} closed.")
    exit(0)


def check_error(header, target, psocket, addr):
    if header != target:
        closed_by_peer(psocket, addr)


def update_flist(psocket, addr, body):
    if not body:
        return
    modbody = eval(body)
    filename = modbody[0]
    filesize = modbody[1]
    seedport = modbody[2]
    with flock:
        if filename in fileList:
            fileList[filename]["peers"].append((addr[0], seedport))
        else:
            fileList[filename] = {"size": filesize, "peers": [(addr[0], seedport)]}
    log = f"Update fileinfo of '{filename}', from {addr}."
    logger(log)
    send_yes(psocket, addr)


def del_flist(psocket, addr, body=None, all=False):
    if all == True:
        for filename in list(fileList.keys()):
            try:
                with flock:
                    plist = fileList[filename]["peers"]
                    for i in range(len(plist)):
                        if plist[i][0] == addr[0]:
                            del plist[i]
            except:
                log = f"Delete fileinfo of {addr} failed."
                logger(log, level='Error')
            if len(fileList[filename]["peers"]) == 0:
                with flock:
                    del fileList[filename]
    else:
        if not body:
            send_no(psocket, addr)
            return
        filename = body
        if filename not in fileList:
            send_no(psocket, addr)
            return
        try:
            with flock:
                plist = fileList[filename]["peers"]
                for i in range(len(plist)):
                    if plist[i][0] == addr[0]:
                        del plist[i]
        except:
            send_no(psocket, addr)
            log = f"Delete fileinfo of {addr} failed."
            logger(log, level='Error')
            return
        if len(fileList[filename]["peers"]) == 0:
            with flock:
                del fileList[filename]
        log = f"Delete fileinfo of '{filename}', from {addr}."
        logger(log)
        send_yes(psocket, addr)


def ret_flist(psocket, addr, body):
    if not body:
        send_no(psocket, addr)
        return
    if fileList.get(body, None) != None:
        sbody = json.dumps(fileList[body]).encode()
        header = struct.pack("!cI", b'F', len(sbody)+5)
        try:
            psocket.send(header + sbody)
        except:
            closed_by_peer(psocket, addr)
    else:
        send_no(psocket, addr)


def ret_plist(psocket, addr):
    sbody = json.dumps(peerList).encode()
    header = struct.pack("!cI", b'P', len(sbody)+5)
    try:
        psocket.send(header + sbody)
    except:
        closed_by_peer(psocket, addr)


def shutdown(psocket, addr):
    send_yes(psocket, addr)
    psocket.close()
    logger(f"{addr[0]}:{addr[1]} closed, program shutdown.", 'Warning')
    del_flist(psocket, addr, all=True)
    try:
        with plock:
            plist = peerList["peers"]
            for i in range(len(plist)):
                if plist[i][0] == addr[0]:
                    del plist[i]
            #peerList["peers"].remove(addr)
    except:
        pass
    global serverSocket
    serverSocket.close()
    exit(0)


def closed_by_peer(psocket, addr):
    log = f"Connection from {addr[0]}:{addr[1]} closed by peer."
    #print(log)
    logger(log, 'Error')
    del_flist(psocket, addr, all=True)
    try:
        with plock:
            plist = peerList["peers"]
            for i in range(len(plist)):
                if plist[i][0] == addr[0]:
                    del plist[i]
            #peerList["peers"].remove(addr)
    except:
        pass
    exit(0)


def tcp_connect(psocket, addr):
    while True:
        try:
            package = recv_data(psocket)
        except:
            closed_by_peer(psocket, addr)
        header = package[0]
        if header[0] == b'S':
            shutdown(psocket, addr)
        elif header[0] == b'O':
            peer_on(psocket, addr, package[1])
        elif header[0] == b'F':
            peer_off(psocket, addr)
        elif header[0] == b'D':
            update_flist(psocket, addr, package[1])
        elif header[0] == b'X':
            del_flist(psocket, addr, package[1])
        elif header[0] == b'G':
            ret_flist(psocket, addr, package[1])
        elif header[0] == b'P':
            ret_plist(psocket, addr)


def tcp_accept():
    logger("The server is online.")
    global serverSocket
    while True:
        try:
            newSocket, addr = serverSocket.accept()
        except OSError:
            #for j in sthread_list:
            #    j.join()
            exit(0)
        t = threading.Thread(target=tcp_connect, args=(newSocket, addr))
        t.setDaemon(True)
        t.start()
        sthread_list.append(t)


def start_gui():
    print("The server is online.\n")
    hint = "Please use 'cat' to read all logs, \
'cat [num]' to read [nums] lines of latest logs.\n\
Type 'exitnow' to exit."
    while True:
        print(hint)
        raw = input('$> ')
        args = raw.split(' ')
        argnum = len(args) - 1
        command = args[0]
        arg = 0 if len(args) == 1 else int(args[1])
        if command == 'cat':
            if arg > 0:
                try:
                    for item in logs[-arg:]:
                        print(item)
                    print(' ')
                except:
                    print("Command error.")
            elif arg == 0:
                for item in logs:
                    print(item)
                print(' ')
            else:
                print("Command error.")
        elif command == 'flist':
            print(fileList)
        elif command == 'plist':
            print(peerList)
        elif command == 'exitnow':
            exitstr = "Shutdown by user."
            logger(exitstr, 'Info')
            with open("server.log", 'a', encoding='utf-8') as f:
                for line in logs:
                    f.write(line + '\n')
            #for j in thread_list:
            #    j.join()
            exit(0)
        else:
            print("Command error.")


def __main__():
    t = threading.Thread(target=tcp_accept)
    t.setDaemon(True)
    t.start()
    thread_list.append(t)
    start_gui()


if __name__ == "__main__":
    __main__()
