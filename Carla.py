
#!/usr/bin/env python3

import boto3
import openai
import os
import pvcobra
import pvleopard
import pvporcupine
import pyaudio
import random
import struct
import sys
import textwrap
import threading
import time

import RPi.GPIO as GPIO

from os import environ
environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame

from colorama import Fore, Style
from openai import OpenAI
from pvleopard import *
from pvrecorder import PvRecorder
from threading import Thread, Event
from time import sleep

GPIO.setwarnings(False)

GPIO.setmode(GPIO.BCM)
led1_pin=18

GPIO.setup(led1_pin, GPIO.OUT)
GPIO.output(led1_pin, GPIO.LOW)

audio_stream = None
cobra = None
pa = None
polly = boto3.client('polly')
porcupine = None
recorder = None
wav_file = None

GPT_model = "gpt-3.5-turbo"
openai.api_key = "inserisci la tua chiave API segreta tra queste virgolette"
pv_access_key= "inserisci la tua chiave API segreta tra queste virgolette"

client = OpenAI(api_key=openai.api_key)

prompt = ["Come posso aiutarti?",
    "Come posso aiutare?",
    "Chiedimi qualunque cosa.",
    "Cosa posso fare per te?",
    "Si?",
    "Sto ascoltando.",
    "Sono qui.",
    "Cosa vorresti che facessi?"]

chat_log=[
    {"role": "system", "content": "Ti chiami  Carla. Sei un assistente prezioso. Se ti viene chiesto di te stesso, includi il tuo nome nella risposta."},
    ]

def ChatGPT(query):
    user_query = [
        {"role": "user", "content": query},
        ]         
    send_query = (chat_log + user_query)
    response = client.chat.completions.create(
    model=GPT_model,
    messages=send_query
    )
    answer = response.choices[0].message.content
    chat_log.append({"role": "assistant", "content": answer})
    return answer
    
def responseprinter(chat):
    wrapper = textwrap.TextWrapper(width=70)  # Regola la larghezza secondo le tue preferenze
    paragraphs = res.split('\n')
    wrapped_chat = "\n".join([wrapper.fill(p) for p in paragraphs])
    for word in wrapped_chat:
       time.sleep(0.06)
       print(word, end="", flush=True)
    print()

#Carla "ricorderà" le domande precedenti in modo da avere maggiore continuità nella risposta
#quanto segue cancellerà quella 'memoria' cinque minuti dopo l'inizio della conversazione
def append_clear_countdown():
    sleep(300)
    global chat_log
    chat_log.clear()
    chat_log=[
        {"role": "system", "content": "Ti chiami Carla. Sei un assistente prezioso. Se ti viene chiesto di te stesso, includi il tuo nome nella risposta."},
        ]    
    global count
    count = 0
    t_count.join

def voice(chat):
   
    voiceResponse = polly.synthesize_speech(Text=chat, OutputFormat="mp3",
                    VoiceId="Carla") #su AWS altre voci disponibili oltre a Carla, sono Bianca e Giorgio
    if "AudioStream" in voiceResponse:
        with voiceResponse["AudioStream"] as stream:
            output_file = "speech.mp3"
            try:
                with open(output_file, "wb") as file:
                    file.write(stream.read())
            except IOError as error:
                print(error)

    else:
        print("non funziona")

    pygame.mixer.init()     
    pygame.mixer.music.load(output_file)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pass
    sleep(0.2)

def fade_leds(event):
    pwm1 = GPIO.PWM(led1_pin, 200)

    event.clear()

    while not event.is_set():
        pwm1.start(0)
        for dc in range(0, 101, 5):
            pwm1.ChangeDutyCycle(dc)  
            time.sleep(0.05)
        time.sleep(0.75)
        for dc in range(100, -1, -5):
            pwm1.ChangeDutyCycle(dc)                
            time.sleep(0.05)
        time.sleep(0.75)
        
def wake_word():
    
    keywords = ["Carla"]
    porcupine = pvporcupine.create(keywords=keywords,
                            access_key=pv_access_key,
                            sensitivities=[0.1], #da 0 a 1.0 - un numero più alto riduce il tasso di errori a scapito di un aumento dei falsi allarmi
                                   )
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    sys.stderr.flush()
    os.dup2(devnull, 2)
    os.close(devnull)
    
    wake_pa = pyaudio.PyAudio()

    porcupine_audio_stream = wake_pa.open(
                    rate=porcupine.sample_rate,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=porcupine.frame_length)
    
    Detect = True

    while Detect:
        porcupine_pcm = porcupine_audio_stream.read(porcupine.frame_length)
        porcupine_pcm = struct.unpack_from("h" * porcupine.frame_length, porcupine_pcm)

        porcupine_keyword_index = porcupine.process(porcupine_pcm)

        if porcupine_keyword_index >= 0:

            GPIO.output(led1_pin, GPIO.HIGH)
            keyword = keywords[porcupine_keyword_index]
            print(Fore.GREEN + "\n" + keyword + " detected\n")
            porcupine_audio_stream.stop_stream
            porcupine_audio_stream.close()
            porcupine.delete()         
            os.dup2(old_stderr, 2)
            os.close(old_stderr)
            Detect = False

def listen():

    cobra = pvcobra.create(access_key=pv_access_key)

    listen_pa = pyaudio.PyAudio()

    listen_audio_stream = listen_pa.open(
                rate=cobra.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=cobra.frame_length)

    print("Sono in Ascolto...")

    while True:
        listen_pcm = listen_audio_stream.read(cobra.frame_length)
        listen_pcm = struct.unpack_from("h" * cobra.frame_length, listen_pcm)
           
        if cobra.process(listen_pcm) > 0.3:
            print("Rilevamento voce")
            listen_audio_stream.stop_stream
            listen_audio_stream.close()
            cobra.delete()
            break

def detect_silence():

    cobra = pvcobra.create(access_key=pv_access_key)

    silence_pa = pyaudio.PyAudio()

    cobra_audio_stream = silence_pa.open(
                    rate=cobra.sample_rate,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=cobra.frame_length)

    last_voice_time = time.time()

    while True:
        cobra_pcm = cobra_audio_stream.read(cobra.frame_length)
        cobra_pcm = struct.unpack_from("h" * cobra.frame_length, cobra_pcm)
           
        if cobra.process(cobra_pcm) > 0.2:
            last_voice_time = time.time()
        else:
            silence_duration = time.time() - last_voice_time
            if silence_duration > 1.3:
                print("Fine della Domanda rilevata\n")
                GPIO.output(led1_pin, GPIO.LOW)
                cobra_audio_stream.stop_stream                
                cobra_audio_stream.close()
                cobra.delete()
                last_voice_time=None
                break

class Recorder(Thread):
    def __init__(self):
        super().__init__()
        self._pcm = list()
        self._is_recording = False
        self._stop = False

    def is_recording(self):
        return self._is_recording

    def run(self):
        self._is_recording = True

        recorder = PvRecorder(device_index=-1, frame_length=512)
        recorder.start()

        while not self._stop:
            self._pcm.extend(recorder.read())
        recorder.stop()

        self._is_recording = False

    def stop(self):
        self._stop = True
        while self._is_recording:
            pass

        return self._pcm

try:

    o = create(
        access_key=pv_access_key,
        enable_automatic_punctuation = True,
        )
    
    event = threading.Event()

    count = 0

    while True:
        
        try:
        
            if count == 0:
                t_count = threading.Thread(target=append_clear_countdown)
                t_count.start()
            else:
                pass   
            count += 1
            wake_word()
# commenta la riga successiva se non vuoi che Carla risponda con il suo nome       
            voice(random.choice(prompt))
            recorder = Recorder()
            recorder.start()
            listen()
            detect_silence()
            transcript, words = o.process(recorder.stop())
            t_fade = threading.Thread(target=fade_leds, args=(event,))
            t_fade.start()
            recorder.stop()
            print(transcript)
            (res) = ChatGPT(transcript)
            print("\nLa risposta di ChatGPT è:\n")        
            t1 = threading.Thread(target=voice, args=(res,))
            t2 = threading.Thread(target=responseprinter, args=(res,))
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)       
            recorder.stop()
            o.delete
            recorder = None

        except openai.APIError as e:
            print("\nSi è verificato un errore API.  Riprova tra qualche minuto.")
            voice("\nSi è verificato un errore  API .  Riprova tra qualche minuto.")
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)        
            recorder.stop()
            o.delete
            recorder = None
            sleep(1)

        except openai.RateLimitError as e:
            print("\nHai raggiunto il limite di tariffa assegnato.")
            voice("\nHai raggiunto il limite di tariffa assegnato.")
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)        
            recorder.stop()
            o.delete
            recorder = None
            break

        except openai.APIConnectionError as e:
            print("\nHo problemi con la connessione API.  Controlla la connessione di rete e riprova.")
            voice("\nHo problemi con la connessione A P I.  Controlla la connessione di rete e riprova.")
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)        
            recorder.stop()
            o.delete
            recorder = None
            sleep(1)

        except openai.AuthenticationError as e:
            print("\nLa tua API o o token  OpenAI non  è valida, scaduta, o revocata.  Per favore risolvi questo problema e poi riavvia il mio programma.")
            voice("\nLa tua API o tocken OpenAI non è valida, scaduta, o revocata. Per favore risolvi questo problema e poi riavvia il mio programma.")
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)       
            recorder.stop()
            o.delete
            recorder = None
            break
     
except KeyboardInterrupt:
    print("\nUscita dall'assistente virtuale ChatGPT")
    o.delete
    GPIO.cleanup()
