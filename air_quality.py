#!/usr/bin/env python3

import requests
import ST7735
import time
from bme280 import BME280
from pms5003 import PMS5003, ReadTimeoutError
from subprocess import PIPE, Popen, check_output
from PIL import Image, ImageDraw, ImageFont
from fonts.ttf import RobotoMedium as UserFont
from enviroplus import gas
from splunk_http_event_collector import http_event_collector
import socket
import os

try:
    from smbus2 import SMBus
except ImportError:
    from smbus import SMBus

# setup send to splunk
try:
    events = http_event_collector(os.getenv("HEC_TOKEN"), "192.168.99.60")
except Exception as e:
    print(f"missing env key e={e}")
    sys.exit(-1)
hec_payload = {}

bus = SMBus(1)

# Create BME280 instance
bme280 = BME280(i2c_dev=bus)

# Create LCD instance
disp = ST7735.ST7735(
    port=0,
    cs=1,
    dc=9,
    backlight=12,
    rotation=270,
    spi_speed_hz=10000000
)

# Initialize display
disp.begin()

# Create PMS5003 instance
pms5003 = PMS5003()


# Read values from BME280 and PMS5003 and return as dict
"""variables = ["temperature",
             "pressure",
             "humidity",
             "light",
             "oxidised",
             "reduced",
             "nh3",
             "pm1",
             "pm25",
             "pm10"]
"""
def read_values():
    values = {}
    # Weather
    try:
        cpu_temp = get_cpu_temperature()
        values["cpu_temp"] = "{:.2f}".format(cpu_temp)
        raw_temp = bme280.get_temperature()
        values["raw_temp"] = "{:.2f}".format(raw_temp)
        comp_temp = raw_temp - ((cpu_temp - raw_temp) / comp_factor)
        values["comp_temp"] = "{:.2f}".format(comp_temp)
        values["pressure"] = "{:.2f}".format(bme280.get_pressure() * 100)
        values["humidity"] = "{:.2f}".format(bme280.get_humidity())
    except:
        pass
    # Light
    try:
        values["light"] = "{:.2f}".format(bme280.get_lux())
    except:
        pass
    # Gas
    try:
        gas_data = gas.read_all()
        values["gas.oxidised"] = "{:.2f}".format(gas_data.oxidising / 1000)
        values["gas.reducing"] = "{:.2f}".format(gas_data.reducing / 1000)
        values["gas.nh3"] = "{:.2f}".format(gas_data.nh3 / 1000)
    except:
        pass

    # Particles
    try:
        pm_values = pms5003.read()
        values["pm.P1"] = str(pm_values.pm_ug_per_m3(1))
        values["pm.P25"] = str(pm_values.pm_ug_per_m3(2.5))
        values["pm.P10"] = str(pm_values.pm_ug_per_m3(10))

        values["pm.per_1l_air_.3"] = str(pm_values.pm_per_1l_air(.3))
        values["pm.per_1l_air_.5"] = str(pm_values.pm_per_1l_air(.5))
        values["pm.per_1l_air_1"] = str(pm_values.pm_per_1l_air(1))
        values["pm.per_1l_air_2.5"] = str(pm_values.pm_per_1l_air(2.5))
        values["pm.per_1l_air_5"] = str(pm_values.pm_per_1l_air(5))
        values["pm.per_1l_air_10"] = str(pm_values.pm_per_1l_air(10))
    except ReadTimeoutError:
        pms5003.reset()
        pm_values = pms5003.read()
        values["pm.P1"] = str(pm_values.pm_ug_per_m3(1))
        values["pm.P25"] = str(pm_values.pm_ug_per_m3(2.5))
        values["pm.P10"] = str(pm_values.pm_ug_per_m3(10))
    return values


# Get CPU temperature to use for compensation
def get_cpu_temperature():
    process = Popen(['vcgencmd', 'measure_temp'], stdout=PIPE, universal_newlines=True)
    output, _error = process.communicate()
    return float(output[output.index('=') + 1:output.rindex("'")])

# Display Raspberry Pi serial and Wi-Fi status on LCD
def display_status(values):
    text_colour = (255, 255, 255)
    back_colour = (0, 170, 170)
    try:
        message = "\nTemp: {}\nPM25: {}".format(values["comp_temp"], values["pm.P25"])
    except:
        message = "PM25: {}".format(values["pm.P25"])
    img = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)
    size_x, size_y = draw.textsize(message, font)
    x = (WIDTH - size_x) / 2
    y = (HEIGHT / 2) - (size_y / 2)
    draw.rectangle((0, 0, 160, 80), back_colour)
    draw.text((x, y), message, font=font, fill=text_colour)
    disp.display(img)


def send_to_splunk(values):
    hec_payload.update({"event":values})
    hec_payload.update({"time":str(round(time.time(),3))})
    events.sendEvent(hec_payload)


# Compensation factor for temperature
comp_factor = 2.25

# Raspberry Pi ID to send to Luftdaten

# Width and height to calculate text position
WIDTH = disp.width
HEIGHT = disp.height

# Text settings
font_size = 16
font = ImageFont.truetype(UserFont, font_size)

time_since_update = 0
update_time = time.time()


# Main loop to read data, display, and send to Luftdaten
while True:

    hec_payload.update({"index":"air"})
    hec_payload.update({"sourcetype":"pyair"})
    hec_payload.update({"source":"pi"})
    try:
        time_since_update = time.time() - update_time
        values = read_values()
        if time_since_update > 1:
            #print(values)
            send_to_splunk(values)
            update_time = time.time()
        display_status(values)
    except Exception as e:
        print(e)

