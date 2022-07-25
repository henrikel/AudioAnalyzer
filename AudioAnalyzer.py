import sys
import random
import matplotlib
import numpy as np
import time
import subprocess
from audioSocket import DataSocket

matplotlib.use('Qt5Agg')

from PyQt5 import QtCore, QtWidgets

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT
from matplotlib.figure import Figure
from scipy.signal.windows import hann, hamming, kaiser, blackman

kaiserBeta = 5

# Widgets for:
# Signal frequency: textbox
# Min frequency: textbox
# Max frequency: textbox
# Data size: popup
# Averaging number: popup
# THD: text
# THD+N: text
# Frequency range (min, max): textbox
# Plot type (lin/log): popup
# Window function: Hamming, Hann, Blackman etc
# Server address: textbox
# Connect button
# Close button



class MplCanvas(FigureCanvas):

    def __init__(self, parent=None, width=5, height=4, dpi=100):
        
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.fig.add_subplot(111)
        self.lines = None
        
        super(MplCanvas, self).__init__(self.fig)
        
    def initPlot(self, xData, yData, frequencyRange):
        
        self.lines = self.axes.semilogx(xData, 20.0 * np.log10(yData + np.finfo(float).eps))
        
        self.hLines = []
        self.maxHLines = 100
        for i in range(self.maxHLines):
            l = self.axes.semilogx(1, 1, 'ro')
            self.hLines.append(l[0])
            
        self.axes.axis((frequencyRange[0], frequencyRange[1], -140,5)) # Change
        self.axes.yaxis.grid(True)
        self.axes.xaxis.grid(True)
        self.axes.set_xlabel('Frequency [Hz]')
        self.axes.set_ylabel('Relative magnitude [dB]')
        
        t = "THD: {0:.4f}%\nNoise: {1:.1f} dB".format(0, -200)
        self.thdText = self.axes.text(frequencyRange[0]*1.1,-10, t)
        self.thdText.set_bbox(dict(facecolor='white'))
        
        self.fig.tight_layout(pad=1)
        
    def updatePlot(self, xData, yData, measurementData, frequencyRange, harmonics):
        
        if not self.lines is None:
            for column,line in enumerate(self.lines):
                line.set_ydata(20.0 * np.log10(yData + np.finfo(float).eps))
                
        if (not self.hLines is None) and (not harmonics is None):
            for column,line in enumerate(self.hLines):
                if column < len(harmonics):
                    line.set_xdata(harmonics[column,0])
                    line.set_ydata(20.0*np.log10(harmonics[column,1] + np.finfo(float).eps))
                else:
                    line.set_xdata(1)
                    line.set_ydata(1)
        
        self.thdText.set_text("THD: {0:.4f}%\nNoise: {1:.1f} dB".format(measurementData['THD'], measurementData['Noise']))


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, app, *args, **kwargs):
        
        super(MainWindow, self).__init__(*args, **kwargs)
        
        self.samplingRate = 192000
        self.generatorFrequency = 1000
        self.generatorActive = False
        self.blockSize = 16384
        self.averaging = 64
        self.winTxt= 'Hann'
        self.minFreq = 10
        self.maxFreq = self.samplingRate/2
        self.serverAddress = "audio-analyzer.local"
        self.bufIdx = 0
        self.cleanup = False
        
        self.measurementData = np.ones(self.blockSize) * np.finfo(float).eps
        self.dataBuf = np.zeros((self.blockSize, self.averaging))
        
        if self.winTxt == 'Hann':
            self.win = hann(self.blockSize)
        elif self.winTxt == 'Hamming':
            self.win = hamming(self.blockSize)
        elif self.winTxt == 'Blackman':
            self.win = blackman(self.blockSize)
        elif self.winTxt == 'Kaiser':
            self.win = kaiser(self.blockSize, kaiserBeta)
        
        self.frequencies = np.arange(self.blockSize) / self.blockSize * self.samplingRate
        self.dataLen = int(self.blockSize/2) + 1
        
        # GUI elements
        self.canvas = MplCanvas(self, width=10, height=8, dpi=100)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        
        self.connectButton = QtWidgets.QPushButton('Connect')
        self.connectButton.clicked.connect(self.doConnectButton)
        
        self.shutDownButton = QtWidgets.QPushButton('Shutdown')
        self.shutDownButton.clicked.connect(self.doShutDownButton)
        self.shutDownButton.setEnabled(False)
        self.shutDownButton.setStyleSheet("background-color: red")
        
        self.generatorCheckBox = QtWidgets.QCheckBox('Generator activated')
        self.generatorCheckBox.stateChanged.connect(self.doGeneratorCheckBox)
        self.generatorCheckBox.setEnabled(False)
        
        self.freqTxt = QtWidgets.QLabel("Generator frequency (Hz)")
        self.freqInput = QtWidgets.QLineEdit('1000', objectName="Frequency")
        self.freqInput.returnPressed.connect(self.doFrequencyText)
        
        self.sampTxt = QtWidgets.QLabel("Sampling frequency (Hz)")
        self.sampPopup = QtWidgets.QComboBox(objectName="SamplingFreq")
        self.sampPopup.addItem("44100")
        self.sampPopup.addItem("48000")
        self.sampPopup.addItem("88200")
        self.sampPopup.addItem("96000")
        self.sampPopup.addItem("192000")
        self.sampPopup.activated[str].connect(self.doPopupSamplingFreq)
        if self.samplingRate == 44100:
            self.sampPopup.setCurrentIndex(3)
        elif self.samplingRate == 48000:
            self.sampPopup.setCurrentIndex(1)
        elif self.samplingRate == 88200:
            self.sampPopup.setCurrentIndex(2)
        elif self.samplingRate == 96000:
            self.sampPopup.setCurrentIndex(3)
        elif self.samplingRate == 192000:
            self.sampPopup.setCurrentIndex(4)
        
        self.aveTxt = QtWidgets.QLabel("Averaging #")
        self.avePopup = QtWidgets.QComboBox(objectName="Averaging")
        self.avePopup.addItem("1")
        self.avePopup.addItem("2")
        self.avePopup.addItem("4")
        self.avePopup.addItem("8")
        self.avePopup.addItem("16")
        self.avePopup.addItem("32")
        self.avePopup.addItem("64")
        self.avePopup.addItem("128")
        self.avePopup.addItem("256")
        self.avePopup.addItem("512")
        self.avePopup.addItem("1024")
        self.avePopup.activated[str].connect(self.doPopupAverage)
        if self.averaging == 1:
            self.avePopup.setCurrentIndex(0)
        elif self.averaging == 2:
            self.avePopup.setCurrentIndex(1)
        elif self.averaging == 4:
            self.avePopup.setCurrentIndex(2)
        elif self.averaging == 8:
            self.avePopup.setCurrentIndex(3)
        elif self.averaging == 16:
            self.avePopup.setCurrentIndex(4)
        elif self.averaging == 32:
            self.avePopup.setCurrentIndex(5)
        elif self.averaging == 64:
            self.avePopup.setCurrentIndex(6)
        elif self.averaging == 128:
            self.avePopup.setCurrentIndex(7)
        elif self.averaging == 256:
            self.avePopup.setCurrentIndex(8)
        elif self.averaging == 512:
            self.avePopup.setCurrentIndex(9)
        elif self.averaging == 1024:
            self.avePopup.setCurrentIndex(10)
        
        self.dataSizeTxt = QtWidgets.QLabel("Data size")
        self.dataSizePopup = QtWidgets.QComboBox(objectName="DataSize")
        self.dataSizePopup.addItem("1024")
        self.dataSizePopup.addItem("2048")
        self.dataSizePopup.addItem("4096")
        self.dataSizePopup.addItem("8192")
        self.dataSizePopup.addItem("16384")
        self.dataSizePopup.addItem("32768")
        self.dataSizePopup.addItem("65536")
        self.dataSizePopup.activated[str].connect(self.doPopupDataSize)
        if self.blockSize == 1024:
            self.dataSizePopup.setCurrentIndex(0)
        elif self.blockSize == 2048:
            self.dataSizePopup.setCurrentIndex(1)
        elif self.blockSize == 4096:
            self.dataSizePopup.setCurrentIndex(2)
        elif self.blockSize == 8192:
            self.dataSizePopup.setCurrentIndex(3)
        elif self.blockSize == 16384:
            self.dataSizePopup.setCurrentIndex(4)
        elif self.blockSize == 65536:
            self.dataSizePopup.setCurrentIndex(5)
        
        self.scaleTxt = QtWidgets.QLabel("Plot scale")
        self.scalePopup = QtWidgets.QComboBox(objectName="Scale")
        self.scalePopup.addItem("log-dB")
        self.scalePopup.addItem("lin-dB")
        self.scalePopup.addItem("log-lin")
        self.scalePopup.addItem("lin-lin")
        self.scalePopup.activated[str].connect(self.doPopupScale)
        
        self.windowTxt = QtWidgets.QLabel("Window")
        self.windowPopup = QtWidgets.QComboBox(objectName="Window")
        self.windowPopup.addItem("Hann")
        self.windowPopup.addItem("Hamming")
        self.windowPopup.addItem("Blackman")
        self.windowPopup.addItem("Kaiser")
        self.windowPopup.activated[str].connect(self.doPopupWindow)
        if self.winTxt == 'Hann':
            self.windowPopup.setCurrentIndex(0)
        elif self.winTxt == 'Hamming':
            self.windowPopup.setCurrentIndex(1)
        elif self.winTxt == 'Blackman':
            self.windowPopup.setCurrentIndex(2)
        elif self.winTxt == 'Kaiser':
            self.windowPopup.setCurrentIndex(3)
            
        self.lockCheckBox = QtWidgets.QCheckBox('Freeze scale')
        self.lockCheckBox.stateChanged.connect(self.doLockCheckBox)
        self.lockCheckBox.setEnabled(True)
        
        self.serverTxt = QtWidgets.QLabel("Server address")
        self.serverInput = QtWidgets.QLineEdit(self.serverAddress, objectName="Server")
        self.serverInput.returnPressed.connect(self.doServerAddressText)
        
        
        self.connectButton.setFixedWidth(100)
        self.shutDownButton.setFixedWidth(100)
        #self.closeButton.setFixedWidth(100)
        self.freqInput.setFixedWidth(100)
        self.dataSizePopup.setFixedWidth(100)
        self.avePopup.setFixedWidth(150)
        self.scalePopup.setFixedWidth(150)
        self.windowPopup.setFixedWidth(150)
        self.serverInput.setFixedWidth(200)
        self.sampPopup.setFixedWidth(150)
        
        mainContainer = QtWidgets.QWidget(self)
        self.setCentralWidget(mainContainer)
        self.setWindowTitle("Audio Analyzer")
        
        layout1 = QtWidgets.QVBoxLayout()
        layout1.setSpacing(0)
        layout1.addWidget(self.freqTxt)
        layout1.addSpacing(5)
        layout1.addWidget(self.freqInput)
        layout1.addSpacing(5)
        layout1.addWidget(self.generatorCheckBox)
        layout1.addSpacing(15)
        layout1.addWidget(self.sampTxt)
        layout1.addWidget(self.sampPopup)
        layout1.addSpacing(15)
        layout1.addWidget(self.dataSizeTxt)
        layout1.addWidget(self.dataSizePopup)
        layout1.addSpacing(15)
        layout1.addWidget(self.aveTxt)
        layout1.addWidget(self.avePopup)
        layout1.addSpacing(15)
        layout1.addWidget(self.scaleTxt)
        layout1.addWidget(self.scalePopup)
        layout1.addSpacing(15)
        layout1.addWidget(self.windowTxt)
        layout1.addWidget(self.windowPopup)
        layout1.addSpacing(15)
        layout1.addWidget(self.lockCheckBox)
        layout1.addStretch(1)
        layout1.addWidget(self.serverTxt)
        layout1.addWidget(self.serverInput)
        layout1.addSpacing(5)
        layout1.addWidget(self.connectButton)
        layout1.addSpacing(15)
        layout1.addWidget(self.shutDownButton)
        #layout1.addWidget(self.closeButton)
        
        
        layout2 = QtWidgets.QVBoxLayout()
        layout2.addWidget(self.toolbar)
        layout2.addWidget(self.canvas)
        
        layout3 = QtWidgets.QHBoxLayout()
        layout3.addLayout(layout1)
        layout3.addLayout(layout2)
        
        self.center()
        mainContainer.setLayout(layout3)
        self.show()
        
        self.canvas.initPlot(self.frequencies[:self.dataLen], 
                             self.measurementData[:self.dataLen], 
                             (self.minFreq, self.maxFreq))

        # Setup a timer to trigger the redraw by calling update.
        self.timer = QtCore.QTimer()
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.update)
        #self.timer.start()
        
        self.connected = False
        
        self.freezeScale = False
        
    def closeEvent(self, e):
        
        print("Closing...")
        if self.connected:
            self.socket.close()
        
    def keyPressEvent(self, e):
        """
        Window closes when we press Esc
        Not sure this is what we want eventually
        """
        if e.key() == QtCore.Qt.Key_Escape:
            self.close()
            
    def doGeneratorCheckBox(self):
        
        sender = self.sender()
        if sender.isChecked():
            self.generatorActive = True
            if self.connected:
                res = self.socket.sendCmd('startGen')
        else:
            self.generatorActive = False
            if self.connected:
                res = self.socket.sendCmd('stopGen')
                
    def doLockCheckBox(self):
        
        sender = self.sender()
        if sender.isChecked():
            self.freezeScale = True
        else:
            self.freezeScale = False
        
    def doConnectButton(self):
        
        sender = self.sender()
        if sender.text() == 'Connect':
            try:
                self.socket = DataSocket(self.blockSize)
                self.socket.connect(self.serverAddress, 10000)
                res = self.socket.sendCmd('dataSize', self.blockSize)
                self.socket.sendCmd('startSend')
                sender.setText('Disconnect')
                self.serverInput.setEnabled(False)
                self.shutDownButton.setEnabled(True)
                self.connected = True
                self.timer.start()
                self.generatorCheckBox.setEnabled(True)
            except:
                print("Connection failed!")
                self.connected = False
        elif sender.text() == 'Disconnect':
            try:
                self.socket.close()
                self.connected = False
                self.timer.stop()
                sender.setText('Connect')
                #self.serverTxt.setEnabled(True)
                self.serverInput.setEnabled(True)
                self.shutDownButton.setEnabled(False)
                self.generatorCheckBox.setEnabled(False)
                self.generatorCheckBox.setCheckState(0)
            except:
                print("Disconnect failed!")
            
        #print("Connect "+sender.text())
        
    def doShutDownButton(self):
        
        sender = self.sender()
        
        msg = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Information)
        msg.setWindowTitle("Shutdown")
        msg.setInformativeText("Are you sure you want to shut down?")
        #msg.setDetailedText("Are you sure you want to shut down?")
        msg.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
        #msg.buttonClicked.connect(msgbtn)
        
        retval = msg.exec_()
        if retval == QtWidgets.QMessageBox.Ok:
            pTxt = "ssh pi@"+self.serverAddress+" sudo shutdown -h now"
            subprocess.Popen(pTxt, shell=True,stdout=subprocess.PIPE, 
                             stderr=subprocess.PIPE).communicate()
        #elif retval == QtWidgets.QMessageBox.Cancel:
        #    print("Cancel")
        
    def doFrequencyText(self):
        
        sender = self.sender()
        
        f = float(sender.text())
        if (f >= 20) and (f <= 20000):
            cycles = np.round(self.blockSize * f / self.samplingRate)
            cycles = np.floor(cycles / 2) * 2 + 1
            self.generatorFrequency = cycles * self.samplingRate / self.blockSize
            if self.connected:
                res = self.socket.sendCmd('frequency', self.generatorFrequency)
        
    def doServerAddressText(self):
        
        sender = self.sender()
        self.serverAddress = sender.text()
        #print("Server address "+sender.text())
        
    def doPopupSamplingFreq(self, text):
        
        oldSamp = self.samplingRate
        if text == '44100':
            self.samplingRate = 44100
        elif text == '48000':
            self.samplingRate = 48000
        elif text == '88200':
            self.samplingRate = 88200
        elif text == '96000':
            self.samplingRate = 96000
        elif text == '192000':
            self.samplingRate = 192000
            
        self.maxFreq = self.samplingRate/2
        
        if (oldSamp != self.samplingRate) and self.connected:
            res = self.socket.sendCmd('fs', self.samplingRate)
            
        self.measurementData = np.ones(self.blockSize) * np.finfo(float).eps
        
        self.bufIdx = 0
        self.dataBuf = np.zeros((self.blockSize, self.averaging))
        
        self.frequencies = np.arange(self.blockSize) / self.blockSize * self.samplingRate
        self.dataLen = int(self.blockSize/2) + 1
        
        self.canvas.axes.cla()
        self.canvas.initPlot(self.frequencies[:self.dataLen], 
                             self.measurementData[:self.dataLen], 
                             (self.minFreq, self.maxFreq))
        
        
    def doPopupAverage(self, text):
        
        self.averaging = int(text)
        self.bufIdx = 0
        self.dataBuf = np.zeros((self.blockSize, self.averaging))
        
    def doPopupDataSize(self, text):
        
        self.blockSize = int(text)
        
        if self.winTxt == 'Hann':
            self.win = hann(self.blockSize)
        elif self.winTxt == 'Hamming':
            self.win = hamming(self.blockSize)
        elif self.winTxt == 'Blackman':
            self.win = blackman(self.blockSize)
        elif self.winTxt == 'Kaiser':
            self.win = kaiser(self.blockSize, kaiserBeta)
        
        if self.connected:
            res = self.socket.sendCmd('dataSize', self.blockSize)
            self.socket.setDataLen(self.blockSize)
        
        self.measurementData = np.ones(self.blockSize) * np.finfo(float).eps
        
        self.bufIdx = 0
        self.dataBuf = np.zeros((self.blockSize, self.averaging))
        
        self.frequencies = np.arange(self.blockSize) / self.blockSize * self.samplingRate
        self.dataLen = int(self.blockSize/2) + 1
        
        self.canvas.axes.cla()
        self.canvas.initPlot(self.frequencies[:self.dataLen], 
                             self.measurementData[:self.dataLen], 
                             (self.minFreq, self.maxFreq))
        
    def doPopupScale(self, text):
        
        print("Scale "+text)
        
    def doPopupWindow(self, text):
        
        self.winTxt = text
        if self.winTxt == 'Hann':
            self.win = hann(self.blockSize)
        elif self.winTxt == 'Hamming':
            self.win = hamming(self.blockSize)
        elif self.winTxt == 'Blackman':
            self.win = blackman(self.blockSize)
        elif self.winTxt == 'Kaiser':
            self.win = kaiser(self.blockSize, kaiserBeta)
        #print("Window "+text)
        
    def center(self):
        qr = self.frameGeometry()
        cp = QtWidgets.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())
        
    def getHarmonics(self, f, data, fc):
        
        n = int(2e4 / fc)
        h = np.zeros((n-1, 2))
        for i in range(n-1):
            fn = fc * (i + 2)
            ind = np.where(f < fn)[0][-1]
            h[i,0] = fn
            h[i,1] = np.max(data[(ind-5):(ind+6)])
            
        return h

    def update(self):
        
        # Acquire data
        #self.measurementData = np.abs(np.random.randn(self.blockSize))
        if self.connected:
            data = self.socket.receiveData()
            if len(data) > 0:
                self.measurementData = np.abs(np.fft.fft(data * self.win))
                #self.measurementData /= np.max(self.measurementData)
            self.socket.sendCmd('idle')
        
        if len(self.measurementData) == self.blockSize:
            self.dataBuf[:,self.bufIdx % self.averaging] = self.measurementData
            if self.bufIdx == 0:
                data = self.dataBuf[:,0]
            elif self.bufIdx < self.averaging:
                data = np.mean(self.dataBuf[:,:self.bufIdx], axis=1)
            else:
                data = np.mean(self.dataBuf, axis=1)
        
            self.bufIdx += 1
        
            measurementData = {}
            measurementData['THD'] = 0
            measurementData['Noise'] = 0
            if not self.freezeScale:
                self.maxVal = np.max(data[:self.dataLen])
                ind = np.argmax(data[:self.dataLen])
                fMax = self.frequencies[:self.dataLen][ind]
                harmonics = self.getHarmonics(self.frequencies[:self.dataLen], data[:self.dataLen], fMax)
                harmonics[:,1] /= self.maxVal
                measurementData['THD'] = np.sqrt(np.sum(harmonics[:,1]**2)) * 100
            else:
                harmonics = None
            #print(maxVal)
            self.canvas.updatePlot(self.frequencies[:self.dataLen], 
                                   data[:self.dataLen]/self.maxVal, measurementData,
                                   (self.minFreq, self.maxFreq), harmonics)
            self.canvas.draw()


app = QtWidgets.QApplication(sys.argv)
w = MainWindow(app)
app.exec_()
#w.close()
app.quit()