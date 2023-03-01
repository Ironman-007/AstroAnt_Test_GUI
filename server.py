from glob import glob
from unittest import skip
import serial
from serial.tools.list_ports_posix import comports
import crc8
from cobs import cobs
import time
import threading
import struct
import socketio
from flask import Flask, send_from_directory
import os
import shutil
import zipfile
from os import listdir
from os.path import isfile, join

sio = socketio.Server(async_mode='threading')
app = Flask(__name__)
app.wsgi_app = socketio.WSGIApp(sio, app.wsgi_app)

# define serial baudrate constants
BAUDRATE = 115200

# mapping destination strings to bytes
destination_dictionary = {
    'CentralStation 0x91': 0x91,
    'AstroAnt 0x92': 0x92
}

# mapping command strings to bytes
command_dictionary = {
    'CentralStation 0x91': {
        'cs_garage_opened_com 0x11': 0x11,
        'cs_rover_not_turning_com 0x12': 0x12,
        'cs_rover_will_turn_com 0x13': 0x13,
        'cs_ping_com 0x14': 0x14,
        'cs_enter_dfu_ble_com 0x15': 0x15,
        'cs_enter_dfu_serial_com 0x16': 0x16,
        'cs_update_ant_init_com 0x17': 0x17,
        'cs_update_ant_fw_packet_com 0x18': 0x18
    },
    'AstroAnt 0x92': {
        'ant_ping_com 0x01': 0x01,
        'ant_start_com 0x02': 0x02,
        'ant_calibrate_com 0x03': 0x03,
        'ant_ota_com 0x04': 0x04,
        'ant_stop_com 0x05': 0x05,
        'ant_off_com 0x06': 0x06,
        'ant_heater_on_com 0x07': 0x07,
        'ant_heater_off_com 0x08': 0x08,
        'ant_move_fwd_com 0x09': 0x09,
        'ant_move_bwd_com 0x0A': 0x0A
    }
}

# global sequence counter to count up commands sent
sequence_number = 0

# rss422 serial handle
rss422_serial = None
astro_ant_serial = None

# handle recording
is_recording = False
recording_file = None

# utility method to compute crc8 of commands
def crc(command):
    hash = crc8.crc8()
    hash.update(command)
    return hash.digest()[0]

# returns the current sequence number
def get_sequence_number():
    global sequence_number
    current_sequence_number = sequence_number
    sequence_number = sequence_number + 1 if sequence_number + 1 <= 255 else 0
    return current_sequence_number.to_bytes(1, 'little')[0]

DFU = False

# listen for RSS422 data and send socket when received new command
def listen_for_rss422_data():
    global rss422_serial
    global is_recording
    global DFU_CENTRAL
    rss422_receive_buffer = bytearray()

    while True:
        while (rss422_serial.in_waiting > 0):
            new_byte = rss422_serial.read(1)[0]
            rss422_receive_buffer.append(new_byte)

            try:
                decoded = cobs.decode(rss422_receive_buffer[0:len(rss422_receive_buffer) - 1])
                if (new_byte == 0x00):
                    i = int(decoded[7])
                    sio.emit('command_received', {
                        "command": list(map(lambda x: format(x, "02X"), decoded)),
                        "corrupt": ((i >> 6) & 1) == 1
                        # getting your message as int
                    })

                    if is_recording:
                        recording_file.write("RECEIVED," + str(','.join(list(map(lambda x: format(x, "02X"), decoded)))) + "\n")

                    sio.emit('log', "RECEIVED - " + str(list(map(lambda x: format(x, "02X"), decoded))))

                    if decoded[7] == 0x94 or decoded[7] == 0x99:
                        sio.emit('command_cs_ping_received_decoded', {
                            'time': int.from_bytes(decoded[2:6], "little"),
                            'rtd': int.from_bytes(decoded[17:19], "little"),
                            'v5': decoded[19],
                            'vcc': decoded[20],
                            'fram': decoded[21],
                            'accel_x': round(struct.unpack('<f', decoded[22:26])[0], 3),
                            'accel_y': round(struct.unpack('<f', decoded[26:30])[0], 3),
                            'accel_z': round(struct.unpack('<f', decoded[30:34])[0], 3),
                            'heater_output': decoded[34]
                        })
                    if decoded[7] == 0x99 or decoded[7] == 0x81 or decoded[7] == 0x82 or decoded[7] == 0x84 or decoded[7] == 0x89 or decoded[7] == 0x8A:
                        offset = 0
                        if decoded[7] == 0x99:
                            print("ofsetting data")
                            offset = 37

                        sio.emit('command_ant_packet_received_decoded', {
                        # print({
                            'time': int.from_bytes(decoded[2:6], "little"),
                            'AAX_VAL': round(struct.unpack('<f', decoded[36 + offset:40 + offset])[0], 3),
                            'AAY_VAL': round(struct.unpack('<f', decoded[40 + offset:44 + offset])[0], 3),
                            'AAZ_VAL': round(struct.unpack('<f', decoded[44 + offset:48 + offset])[0], 3),
                            'AGX_VAL': round(struct.unpack('<f', decoded[24 + offset:28 + offset])[0], 3),
                            'AGY_VAL': round(struct.unpack('<f', decoded[28 + offset:32 + offset])[0], 3),
                            'AGZ_VAL': round(struct.unpack('<f', decoded[32 + offset:36 + offset])[0], 3),
                            'ACT_VAL': round(struct.unpack('<f', decoded[48 + offset:52 + offset])[0], 3),
                            'ACAT_VAL': round(struct.unpack('<f', decoded[52 + offset:56 + offset])[0], 3),
                            'BAT_V_VAL': int.from_bytes(decoded[21 + offset:22 + offset], "little"),
                            'APT_VAL': int.from_bytes(decoded[17 + offset:19 + offset], "little"),
                            'ARTD_VAL': int.from_bytes(decoded[19 + offset:21 + offset], "little"),
                            'AFRAM_VAL': int.from_bytes(decoded[22 + offset:24 + offset], "little"),
                            'ASTEP_VAL': int.from_bytes(decoded[48 + offset:50 + offset], "little"),
                            # FZ
                            # 'A_PID_DIR_VAL': int.from_bytes(decoded[56 + offset:60 + offset], "little"),
                            'A_PID_DIR_VAL': (struct.unpack('<f', decoded[56 + offset:60 + offset])[0] * 57.3),
                            'A_PID_STEER_VAL': int.from_bytes(decoded[61 + offset:62 + offset], "little"),
                            'A_HEATER_VAL': int.from_bytes(decoded[64 + offset:65 + offset], "little"),
                            'A_RSSI_VAL': int.from_bytes(decoded[65 + offset:66 + offset], "little", signed=True),
                        })

                    if decoded[7] == 0x97 or decoded[7] == 0x98:
                        write_command(None, {
                            "destination": "CentralStation 0x91",
                            "command_type": "cs_update_ant_fw_packet 0x18",
                            "firmware_packet": None 
                        })

                    rss422_receive_buffer = bytearray()
            except cobs.DecodeError:
                pass
     
def listen_for_astro_ant_data():
    global astro_ant_serial

    while True:

        line = astro_ant_serial.readline()
        line = str(line).replace("\\n", "").replace("\"", "").replace("\\r", "")
        sio.emit('antLog', line[1:])

# returns the list of available serial ports
@sio.on('get_serial_ports')
def get_serial_ports(sid):
    sio.emit("get_serial_ports", list(map(lambda portInfo: portInfo[0], comports(False))))
    sio.emit('log', "Ports scanned. Ready to connect!")
    sio.emit('antLog', "Ports scanned. Ready to connect!")

# returns the list of possible destinations
@sio.on('get_destinations')
def get_destinations(sid):
    sio.emit('get_destinations', ['CentralStation 0x91', 'AstroAnt 0x92'])

# returns the list of possible command types
@sio.on('get_command_types')
def get_commands(sid, data):
    if data == 'CentralStation 0x91':
        sio.emit('get_command_types', list(command_dictionary['CentralStation 0x91'].keys()))
    elif data == 'AstroAnt 0x92':
        sio.emit('get_command_types', list(command_dictionary['AstroAnt 0x92'].keys()))

# opens the rss422 serial port
@sio.on('open_rss422_serial')
def open_rss422_serial(sid, data):
    global rss422_serial

    if rss422_serial != None:
        sio.emit('log', 'Serial port to Central Station (RSS422) already opened on \'' + rss422_serial.port + '\'. Restored.')
        return

    # open serial port
    try:
        rss422_serial = serial.Serial(data, BAUDRATE)
        rss422_serial_listen_thread = threading.Thread(target=listen_for_rss422_data)
        rss422_serial_listen_thread.start()
        sio.emit('open_rss422_serial', True)
        sio.emit('log', 'Opened serial port to Central Station (RSS422) on \'' + data + '\'.')
    except:
        sio.emit('open_rss422_serial', False)
        sio.emit('log', 'Failed to open serial port to Central Station (RSS422).')

@sio.on('open_astro_ant_serial')
def open_astro_ant_serial(sid, data):
    global astro_ant_serial

    if astro_ant_serial != None:
        sio.emit('antLog', 'Serial port to AstroAnt Emulator (USB) already opened on \'' + astro_ant_serial.port + '\'. Restored.')
        return

    # open serial port
    try:
        astro_ant_serial = serial.Serial(data, BAUDRATE)
        astro_ant_serial_listen_thread = threading.Thread(target=listen_for_astro_ant_data)
        astro_ant_serial_listen_thread.start()
        sio.emit('open_astro_ant_serial', True)
        sio.emit('antLog', 'Opened serial port to AstroAnt Emulator (USB) on \'' + data + '\'.')
    except:
        sio.emit('open_rss422_serial', False)
        sio.emit('antLog', 'Failed to open serial port to AstroAnt Emulator (USB).')

#  begins recording
@sio.on('start_recording')
def start_recording(sid):
    global is_recording
    global recording_file

    is_recording = True
    current_directory = os.getcwd()
    final_directory = os.path.join(current_directory, r'log')
    if not os.path.exists(final_directory):
        os.makedirs(final_directory)

    recording_file = open("./log/" + str(time.time()) + ".csv", "a")

#  stop recording
@sio.on('stop_recording')
def stop_recording(sid):
    global is_recording
    global recording_file
    sio.emit('file_path', recording_file.name)
    is_recording = False
    recording_file.close()

binFileFound = False
datFileFound = False
binFileLength = 0
datFileLength = 0
binFileBytesSent = 0
binFileBytes = bytes()
datFileBytes = bytes()

# write a command to the rss422 serial port
@sio.on('write_command')
def write_command(sid, data):
    
    global rss422_serial
    global sequence_number
    global is_recording
    global DFU_CENTRAL
    global binFileFound 
    global datFileFound 
    global binFileLength
    global datFileLength
    global binFileBytes 
    global datFileBytes 
    global binFileBytesSent
    

    if rss422_serial is None:
        sio.emit('log', 'Error: Please open the serial port first before performing this action.')
        return
    
    command_type = command_dictionary[data["destination"]][data["command_type"]]
    destination = destination_dictionary[data["destination"]]

    # build the command
    command = bytearray()
    command.append(0xEB) # set EB byte
    command.append(destination) # set destination
    command.extend(((int)(time.time())).to_bytes(4, 'little')) # set timestamp
    command.append(get_sequence_number()) # set sequence number
    command.append(command_type) # set command type
    command.extend([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

    if "firmware_packet" in data:
        print("Sending serial pack: " + str(binFileBytesSent) + " of " + str(binFileLength))
        for i in range(0, 20):
            if binFileBytesSent < binFileLength:
                command.append(binFileBytes[binFileBytesSent]) 
                binFileBytesSent += 1   
                sio.emit('log', str(binFileBytesSent) + " / " + str(binFileLength))
    elif "firmware_binary" in data and data["destination"] == "CentralStation 0x91" and data["command_type"] == "cs_update_ant_init_com 0x17": # must be ant fw
        binFileBytesSent = 0
        firmware_binary = data["firmware_binary"]
        with open("firmware.zip", "wb") as binary_file:
            binary_file.write(firmware_binary)
        
        with zipfile.ZipFile("firmware.zip", 'r') as zip_ref:
            if (os.path.exists('./firmware')):
                shutil.rmtree('./firmware')
            os.makedirs('./firmware')
            zip_ref.extractall("./firmware")

        files = [f for f in listdir('./firmware') if isfile(join('./firmware', f))]
        for file in files:
            if '.bin' in file:
                with open("./firmware/" + file, mode='rb') as file: # b is important -> binary
                    fileContent = file.read()
                    binFileBytes = fileContent
                    binFileLength = len(binFileBytes)
                    binFileFound = True
            elif '.dat' in file:
                with open("./firmware/" + file, mode='rb') as file: # b is important -> binary
                    fileContent = file.read()
                    datFileBytes = fileContent
                    datFileLength = len(datFileBytes)
                    datFileFound = True
        if not (binFileFound and datFileFound):
            sio.emit('log', "Failed to send update ant packet because zip file did not contain bin and dat file.")
            return
        print("Sending AstroAnt update file: " + str(datFileLength) + ", " + str(binFileLength))
        command.extend(datFileLength.to_bytes(4, 'little'))
        command.extend(binFileLength.to_bytes(4, 'little'))
        command.extend(datFileBytes)
        #command.extend(binFileBytes)


    command.append(crc(command)) # append checksum

    print(command)

    if 'send_corrupt' in data.keys():
        command[len(command) - 2] = 0xff # make data corrupt intentionally
    

    # encode command
    encoded = cobs.encode(command) 

    if not 'send_incomplete' in data.keys():
        encoded += bytes([0])

    # write command to serial
    try:
        rss422_serial.write(encoded)
    except serial.SerialException:
        rss422_serial = None
        sio.emit('log', "Serial was disconnected. Please reconnect.")
        return

    # emit the command and log it
    if not "firmware_packet" in data:
        sio.emit('write_command', {
            "command": list(map(lambda x: format(x, "02X"), command)),
            "corrupt": 'send_corrupt' in data.keys()
        })

        if is_recording:
            recording_file.write("SEND," + str(','.join(list(map(lambda x: format(x, "02X"), command)))) + "\n")

        sio.emit('log', "SEND - " + str(list(map(lambda x: format(x, "02X"), command))))

    if "firmware_binary" in data and data["destination"] == "CentralStation 0x91" and data["command_type"] == "cs_enter_dfu_serial_com 0x16": # append firmware
        firmware_binary = data["firmware_binary"]
        with open("firmware.zip", "wb") as binary_file:
            binary_file.write(firmware_binary)
            time.sleep(1) # sleep one sec to wait for DFU available (DFU times out after 3 seconds)
            DFU_CENTRAL = True
            sio.emit('log', 'Updating central via RSS422. This may take a while.')
            print("adafruit-nrfutil dfu serial -pkg ./firmware.zip -p " + rss422_serial.port + " -b 115200 --singlebank")
            os.system("adafruit-nrfutil dfu serial -pkg ./firmware.zip -p " + rss422_serial.port + " -b 115200 --singlebank")
            sio.emit('log', 'Finished updating central via RSS422.')
            DFU_CENTRAL = False
    

@app.route('/')
def index():
    return send_from_directory('frontend', 'index.html')

@app.route('/log/<path:path>')
def static_files(path):
    return send_from_directory('log', path)

app.run(host="localhost", port="8000")
