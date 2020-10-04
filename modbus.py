import socket, time, threading, serial, requests, json

class myTimerObject(object):
    def __init__(self, interval, function, *args, **kwargs):
        self._timer = None
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.next_call = time.time()
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        if not self.is_running:
            self.next_call += self.interval
            self._timer = threading.Timer(self.next_call - time.time(), self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False

RS485 = serial.Serial(port = 'COM4', baudrate=9600, timeout=0.5)


def readModbus16(unitID, registr):

    command = bytearray([0, 1, 0, 0, 0, 6, 245, 3, 3, 21, 0, 1])
    validflag = True

    global tctr
    
    tctr = tctr + 1
    if tctr > 255: tctr = 0

    command[1] = tctr
    command[6] = unitID;
    command[8] = registr // 256
    command[9] = registr % 256

    ESSClient = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ESSClient.settimeout(0.5)
    ESSClient.connect(('10.0.0.55', 502))
    ESSClient.sendall(command)
      
    inbyte = ESSClient.recv(16)
    
    ESSClient.close()
    
    for i in range(0,8):
        if ((i != 5) and (command[i] != inbyte[i])): validflag = False

    if validflag:
        return inbyte[9] * 256 + inbyte[10]
    else:
        return -1

def readModbus1():
    global RS485, TY, acpv
    command = bytearray([1, 3, 0, 8, 0, 10, 68, 15])
    if not RS485.is_open:
        RS485.open()
    RS485.reset_input_buffer()
    RS485.write(command)

    try:
        inbuf = RS485.read(26)
        if inbuf[2] == 20:
            TY = inbuf[3] * 16777216 + inbuf[4] * 65336 + inbuf[5] * 256 + inbuf[6]
            acpv = -1 * (inbuf[15] * 256 + inbuf[16])
            return 0
    except:
        return -1

    return -1

def readModbus2():
    global RS485, ac, hz, nonessential
    command = bytearray([2, 3, 0, 12, 0, 6, 5, 248])
    if not RS485.is_open:
        RS485.open()
    RS485.reset_input_buffer()
    RS485.write(command)

    try:
        inbuf = RS485.read(26)
        if inbuf[2] == 12:
            ac = inbuf[3] * 256 + inbuf[4]
            hz = inbuf[13] * 256 + inbuf[14]
            nonessential = inbuf[7] * 256 + inbuf[8]
            return 0
    except:
        return -1

    return -1
    

def modbusLoop():

    global ac, hz, nonessential, alarm, crload, dcpv, grid, mpload, battV, SOC, battA, lastRead, house, solar
    global dcpvt, houset, offpeak, peak, shoulder, TY, acpv, acpvt, acpvy, midnightReset

    inPut = readModbus2()    
    if inPut == -1:
        ac = readModbus16(242, 15) / 10
        hz = readModbus16(242, 21) / 100
        nonessential = 0

    inPut = readModbus16(100, 830)
    if inPut <= 0: alarm = 0
    else: alarm = 2

    inPut = readModbus16(242, 23)
    if inPut > 32767: crload = (inPut - 65535) * 10
    elif inPut != -1: crload = inPut * 10
    
    inPut = readModbus16(100,850)
    if inPut != -1: dcpv = round(inPut * 0.9)

    inPut = readModbus16(30, 2600)
    if inPut > 32767: grid = inPut - 65535
    else: grid = inPut

    inPut = readModbus16(100, 866)
    if inPut > 32767: mpload = inPut - 65535
    else: mpload = inPut

    inPut = readModbus16(100, 840);
    if inPut != -1: battV = inPut / 10

    inPut = readModbus16(100, 843);
    if inPut != -1: SOC = inPut

    inPut = readModbus16(100, 841);
    if inPut > 32767: battA = (inPut - 65535) / 10
    elif inPut != -1: battA = inPut / 10

    if (dcpv != -1 and crload != -1 and grid != -1 and mpload != -1):
        gap = time.perf_counter_ns() / 1000000 - lastRead
        lastRead = time.perf_counter_ns() / 1000000
        print ("......................Gap: %d"% gap)
        
        inPut = readModbus1()
        
        if inPut != -1:
            ## meter has been reset    
            if TY * 10 < acpvy: acpvy = 0

            acpvt = TY * 10.0 - acpvy;
        elif alarm == 2:
            acpv = 0
        else:
            parload = - (grid - mpload - crload)
            if parload > 0:
                acpv = parload;
                acpvt = acpvt + acpv * (gap / 3600000000);
            else:
                acpv = 0
            
        house = crload + nonessential
        solar = dcpv + acpv
        dcpvt = dcpvt + dcpv * (gap / 3600000000);
        houset = houset + house * (gap / 3600000000);
        
        result = time.localtime()
        wkn = result.tm_wday
        hour = result.tm_hour
        minute = result.tm_min      
        if ((hour >= 0 and hour <= 6) or (hour >= 22 and hour <= 23)):
            offpeak = offpeak + house * (gap / 3600000000);
        if ((hour >= 7 and hour <= 13) or (hour >= 20 and hour <= 21)):
            shoulder = shoulder + house * (gap / 3600000000);
        if (hour >= 14 and hour <= 19 and wkn >= 5):
            shoulder = shoulder + house * (gap / 3600000000);
        if (hour >= 14 and hour <= 19 and wkn < 5):
            peak = peak + house * (gap / 3600000000);

        if (hour == 0 and minute == 0 and not midnightReset):
            ## write data to daily database
            result2 = time.localtime(time.time()-3600)
            yesterday = time.strftime("%d/%m/%Y", result2)

            args = "http://10.0.0.4/php/savedaily2.php?"
            args = args + "DATE=" + yesterday
            args = args + "&ACPV={:.2f}".format(acpvt)
            args = args + "&DCPV={:.2f}".format(dcpvt)
            args = args + "&HOUSE={:.2f}".format(houset)
            args = args + "&OFFPEAK={:.2f}".format(offpeak)
            args = args + "&PEAK={:.2f}".format(peak)
            args = args + "&SHOULDER={:.2f}".format(shoulder) + "\r\n"

            requests.get(args.encode())

            inPut = readModbus1()
            
            if inPut != -1:
                acpvy = TY * 10
            else:
                acpvy = acpvy + acpvt
                
            midnightReset = True
            acpvt = dcpvt = houset = offpeak = peak = shoulder = 0
            print("i am resetting")

        return True
    else: return False


def main():
    goodData = modbusLoop()
    if goodData:
        
        args = "http://10.0.0.4/php/saveess2.php?"
        args = args + "AC_PV=" + str(acpv)
        args = args + "&DC_PV=" + str(dcpv)
        args = args + "&SOLAR=" + str(solar)
        args = args + "&GRID=" + str(grid)
        args = args + "&HOUSE=" + str(house)
        args = args + "&NON_E=" + str(nonessential)
        args = args + "&SOC=" + str(SOC)
        args = args + "&DC_V={:.1f}".format(battV)
        args = args + "&DC_A={:.1f}".format(battA)
        args = args + "&AC_V={:.1f}".format(ac)
        args = args + "&AC_HZ={:.2f}".format(hz)
        args = args + "&AC_PV_T={:.2f}".format(acpvt)
        args = args + "&DC_PV_T={:.2f}".format(dcpvt)
        args = args + "&HOUSE_T={:.2f}".format(houset)
        args = args + "&OFFPEAK={:.2f}".format(offpeak)
        args = args + "&PEAK={:.2f}".format(peak)
        args = args + "&SHOULDER={:.2f}".format(shoulder)
        args = args + "&ALARM=" + str(alarm) + "\r\n"

        requests.get(args)
        
#        print(x.status_code)
#         print ("AC V:", ac)
#         print ("AC Hz:", hz)
#         print ("Alarm:", alarm)
#         print ("Critical Houseload:", crload)
#         print ("DC Solar:", dcpv)
#         print ("AC Solar:", acpv)
#         print ("Grid:", grid)
#         print ("mpload:", mpload)
#         print ("Battery V:", battV)
#         print ("Battery A:", battA)
#         print ("SOC:", SOC)
#         print ("House:", house)
#         print ("Solar:", solar)
#         print ("Non-Essential:", nonessential)
#         print ("DC Solar Today: %6.3f"% dcpvt )
#         print ("House kWH Today: %6.3f"% houset)
#         print ("Offpeak kWH Today: %6.3f"% offpeak)
#         print ("Shoulder kWH Today: %6.3f"% shoulder)
#         print ("Peak kWH Today: %6.3f"% peak)
#         print ("Total Yield: %7.2f"% (TY/100))
    else: print ("...............bad data")

if __name__ == '__main__':
    tctr = 0
    acpvt = acpvy = dcpvt = houset = offpeak = peak = shoulder = TY = 0
    alarm = ac = hz = nonessential = crload = dcpv = grid = mpload = battV = SOC = battA = house = solar = acpv = 0
    midnightReset = False;
    
    response = requests.get("http://10.0.0.4/php/retrievesums2.php")
    sv = json.loads(response.text)
    acpvt = float(sv["AC_PV_T"])
    dcpvt = float(sv["DC_PV_T"])
    houset = float(sv["HOUSE_T"])
    offpeak = float(sv["OFFPEAK"])
    peak = float(sv["PEAK"])
    shoulder = float(sv["SHOULDER"])
    
    lastRead = time.perf_counter_ns() / 1000000

    mTO1 = myTimerObject(2, main) 


