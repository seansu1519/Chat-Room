import socket
import sys

class MessageObj():
    def __init__(self, sender, reciever, msg, file_dic):
        self.send_name = sender
        self.recv_name = reciever
        self.message = msg
        self.file_dic = file_dic

class UserDataObj():
    def __init__(self, mode, username, password):
        self.mode = mode
        self.username = username
        self.password = password

def createSocket():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except socket.error:
        print('Failed to create socket.')
        sys.exit()
    print('Socket created...')
    return s

