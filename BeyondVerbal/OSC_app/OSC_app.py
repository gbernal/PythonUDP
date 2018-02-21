#!/usr/bin/python
import sys, struct, serial , socket
from OSC import OSCClient, OSCMessage
import requests,threading
from socketIO_client import SocketIO, LoggingNamespace
import pyaudio
import time
import wave

requests.packages.urllib3.disable_warnings()

cs= socket.socket(socket.AF_INET , socket.SOCK_DGRAM)

BEYOND_API_KEY = "38978d95-7bc7-4e87-b909-b34f234d6a8a"

UDP_IP_ADDRESS = "127.0.0.1"
UDP_PORT_NO = 6789
#///// Voice emotion component begins //////////
def emotionMapping(analysis): # Neutral
    # Happy
    # Sad
    # Angry
    # excitement
    attributes = analysis.keys()
    neutral = True
    happy = True
    angry = True
    sad = True
    #excitement = True
    modes = [analysis[attr]['Mode'] for attr in attributes] 

    print modes
    for attr in attributes:
        mode = analysis[attr]['Mode']
        if attr == 'Valence':
            neutral = neutral and (mode == 'neutral' or mode == 'positive')
            happy = happy and (mode == 'positive')
            sad = sad and (mode == 'negative')
            # angry = angry and (mode == 'negative')
            # [0 1 1]
            # [0 0 1]
            # [1 0 0]
            # [1 0 0]
            #excitement = excitement and (mode == 'neutral')
            #fear = fear and (mode == 'negative')
        elif attr == 'Arousal':
            neutral = neutral and (mode == 'neutral' or mode == 'low')
            happy = happy and (mode == 'neutral' or mode == 'high')   
            sad = sad and (mode == 'neutral' or mode == 'low')
            angry = angry and (mode == 'neutral' or mode == 'high')
            # [1 1 0]
            # [0 1 1]
            # [1 1 0]
            # [0 0 1]
            #excitement = excitement and (mode == 'high')
            #fear = fear and (mode == 'high')
        else: # Temper
            neutral = neutral and (mode == 'low')
            # neutral = neutral and (mode == 'medium' or mode == 'low')
            happy = happy and (mode == 'medium')
            sad = sad and (mode == 'low')
            angry = angry and (mode == 'high')

            # [1 0 0]
            # [0 1 0]
            # [1 0 0]
            # [0 0 1]
            #excitement = excitement and (mode == 'medium')
            #fear = fear and (mode == 'low' or mode == 'high')

    # Edge Case: [negative, neutral/low, medium/high]       -->         angry
    # Edge Case: [negative, high, low/medium]               -->         sad
    
    # Edge Case: [neutral, low, low]                        -->         sad
    # Edge Case: [neutral, low/neutral, medium/high]        -->         neutral
    # Edge Case: [neutral, high, low/medium/high]           -->         neutral
    
    # Edge Case: [positive, high, low/medium/high]          -->         happy
    # Edge Case: [positive, neutral, high]                  -->         happy
    # Edge Case: [positive, low, medium/high]               -->         neutral

    sad = sad or (modes[1] == 'negative' and modes[0] == 'high' and (modes[2] == 'medium' or  modes[2] == 'low'))
    if (modes[1] == 'neutral' and modes[0] == 'low' and modes[2] == 'low'):
        sad = True
        neutral = False

    angry = angry or (modes[1] == 'negative' and (modes[0] == 'low' or modes[0] == 'medium') and (modes[2] == 'medium' or modes[2] == 'high'))

    #happy = happy or (modes[1] == 'positive' and modes[0] == 'high')
    #happy = happy or (modes[1] == 'positive' and modes[0] == 'medium')

    mapping = dict(neutral=neutral, happy=happy, sad=sad, angry=angry)
    print mapping

    if reduce(lambda x, y: not x and not y, mapping.values()): mapping['neutral'] = True
    recognizedEmotion = 0
    for emo in mapping:
        if mapping[emo]:
            recognizedEmotion = emo 
            print emo
    OSCmap = dict(neutral=0, happy=1, sad=2, angry=3)
    return OSCmap[recognizedEmotion]
            

def results(*args):
    return
    #data = args['result']['analysisSummary']['AnalysisResult']
    #print(data)

def post(recordingId,headers,wavdata,e):
    global client,UDP_IP_ADDRESS,UDP_PORT_NO
    r =requests.post("https://apiv3.beyondverbal.com/v3/recording/"+recordingId,data=wavdata, verify=False, headers=headers)
    e.set()
    # Response from beyond verbal server
    data = r.json()
    print data
    # Read out the analysis summary portion of the response
    analysisSummary = None
    sp = "!!,"

    if 'analysisSummary' in data['result']:
        #print data['result']
        analysisSummary = data['result']['analysisSummary']['AnalysisResult']
        recognizedEmotion = emotionMapping(analysisSummary)
        print recognizedEmotion
        sp += str(recognizedEmotion)
        cs.sendto(sp, (UDP_IP_ADDRESS, UDP_PORT_NO))

    print analysisSummary


    #print result full analysis : 
    #print(r.json())

def analyze(API_Key,wavdata):
    wavdata1 = open(wavdata,'rb')
    with SocketIO("http://analysis.beyondverbal.com", 80, LoggingNamespace) as socketIO:
        e = threading.Event()
        # Authentication message 
        res = requests.post("https://token.beyondverbal.com/token",data={"grant_type":"client_credentials","apiKey":API_Key},verify=False)
        token = res.json()['access_token']
        headers={"Authorization":"Bearer "+token}
        # Send Beyond Verbal API our audio data
        pp = requests.post("https://apiv3.beyondverbal.com/v3/recording/start",json={"dataFormat": { "type":"WAV" }},verify=False,headers=headers)
        recordingId = pp.json()['recordingId']
        # Whenever our socket connection has a 'update' event, call results
        socketIO.on('update', results)
        socketIO.emit('join', recordingId)
            
        
        my_thread = threading.Thread(target=post, name="post", args=(recordingId,headers,wavdata1,e))
        my_thread.start()
        socketIO.wait(seconds=5)
        while not e.is_set():
            socketIO.wait(seconds=1)
        socketIO._close()

# Realtime audio recording

recordingFile = 'test_streaming2.wav'

def startRecording():
    # instantiate PyAudio (1)
    p = pyaudio.PyAudio()

  
    
    def recordCallback(in_data, frame_count, time_info, status):
        wf = wave.open(recordingFile, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
        wf.setframerate(8000)
        wf.writeframes(in_data)
        wf.close()
        print 'Audio to file'
        thr = threading.Thread(target=analyze, args=(BEYOND_API_KEY, recordingFile), kwargs={})
        thr.start()
        return (in_data, pyaudio.paContinue)

    # open stream using callback (3)
    stream = p.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=8000,
                    input=True,
                    frames_per_buffer=1024*2*2*2*2*2*4,
                    stream_callback=recordCallback)

    # start the stream (4)
    stream.start_stream()
    return stream, p
#frames_per_buffer=1024*2*2*2*2*2*2*2*2*2*2
def stopRecording(stream, p):
    # wait for stream to finish (5)
    while stream.is_active():
        time.sleep(0.1)

    # stop stream (6)
    stream.stop_stream()
    stream.close()
    #wf.close()

    # close PyAudio (7)
    p.terminate()
#/////////// Voice components end/////////


#//// Biosignal packets rx begins //////////////////////

def wait_for_ack():
   ddata = ""
   ack = struct.pack('B', 0xff)
   while ddata != ack:
      ddata = ser.read(1)
   return

#if len(sys.argv) < 2:
#   print "No device specified."
#   print "Specify the serial port of the device you wish to connect to."
#   print "Example:"
#   print "   aAccelGsrGyro51.2Hz.py Com12"
#   print "or"
#   print "   aAccelGsrGyro51.2Hz.py /  dev/rfcomm0"
if True:
   #ser = serial.Serial(sys.argv[1], 115200)

   #ser.flushInput()
# send the set sensors command
   #ser.write(struct.pack('BBBB', 0x08, 0xC4, 0x00, 0x00))  #analog accel, gsr, MPU9150 gyro
   #wait_for_ack()
# send the set sampling rate command
   #ser.write(struct.pack('BBB', 0x05, 0x80, 0x02)) #51.2Hz (32768/640=51.2Hz: 640 -> 0x0280; has to be done like this for alignment reasons.)
   #wait_for_ack()
# send start streaming command
   #ser.write(struct.pack('B', 0x07))
   #wait_for_ack()

# read incoming data
   ddata = ""
   numbytes = 0
   framesize = 17 # 1byte packet type + 2byte timestamp + 3x2byte Analog Accel + 2byte GSR + 3x2byte MPU9150 gyro
   #code that starts the voice analyzing thread
   #code that starts the GSR reading thread
   print "Packet Type,Timestamp,Analog AccelX,Analog AccelY,Analog AccelZ,GSR Range,GSR,GyroX,GyroY,GyroZ"

   startRecording()
   
   try:
      while True:
         #while numbytes < framesize:
         #   ddata += ser.read(framesize)
         #   numbytes = len(ddata)
         
         #data = ddata[0:framesize]
         #ddata = ddata[framesize:]
         #numbytes = len(ddata)

         #(packettype,) = struct.unpack('B', data[0:1])
         #(timestamp, analogacceyx, analogacceyy, analogacceyz, gsr) = struct.unpack('HHHHH', data[1:11])
         #(gyrox, gyroy, gyroz) = struct.unpack('>hhh', data[11:framesize])
         #gsrrange = (gsr & 0xC000) >> 14
         gsr = 0xFFF
         #gsr+0.00
         #agsr = float(gsr)
         #type(agsr)
         #print agsr
         #grab the samples stored in class variables for each (GSR, voice recording)
         #if voiceAnalyzer.checkNewSample() == True:
            #your_voice_labels = voiceAnalyzer.unwrapSample()
            #client.send("sensor/voice", your_voice_labels)


         #delay(16)

         #print "0x%02x,%5d,\t%4d, %4d, %4d,\t%d, %4d,\t%4d, %4d, %4d" % (packettype, timestamp, analogacceyx, analogacceyy, analogacceyz, gsrrange, gsr, gyrox, gyroy, gyroz)
         #client.send( OSCMessage("agsr", [agsr] ) )
   except KeyboardInterrupt:
#send stop streaming command
      #ser.write(struct.pack('B', 0x20))
      #wait_for_ack()
#close serial port
      #ser.close()
      print
      print "All done!"
