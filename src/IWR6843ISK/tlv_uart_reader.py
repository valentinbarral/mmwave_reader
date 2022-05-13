import struct
import sys
import serial
import binascii
import time
import numpy as np
import math
import fft
from operator import add
from enum import Enum

class LabId(Enum):
    OutOfBoxDemo = 0
    PeopleCounting3D = 1

class TLVUartReader():
    def __init__(self,type='SDK Out of Box Demo'):
        self.headerLength = 52
        self.magicWord = 0x708050603040102
        self.labId = 0
        #TODO: get the next from config file or parameter
        self.num_azimuth_antennas = 8
        self.range_fft_size = 256
        self.dopplerBins = 16
        
        if (type=="SDK Out of Box Demo"):
            self.labId = LabId.OutOfBoxDemo
        elif (type=='3D People Counting'):
            self.labId = LabId.PeopleCounting3D

    def connectComPorts(self, uartCom, dataCom):
        self.uartCom = serial.Serial(uartCom, 115200,parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE,timeout=0.3)
        self.dataCom = serial.Serial(dataCom, 921600,parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE,timeout=0.025)
        self.dataCom.reset_output_buffer()
        print('Connected')

    def sendCfgOverwriteSensorPosition(self, cfg, sensor_height, elev_tilt):
        for line in cfg:
            if (line.startswith('sensorPosition')):
                self.sendLine('sensorPosition %f 0 %f\n'%(sensor_height, elev_tilt))
            else:
                self.sendLine(line)
        time.sleep(3)
        self.uartCom.reset_input_buffer()
        self.uartCom.close()


    def sendCfg(self, cfg):
        for line in cfg:
            self.sendLine(line)
        time.sleep(3)
        self.uartCom.reset_input_buffer()
        self.uartCom.close()

    #send single command to device over UART Com.
    def sendLine(self, line):
        if (not line[0]=='%'):
            time.sleep(.1)
            print(line)
            self.uartCom.write(line.encode())
            ack = self.uartCom.readline()
            #print(ack)
            ack = self.uartCom.readline()
            print(str(ack))


    def readAndParseUart(self):
        numDetectedObj = 0
        self.fail = 0
        self.byteData = bytes(1)
        numBytes = 0
        if (self.labId == LabId.OutOfBoxDemo):
            numBytes = 8192
        elif (self.labId == LabId.PeopleCounting3D):
            numBytes = 4666

        data = self.dataCom.read(numBytes)
        if (self.byteData is None):
            self.byteData = data
        else:
            self.byteData += data
        dataTosend = None
        if (self.labId == LabId.OutOfBoxDemo):
            dataTosend, numTLVs, tlvHeaderLength, numDetectedObj= self.parseOutOfBoxTLVHeader(self.byteData)
        elif (self.labId == LabId.PeopleCounting3D):
            dataTosend, numTLVs, tlvHeaderLength = self.parsePeople3DHeader(self.byteData)

        return self.fail, dataTosend, numTLVs, tlvHeaderLength, numDetectedObj



    def parseOutOfBoxTLVHeader(self, dataIn):
        headerStruct = 'Q8I'
        headerLength = struct.calcsize(headerStruct)
        tlvHeaderLength = 8
        #search until we find magic word
        while(1):
            try:
                magic, version, totalPacketLen, platform, self.frameNum, timeCPUCycles, numDetectedObj, numTLVs, subFrameNum = struct.unpack(headerStruct, dataIn[:headerLength])
                
            except:
                #bad data, return
                self.fail = 1
                return dataIn,0,0,0
            if (magic != self.magicWord):
                #wrong magic word, increment pointer by 1 and try again
                dataIn = dataIn[1:]
            else:
                #we have correct magic word, proceed to parse rest of data
                break
        #print('Total Packet length: %d numTLVs: %d'%(totalPacketLen, numTLVs))
        #print('HeaderLength: %d'%(headerLength))
        dataIn = dataIn[headerLength:]
        remainingData = totalPacketLen - len(dataIn)
        #print('Total Packet length (without header): %d'%(remainingData))
        count = 0
        while (remainingData > 0):
            newData = self.dataCom.read(remainingData)
            remainingData = totalPacketLen - len(dataIn) - len(newData)
            dataIn += newData
            count += 1

        #print('Size of result after read all: %d'%(len(result)))
        return dataIn, numTLVs, tlvHeaderLength, numDetectedObj

    def parsePeople3DHeader(self, dataIn):
        #reset point buffers
        self.numDetectedTarget = 0
        self.numDetectedObj = 0
        self.indexes = []
        tlvHeaderLength = 8
        headerLength = 48
        #stay in this loop until we find the magic word or run out of data to parse
        while (1):
            try:
                magic, version, packetLength, platform, frameNum, subFrameNum, chirpMargin, frameMargin, uartSentTime, trackProcessTime, numTLVs, checksum =  struct.unpack('Q9I2H', dataIn[:headerLength])
            except Exception as e:
                #bad data, return
                #print("Cannot Read Frame Header")
                #print(e)
                self.fail = 1
                return dataIn,0,0
            if (magic != self.magicWord):
                #wrong magic word, increment pointer by 1 and try again
                dataIn = dataIn[1:]
            else:
                #got magic word, proceed to parse
                break
        
        
        #print('HeaderLength: %d'%(headerLength))
        dataIn = dataIn[headerLength:]
        remainingData = packetLength - len(dataIn) - headerLength
        count = 0
        while (remainingData > 0):
            newData = self.dataCom.read(remainingData)
            remainingData = packetLength - len(dataIn) - len(newData) - headerLength
            dataIn += newData
            count += 1
        #print('Total Packet length: %d numTLVs: %d'%(packetLength, numTLVs))
        return dataIn, numTLVs, tlvHeaderLength