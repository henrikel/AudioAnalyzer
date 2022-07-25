import select
import socket
import sys
import pickle
import time
import numpy as np
import pyaudio

MAXDATALEN = 2048

DATALENGTH = 1024

sendData = False
dataLength = 4
frequency = 1000
fs = 192000
amplitude = 2**31-1
startIdx = 0
generatorActive = False
audioStream = None
measurementData = None
		
def sendMyData(sock, data):
		
	totalsent = 0
	d = bytes(data)
		
	while totalsent < len(d):
		sent = sock.send(d[totalsent:])
		if sent == 0:
			raise RuntimeError("Socket connection broken")
		totalsent += sent
	
	return totalsent
	
def audioCallback(inData, frameCount, timeInfo, status):
    
    global startIdx, measurementData
    
    if generatorActive:
        t = (startIdx + np.arange(frameCount)) / fs
        t = t.reshape(-1, 1)
        outData = (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.int32)
        startIdx += frameCount
    else:
        outData = np.zeros(frameCount)
        
    if any(inData):
        measurementData = np.frombuffer(inData, dtype=np.float32)[:dataLength]
    else:
        measurementData = None
        #print(len(inData))
        
    return (outData.astype(np.int32).tobytes(), pyaudio.paContinue)

p = pyaudio.PyAudio()

# Create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#server.setblocking(0)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

# Bind the socket to the port
server_address = ('0.0.0.0', 10000)
print('starting up on %s port %s' % server_address)
sock.bind(server_address)

# Listen for incoming connections
sock.listen(5)

while True:
	print("Waiting for a connection")
	connection, client_address = sock.accept()
	
	try:
		print("Connection from", client_address)
		audioStream = p.open(format=pyaudio.paInt32, channels=1, rate=fs, output=True,
		                     input=True, input_device_index=0, output_device_index=0,
		                     frames_per_buffer=65536, stream_callback=audioCallback)
		
		while(True):
			try:
				data = connection.recv(1024)
			except:
				data = None
				connection.close()
				print("No data")
				break
			if data:
				d = pickle.loads(data)
				if type(d) is list:
					cmd = d[0]
					if len(d) > 1:
						arg = d[1]
					if cmd == 'dataSize':
						print("Set data size to", arg)
						dataLength = arg
					elif cmd == 'frequency':
					    print("Set generator frequency to", arg)
					    frequency = arg
					elif cmd == 'fs':
					    print("Set sampling frequency to", arg)
					    fs = arg
					elif cmd == 'startGen':
					    print("Starting generator")
					    if not generatorActive:
					        generatorActive = True
					        startIdx = 0
					elif cmd == 'stopGen':
					    print("Stopping generator")
					    if generatorActive:
					        generatorActive = False
					elif cmd == 'startSend':
						print("Start sending data")
						if not sendData:
						    sendData = True
						    audioStream.start_stream()
					elif cmd == 'stopSend':
						print("Stop sending data")
						if sendData:
						    sendData = False
					elif cmd != 'idle':
						break
			else:
				print("No data from", client_address)
				if not sendData:
					break
			
			if sendData:
				try:
					#if measurementData is None:
					#	measurementData = np.ones(dataLength)
					if not measurementData is None:
					    mData = measurementData.copy()
					else:
					    mData = np.random.randn(dataLength)
					if sendMyData(connection, mData) > 0:
					    pass
						#print("Sending data of length {}".format(dataLength))
					#connection.send(bytes(b))
					time.sleep(0.1)
				except:
					print("Transmission error")
					connection.close()
					break
	finally:
		# Clean up
		print("Closing current connection")
		if not audioStream is None:
		    if sendData:
		        audioStream.stop_stream()
		        audioStream.close()
		        audioStream = None
		connection.close()

p.terminate()