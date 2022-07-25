import socket
import sys
import pickle
import time
import numpy as np

MAXDATALEN = 2048

class DataSocket:
    def __init__(self, dataLen=1024, dataSize=4, sock=None):
        if sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        else:
            self.sock = sock
            
        self.dataSize = dataSize
        self.dataLen = dataLen * dataSize
        
    def connect(self, host, port):
        self.sock.connect((host, port))
        
    def close(self):
        self.sock.close()
        
    def setDataLen(self, dataLen):
        self.dataLen = dataLen * self.dataSize
        
    def receiveData(self):
    
        chunks = []
        bytes_received = 0
        try:
            while bytes_received < self.dataLen:
                chunk = self.sock.recv(min(self.dataLen - bytes_received, MAXDATALEN))
                chunks.append(chunk)
                bytes_received += len(chunk)
        except:
            print("Data unsuccessfully received")
            chunks = []
        
        time.sleep(0.1)
        if self.dataSize == 4:
            return np.frombuffer(b''.join(chunks), dtype=np.int32)
        elif self.dataSize == 8:
            return np.frombuffer(b''.join(chunks), dtype=np.float64)
        else:
            return np.frombuffer(b''.join(chunks), dtype=float)
    
    def sendCmd(self, msg, arg=0):
        try:
            self.sock.send(pickle.dumps([msg, arg]))
            time.sleep(0.1)
            return True
        except:
            return False


if __name__ == '__main__':
    server_address = ('audio-analyzer.local', 10000)
    mySock = DataSocket()
    mySock.connect(server_address[0], server_address[1])

    dataSize = 16384
    mySock.setDataLen(dataSize)
    
    mySock.sendCmd('dataSize', dataSize)
    mySock.sendCmd('startSend')

    for i in range(10):
        data = mySock.receiveData()
        print(data)
        print(len(data))
        mySock.sendCmd('idle')
    data = mySock.receiveData()
    print(data)
    print(len(data))

    mySock.sendCmd('stopSend')
    mySock.close()

