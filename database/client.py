import getpass
import pickle
import socket
import sys
import os
import threading
import subprocess
import struct
import json
from helper import UserDataObj, MessageObj, createSocket
HOST = 'localhost'
PORT = 5488
YOUR_NAME = None


def user_exist(*data):
    if len(data) == 1:
        s.sendall(pickle.dumps(UserDataObj('check_name', data[0], '')))
        return True if s.recv(4096).decode() == 'T' else False
    elif len(data) == 2:
        s.sendall(pickle.dumps(UserDataObj('check_name_and_pwd', data[0], data[1])))
        return True if s.recv(4096).decode() == 'T' else False

def register_or_signin():
    global YOUR_NAME
    action = None
    
    while action != '1' and action != '2':
        action = input('Register(1) or Sign in(2)? ')
    
    # Register
    if action == '1':
        while True:
            username = input('Input an username: ')
            if user_exist(username):
                print('Username exist.')
                continue
            break
        while True:
            password = getpass.getpass('Set a password: ')
            if getpass.getpass('Please type your password again: ') == password:
                s.sendall(pickle.dumps(UserDataObj('set_name_and_pwd', username, password)))
                s.sendall(pickle.dumps(UserDataObj('OK', username, '')))
                break
        YOUR_NAME = username
    # Sign in
    elif action == '2':
        while True:
            username = input('Input your username: ')
            if user_exist(username):
                break
            print('Username not exist.')
        while True:
            password = getpass.getpass('Input your password: ')
            if user_exist(username, password):
                s.sendall(pickle.dumps(UserDataObj('OK', username, '')))
                break
            print('Wrong password.')
        YOUR_NAME = username

# Covert domain name to ip address and connect to it.
def get_host_and_connect(s):
    try:
        remote_ip = socket.gethostbyname(HOST)
    except socket.gaierror:
        print('Hostname could not be resolved. Exiting...')
        sys.exit()
    print('Ip address of', HOST, 'is', remote_ip)

    try:
        s.connect((remote_ip, PORT))
    except ConnectionRefusedError:
        print('Server is not running...')
        sys.exit()
    
    print('Socket Connected to', HOST ,'on ip', remote_ip, '...')
    register_or_signin()


def option():
    while True:
        send_type = input("File(1) or message(2) or search(3)?")
        if send_type == '1':
            send_file()
        elif send_type == '2':
            to_send = pickle.dumps(send_type)
            s.sendall(to_send)
            send_message()
        elif send_type == '3':
            to_send = pickle.dumps(send_type)
            s.sendall(to_send)
            search_message()
        else:
            break

def send_file():
    share_dir = os.getcwd()
    filename_list = input('Enter a filename or several files seperated by spaces: ').split()
    recv_name = input("To whom?: " )
    to_send = pickle.dumps('1')
    s.sendall(to_send)
    
    #send files in a row
    for filename in filename_list:

        header_dic = {
            'filename':filename,
            'file_size':os.path.getsize('%s/%s'%(share_dir, filename)), 
            'recv_name':recv_name,
            'end_flg': False
        }

        if filename == filename_list[-1]: header_dic['end_flg'] = True
        
        header_json = json.dumps(header_dic)
        header_bytes = header_json.encode('utf-8')
        
        s.send(struct.pack('i',len(header_bytes)))
        s.send(header_bytes)
    

        with open('%s/%s' % (share_dir, filename),'rb') as f:
            for line in f:
                s.sendall(line)

# A thread for sending messages
def send_message():
    global YOUR_NAME
    while True:
        message = input("Type your message: ")
        # If you type 'exit', you will recieve it yourself and disconnect from the server.  See 'recv_msg_thread'
        if message == 'exit':
            to_send = pickle.dumps(MessageObj(YOUR_NAME, YOUR_NAME, message, None))
            s.sendall(to_send)
            break
        target = input("To whom? ")
        to_send = pickle.dumps(MessageObj(YOUR_NAME, target, message, None))
        try :
            s.sendall(to_send)
            break
        except socket.error:
            print('Send failed')
            sys.exit()

def search_message():
    global YOUR_NAME
    friend = input("Enter a friend name: ")
    keyword = input("Please input any keyword: ")
    s.sendall(pickle.dumps({'searcher': YOUR_NAME, 'friend': friend, 'keyword': keyword}))

# A thread for recieving messages
def recv_msg_thread():
    while True:
        send_type = s.recv(1024)
        send_type = pickle.loads(send_type)
        if send_type == 'message':
            reply = s.recv(4096)
            recvObj = pickle.loads(reply)
            # If you recieve a 'exit' message from yourself, you will break the thread.
            if recvObj.message == 'exit' and recvObj.send_name == YOUR_NAME:
                break
            if recvObj.message == 'No such message' and recvObj.send_name == '':
                print(recvObj.message)
                break
            
            print(recvObj.send_name + ':' + recvObj.message)
        elif send_type == 'file':
            reply = s.recv(4)
            download_dir = os.getcwd()
            header_size = struct.unpack('i',reply)[0]
            header_bytes = s.recv(header_size)
            header_json = header_bytes.decode('utf-8')
            header_dic = json.loads(header_json)
            
            total_size = header_dic['file_size']
            file_name = header_dic['filename']

            with open('%s/download_files/%s'%(download_dir, file_name),'wb') as f:
                recv_size = 0
                print('You recieved a file...')
                while recv_size < total_size:
                    line = s.recv(1024)
                    f.write(line)
                    recv_size += len(line)
                    #print('總大小：%s  已下載大小：%s' % (total_size, recv_size))

# Create two threads for sending and recieving messages
def communication():
    se = threading.Thread(target = option)
    re = threading.Thread(target = recv_msg_thread)
    se.start()
    re.start()

    # Threads will be joined after it's done
    se.join()
    re.join()

s = createSocket()
get_host_and_connect(s)
communication()
s.close()
