import hashlib
import pickle
import pymysql
import socket
import sys
import os
import threading
import subprocess
import struct
import json
from helper import UserDataObj, MessageObj, createSocket
HOST = 'localhost'
PORT = 5487
MAX_CLIENT_NUM = 10
client_data = {}

def connect_to_db():
    global db, cursor
    try:
        # Connect to database, Username: root, Password: password, DB: ChatApp
        db = pymysql.connect('localhost', 'root', 'password', 'ChatApp')
        cursor = db.cursor(pymysql.cursors.DictCursor)
        print('DB connected...')
    except:
        print('DB connection error')
    return db, cursor

# Handle the registration or sign in process
def register_or_signin(conn):
    while True:
        userdata = pickle.loads(conn.recv(1024))
        # Check if the username is in the database.
        if userdata.mode == 'check_name':
            sql = """
                SELECT username
                FROM Info_UserData
                WHERE username = '%s'
            """ % (userdata.username)
            cursor.execute(sql)
            results = cursor.fetchall()
            conn.sendall('T'.encode() if len(results) != 0 else 'F'.encode())
        # Check if the (username, password) pair is in the database.
        elif userdata.mode == 'check_name_and_pwd':
            sql = """
                SELECT username
                FROM Info_UserData
                WHERE username = '%s' AND password = '%s'
            """ % (userdata.username, hashlib.sha256(userdata.password.encode()).hexdigest())
            cursor.execute(sql)
            results = cursor.fetchall()
            conn.sendall('T'.encode() if len(results) != 0 else 'F'.encode())
        # Insert new user data into the database.(Registration)
        elif userdata.mode == 'set_name_and_pwd':
            sql = """
                INSERT INTO Info_UserData(username, password)
                VALUES('%s', '%s')
            """ % (userdata.username, hashlib.sha256(userdata.password.encode()).hexdigest())
            try:
                cursor.execute(sql)
                db.commit()
            except pymysql.DatabaseError as e:
                print(e)
                db.rollback()
        # If the user finishes registration or login, it will send 'OK'.
        # Then this method return his(her) username.
        elif userdata.mode == 'OK':
            return userdata.username

# Bind the socket object to specified host/port, and listen at it.
def socket_bind_listen(s_obj, host, port, max_client_num):
    try:
        s_obj.bind((host, port))
    except socket.error as e:
        print(e)
        sys.exit()
    print('Socket bind complete...')
    
    s_obj.listen(max_client_num)
    print('Socket now listening...')

# This method waits for clients to connect, 
# and start a new thread when a new client is connected.
def handle_connections(s_obj):
    threads = []
    threading.Thread(target = server_command, args = (s_obj,)).start()
    while True:
        conn, addr = s_obj.accept()
        name = register_or_signin(conn)
        print('Connected with ' + addr[0] + ':' + str(addr[1]) + ' Name:' + name)
        client_data[name] = {'sock_obj': conn, 'addr': addr}
        threads.append(threading.Thread(target = on_new_client, args = (conn, addr)))
        threads[-1].start()
    
    # Not used now
    for i in threads:
        i.join()

def server_command(s):
    if(input() == 'exit'):
        # Doesn't actually turn of the program
        print('Turning off the server...')

# Send offline messages when the user is online
def send_offline_message(client_name):
    sql = """
        SELECT *
        FROM Log_OfflineMessage
        WHERE reciever = '%s'
    """ % (client_name)
    cursor.execute(sql)
    results = cursor.fetchall()
    for message in results:
        send_type = pickle.dumps('message')
        client_data[client_name]['sock_obj'].sendall(send_type)
        client_data[client_name]['sock_obj'].sendall(pickle.dumps(MessageObj(message['sender'], message['reciever'], message['message'], None)))

    sql = """
        DELETE FROM Log_OfflineMessage WHERE reciever = '%s'
    """ % (client_name)
    cursor.execute(sql)
    db.commit()

def recieve_file(clientsocket):
    while True:
        download_dir = os.getcwd()
        header_size = struct.unpack('i', clientsocket.recv(4))[0]
        header_bytes = clientsocket.recv(header_size)
        header_json = header_bytes.decode('utf-8')

        header_dic = json.loads(header_json)
        total_size = header_dic['file_size']
        file_name = header_dic['filename']
        recv_name = header_dic['recv_name']

        with open('%s/database/%s'%(download_dir, file_name),'wb') as f:
            recv_size = 0
            while recv_size < total_size:
                line = clientsocket.recv(1024)
                f.write(line)
                recv_size += len(line)
                print('總大小：%s  已下載大小：%s' % (total_size, recv_size))

        if recv_name in client_data:
            send_type = pickle.dumps('file')
            client_data[recv_name]['sock_obj'].sendall(send_type)
            client_data[recv_name]['sock_obj'].send(struct.pack('i',len(header_bytes)))
            client_data[recv_name]['sock_obj'].send(header_bytes)

            with open('%s/database/%s'%(download_dir, file_name),'rb') as f:
                for line in f:
                    client_data[recv_name]['sock_obj'].send(line)
        else:
            print("Person not found. (file)")
            break
        
        if header_dic['end_flg']: break

def recieve_message(clientsocket):
    data = clientsocket.recv(1024)
    recv_msg = pickle.loads(data)
    print('From:', recv_msg.send_name, 'To:', recv_msg.recv_name, 'Message:', recv_msg.message)

    # Store the message into the database
    sql = """
        INSERT INTO Log_UserMessage(sender, reciever, message)
        VALUES('%s', '%s', '%s')
    """ % (recv_msg.send_name,recv_msg.recv_name, recv_msg.message)
    try:
        cursor.execute(sql)
        db.commit()
    except pymysql.DatabaseError as e:
        print(e)
        db.rollback()

    if recv_msg.recv_name in client_data:
        send_type = pickle.dumps('message')
        client_data[recv_msg.recv_name]['sock_obj'].sendall(send_type)
        client_data[recv_msg.recv_name]['sock_obj'].sendall(data)
    else:
        print('Person not found...')
        # Store the message into the db if the reciever isn't online
        sql = """
            INSERT INTO Log_OfflineMessage(sender, reciever, message)
            VALUES('%s', '%s', '%s')
        """ % (recv_msg.send_name,recv_msg.recv_name, recv_msg.message)
        try:
            cursor.execute(sql)
            db.commit()
        except pymysql.DatabaseError as e:
            print(e)
            db.rollback()

def search_message(clientsocket):
    data = pickle.loads(clientsocket.recv(4096))
    sql = """
        SELECT sender, reciever, message
        FROM Log_UserMessage
        WHERE message LIKE '%""" + data['keyword'] + """%'
        AND (sender = '""" + data['friend'] + "' OR reciever = '" + data['friend'] + "')"
    cursor.execute(sql)
    results = cursor.fetchall()
    if len(results) != 0:
        for i in range(len(results)):
            to_send = pickle.dumps(MessageObj(results[i]['sender'], results[i]['reciever'], results[i]['message'], None))
            try:
                send_type = pickle.dumps('message')
                client_data[data['searcher']]['sock_obj'].sendall(send_type)
                client_data[data['searcher']]['sock_obj'].sendall(to_send)
            except socket.error:
                print('Send failed')
                sys.exit()
    else:
        to_send = pickle.dumps(MessageObj('', '', 'No such message', None))
        try:
            send_type = pickle.dumps('message')
            client_data[data['searcher']]['sock_obj'].sendall(send_type)
            client_data[data['searcher']]['sock_obj'].sendall(to_send)
        except socket.error:
            print('Send failed')
            sys.exit()

# Call this method whenever a new client thread created.
def on_new_client(clientsocket, addr):
    # Check and send offline messages
    client_name = None
    for name in client_data:
        if client_data[name]['sock_obj'] == clientsocket:
            client_name = name
            break

    send_offline_message(client_name)

    while True:
        data = clientsocket.recv(1024)
        if not data:
            print('One client disconnect...')
            del client_data[client_name]
            break

        send_type = pickle.loads(data)
        if send_type == '1': # file
            recieve_file(clientsocket)
        elif send_type == '2': # message
            recieve_message(clientsocket)
        elif send_type == '3': # searching
            search_message(clientsocket)

db, cursor = connect_to_db()
s = createSocket()
socket_bind_listen(s, HOST, PORT, MAX_CLIENT_NUM)
handle_connections(s)
s.close()
db.close()
