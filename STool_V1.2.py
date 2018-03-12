#!/usr/bin/env python
# -*-coding:utf-8-*-

"""
STool串口工具v1.2 （2018-03-12）

各线程机制：
    1、threadRefreshHis，threadRefreshArm线程
        *主UI窗口打开后启动，并进入阻塞状态
        *刷新弹出窗口打开后，解除阻塞
        *刷新弹出窗口关闭后，进入阻塞

待解决问题：
    1、实现各个框架通过鼠标改变大小，达到div拖动效果
    2、value = value + self.comDataOldList[index + 1][:(fetch_len * 2)]
        IndexError: list index out of range
修改记录：
1、将输出原数据窗口width减少33，兼容thinkpad小屏幕
"""

__author__ = 'wyl'

import serial
import serial.tools.list_ports
import threading
import time
import logging
import function_lib
from tkinter import *
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk
from tkinter import messagebox
from tkinter import filedialog


# 创建一个继承Frame的类
class ComUi(Frame):
    saveRawVar = None
    saveParseVar = None
    portVal = None
    baudRateVal = None
    enParseVar = None  # 使能是否解析
    enHexSendVar = None  # 使能是否16进制发送
    enHexRecvVar = None  # 使能是否16进制显示
    enTimingSend = None  # 使能定时发送

    scrollbar_y_raw = None
    scrollbar_y_parse = None

    def __init__(self, master=None):
        # 创建实例
        self.ser = serial.Serial()
        self.mcu = Mcu()

        self.comPort = 'COM3'
        self.comBaudrate = 9600
        self.serTimeOut = 1  # 设置超时1秒，解决接收不到换行符时，串口一直阻塞问题
        self.comAlive = False
        self.comData = None
        self.inputData = None
        self.inputDataHistory = ''

        # 日志保存路径变量
        self.path_save_raw = None
        self.path_save_parse = None

        self.boxOutRaw = None
        self.boxOutParse = None
        self.boxInput = None
        self.boxInputCmd = None
        self.boxPort = None
        self.boxBaud = None
        self.boxTiming = None
        self.boxInputSData = None  # 匹配解析后的数据
        self.boxInputRData = None  # 匹配原始数据
        self.boxInputCmdId = None  # 匹配解析后特定cmdId数据
        self.buttonComSw = None
        self.labelSaveRawStatus = None
        self.labelSaveParseStatus = None
        self.labelFilterItem = None
        self.labelCalcR = None
        self.labelCalcS = None
        self.labelMatchCmdNum = None
        self.packageNumR = 0
        self.packageNumS = 0
        self.matchCmdNum = 0

        self.boxOutRawBuff = 500000
        self.boxOutParseBuff = 500000
        self.boxOutRawDataSize = 0
        self.boxOutParseDataSize = 0

        self.threadReadData = threading.Thread(target=self.read_com_data)
        self.threadRefreshHis = threading.Thread(target=self.mcu.refresh_his)
        self.threadRefreshArm = threading.Thread(target=self.mcu.refresh_arm)
        self.threadTiming = threading.Thread(target=self.timing_send)
        self.threadReadData.setDaemon(True)  # 在主线程结束后回收threadReadData线程
        self.threadRefreshHis.setDaemon(True)
        self.threadRefreshArm.setDaemon(True)
        self.threadTiming.setDaemon(True)
        self.threadReadDataFlag = threading.Event()  # 用于阻塞threadReadData线程和恢复的标识
        self.threadReadDataFlag.set()  # 默认设置threadReadData为非阻塞
        self.threadTimingFlag = threading.Event()
        self.threadTimingFlag.clear()
        self.threadRefreshHisFlag = threading.Event()
        self.threadRefreshHisFlag.clear()
        self.threadRefreshArmFlag = threading.Event()
        self.threadRefreshArmFlag.clear()

        self.threadReadDataIsStop = True
        self.hisUiWindowIsOpen = False
        self.armUiWindowIsOpen = False

        print('串口初始状态：', self.ser)
        Frame.__init__(self, master)
        self.pack()
        self.create_comtool_ui()

    def create_comtool_ui(self):
        frm_left = Frame(self)
        frm_right = Frame(self)
        frm_left.pack(side=LEFT, fill='both', expand=True)
        frm_right.pack(side=LEFT, fill='both', expand=True)

        # --------------------------------------创建顶部菜单页-------------------------------------- #

        # 创建右键鼠标菜单项
        self.menu_output_raw = Menu(self.master, tearoff=0)
        self.menu_output_raw.add_command(label='清空', command=lambda: self.clear_box_txt(self.boxOutRaw))
        self.menu_output_parse = Menu(self.master, tearoff=0)
        self.menu_output_parse.add_command(label='清空', command=lambda: self.clear_box_txt(self.boxOutParse))

        # 创建顶部菜单页
        menu_bar = Menu(self.master)
        self.master.config(menu=menu_bar)

        # 增加文件类菜单项
        file_menu = Menu(menu_bar, tearoff=0)  # tearoff虚线分离菜单项
        menu_bar.add_cascade(label='文件', menu=file_menu)
        file_menu.add_command(label='保存日志')

        # 增加保存类菜单项
        save_menu = Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label='保存', menu=save_menu)
        self.saveRawVar = IntVar()
        self.saveParseVar = IntVar()
        save_menu.add_checkbutton(label='源数据', variable=self.saveRawVar, command=lambda: self.set_log_save(True))
        save_menu.add_separator()
        save_menu.add_checkbutton(label='解析数据', variable=self.saveParseVar, command=self.set_log_save)

        # --------------------------------------左框架-------------------------------------- #

        # 左框架（以下配置，可以保证缩小整体框架时，container2可以保持显示）
        container2 = ttk.LabelFrame(frm_left, text='参数配置')
        container2.pack(fill='both', expand=True, side='bottom')
        container1 = ttk.LabelFrame(frm_left, text='源数据')
        container1.pack(fill='both', expand=True, side='bottom')
        frm_left1 = Frame(container2)
        frm_left2 = Frame(container2)
        frm_left3 = Frame(container2)
        frm_left4 = Frame(container2)
        frm_left1.pack(fill='both', expand=True)
        frm_left2.pack(fill='both', expand=True)
        frm_left3.pack(fill='both', expand=True)
        frm_left4.pack(fill='both', expand=True)

        self.scrollbar_y_raw = Scrollbar(container1)
        self.boxOutRaw = Text(container1, width=100, borderwidth=3, height=60,
                            yscrollcommand=self.scrollbar_y_raw.set)  # 设置不换行wrap='none'
        self.scrollbar_y_raw.config(command=self.boxOutRaw.yview)
        self.scrollbar_y_raw.pack(fill='y', expand=True, side='right')
        self.boxOutRaw.pack(fill='both', expand=True, side='right')

        self.boxOutRaw.bind('<Button-3>', self.right_key_raw)

        # 左框架第一行
        Label(frm_left1, text='端口号：').grid(row=0, column=0)
        self.portVal = StringVar()
        self.boxPort = ttk.Combobox(frm_left1, width=7, textvariable=self.portVal, foreground='green')
        self.boxPort['values'] = ('COM1', 'COM2', 'COM3', 'COM4')
        self.boxPort.current(2)
        # boxPort.bind('<<ComboboxSelected>>', self.choicePort)
        self.boxPort.grid(row=0, column=1)
        Label(frm_left1, text='波特率：').grid(row=0, column=2)
        self.baudRateVal = StringVar()
        self.boxBaud = ttk.Combobox(frm_left1, width=6, textvariable=self.baudRateVal, foreground='green',
                                    state='readonly')
        self.boxBaud['values'] = ('9600', '19200', '38400', '115200')
        self.boxBaud.current(3)
        # boxBaud.bind('<<ComboboxSelected>>', self.choiceBaud)
        self.boxBaud.grid(row=0, column=3)
        self.buttonComSw = ttk.Button(frm_left1, text='打开串口', command=self.com_switch, width=8)
        self.buttonComSw.grid(row=0, column=4, padx=10)
        self.enHexRecvVar = IntVar()
        check_hexR = Checkbutton(frm_left1, text='HEX显示', variable=self.enHexRecvVar)
        check_hexR.deselect()
        check_hexR.grid(row=0, column=5, padx=3)
        self.enHexSendVar = IntVar()
        check_hexS = Checkbutton(frm_left1, text='HEX发送', variable=self.enHexSendVar)
        check_hexS.deselect()
        check_hexS.grid(row=0, column=6)
        self.enTimingSend = IntVar()
        check_timing = Checkbutton(frm_left1, text='定时发送：', variable=self.enTimingSend,
                                   command=self.timing_switch)
        check_timing.deselect()
        check_timing.grid(row=0, column=7)
        self.boxTiming = Text(frm_left1, width=5, height=1, borderwidth=1)
        self.boxTiming.grid(row=0, column=10)
        self.boxTiming.insert('0.0', '1000')
        Label(frm_left1, text='ms/次').grid(row=0, column=11)

        # 左框架第二行
        Button(frm_left2, text='发送', command=self.write_com_data, width=7, height=3).pack(fill='x', side='right')
        self.boxInput = ScrolledText(frm_left2, width=92, height=5, borderwidth=2)
        # self.boxInput.bind('<Key-Return>', self.write_com_data)
        self.boxInput.bind('<Key>', self.write_com_data)
        self.boxInput.pack(fill='x', side='right')
        self.boxInput.insert('0.0', 'AA 75 00 00 00 00 DF')

        # 左框架第三行
        Label(frm_left3, text='匹配到以下数据包数：').grid(row=0, column=0)
        self.labelCalcS = Label(frm_left3, text='0')
        self.labelCalcS.grid(row=0, column=1)
        ttk.Button(frm_left3, text='重新计数', command=lambda: self.clear_calc('calcS'), width=7) \
            .grid(row=0, column=2, padx=3)

        # 左框架第四行
        self.boxInputRData = Text(frm_left4, height=2, borderwidth=1)
        self.boxInputRData.pack(fill='x')
        self.boxInputRData.insert('0.0', 'aa55f000070190000100980a')

        self.labelSaveRawStatus = Label(frm_left4, text='底部状态栏', borderwidth=1, bg='Gainsboro')
        self.labelSaveRawStatus.pack(fill='x')

        # --------------------------------------右框架-------------------------------------- #

        # 右框架（以下配置，可以保证缩小整体框架时，container2可以保持显示）
        container4 = ttk.LabelFrame(frm_right, text='参数配置')
        container4.pack(fill='both', expand=True, side='bottom')
        container3 = ttk.LabelFrame(frm_right, text='解析数据')
        container3.pack(fill='both', expand=True, side='bottom')

        frm_right1 = Frame(container4)
        frm_right2 = Frame(container4)
        frm_right3 = Frame(container4)
        frm_right4 = Frame(container4)
        frm_right5 = Frame(container4)
        frm_right1.pack(fill='both', expand=True)
        frm_right2.pack(fill='both', expand=True)
        frm_right3.pack(fill='both', expand=True)
        frm_right4.pack(fill='both', expand=True)
        frm_right5.pack(fill='both', expand=True)

        self.scrollbar_y_parse = Scrollbar(container3)
        self.boxOutParse = Text(container3, width=133, borderwidth=3, height=60,
                            yscrollcommand=self.scrollbar_y_parse.set)
        self.scrollbar_y_parse.config(command=self.boxOutParse.yview)
        self.scrollbar_y_parse.pack(fill='y', expand=True, side='right')
        self.boxOutParse.pack(fill='both', expand=True, side='right')

        self.boxOutParse.bind('<Button-3>', self.right_key_parse)

        # 右框架第一行
        Label(frm_right1, text='数据处理开关：').grid(row=0, column=0)
        self.enParseVar = IntVar()
        check_All = Checkbutton(frm_right1, text='', variable=self.enParseVar)
        check_All.select()
        check_All.grid(row=0, column=1)
        ttk.Button(frm_right1, text='解析His心跳', width=10, command=self.mcu.create_his_ui) \
            .grid(row=0, column=2, sticky=E, padx=20)
        ttk.Button(frm_right1, text='解析Arm心跳', width=11, command=self.mcu.create_arm_ui) \
            .grid(row=0, column=3, sticky=E)

        # 右框架第二行
        Label(frm_right2, text='仅显示的项：').grid(row=0, column=0)
        self.labelFilterItem = Label(frm_right2, text='')
        self.labelFilterItem.grid(row=0, column=1)
 
        # 右框架第三行
        self.boxInputCmd = ScrolledText(frm_right3, height=1, borderwidth=3)
        self.boxInputCmd.pack(fill='x')

        # 右框架第四行
        Label(frm_right4, text='匹配到以下数据包数：').grid(row=0, column=0)
        self.labelCalcR = Label(frm_right4, text='0')
        self.labelCalcR.grid(row=0, column=1)
        ttk.Button(frm_right4, text='重新计数', command=lambda: self.clear_calc('calcR'), width=7) \
            .grid(row=0, column=2, padx=3)
        Label(frm_right4, text='  匹配到cmd：').grid(row=0, column=3)
        self.boxInputCmdId = Text(frm_right4, width=3, height=1, borderwidth=1)
        self.boxInputCmdId.grid(row=0, column=4)
        self.boxInputCmdId.insert('0.0', '81')
        Label(frm_right4, text='包数:').grid(row=0, column=5)
        self.labelMatchCmdNum = Label(frm_right4, text='0')
        self.labelMatchCmdNum.grid(row=0, column=6)

        # 右框架第五行
        self.boxInputSData = Text(frm_right5, height=2, borderwidth=1)
        self.boxInputSData.pack(fill='x')
        self.boxInputSData.insert('0.0', 'aa55f0006a00100064000000c8edbcfeb0e6b1be3a2042534a2d4746202020205'
                                         '8585858585858582e582028585858582d58582d585829205b636865636b73756d3'
                                         'a314133334231445d0d0a')

        self.labelSaveParseStatus = Label(frm_right5, text='底部状态栏', borderwidth=1, bg='Gainsboro')
        self.labelSaveParseStatus.pack(fill='x')

        self.threadTiming.start()  # 暂时由发送按钮触发启动定时发送线程

    def set_log_save(self, is_raw_data=False):
        def _set(checkButtonVar, label):
            if checkButtonVar.get():
                checkButtonVar.set(0)  # 在未成功获取到路径前，checkButtonVar.get()值为0
                savePath = filedialog.asksaveasfilename()
                print('savePath: ', savePath)

                if savePath == '':  # 用于检测用户点击取消保存按钮或文件名为空
                    # messagebox.showerror('文件名错误', '日志文件名不能为空！')
                    return

                label.config(text='日志保存中：' + savePath, fg='blue')
                checkButtonVar.set(1)
                return savePath
            else:
                label.config(text='')

        if is_raw_data:
            self.path_save_raw = _set(self.saveRawVar, self.labelSaveRawStatus)
        else:
            self.path_save_parse = _set(self.saveParseVar, self.labelSaveParseStatus)
            print('path_save_parse: ', self.path_save_parse)

    def save_log(self, is_raw_data=False, data=None):
        def _save(savePath, data):
            with open(savePath, 'a') as f:
                f.write(data)

        if is_raw_data:
            if self.saveRawVar.get():
                _save(self.path_save_raw, self.comData.strip('\n'))
        else:
            if self.saveParseVar.get():
                _save(self.path_save_parse, data)

    @staticmethod
    def clear_box_txt(box_name):
        box_name.delete('0.0', 'end')

    def right_key_raw(self, event):
        self.menu_output_raw.post(event.x_root, event.y_root)

    def right_key_parse(self, event):
        self.menu_output_parse.post(event.x_root, event.y_root)

    def com_switch(self):
        if not self.comAlive:
            # print('串口打开前状态：', self.ser)
            self.set_baudrate()
            try:
                self.ser.open()
            except Exception as e:
                function_lib.print_colorfont(e)
                messagebox.showerror('打开串口失败', e)
            if self.ser.is_open:
                print('打开串口成功！')
                self.comAlive = True
                self.buttonComSw.configure(text='关闭串口')
                self.boxPort['state'] = DISABLED
                self.boxBaud['state'] = DISABLED
                # print('串口打开后状态：', self.ser)

                if self.threadReadDataIsStop:
                    self.threadReadData.start()
                    print('线程threadReadData已启动')
                    self.threadReadDataIsStop = False
                else:
                    # print('线程threadReadData不能重复启动！')
                    pass
                self.threadReadDataFlag.set()
                if self.enTimingSend.get():
                    self.threadTimingFlag.set()
            else:
                print('打开串口失败！')
                self.comAlive = False

        else:
            self.ser.close()
            self.comAlive = False
            if not self.ser.is_open:
                print('关闭串口成功！')
            print('关闭串口后状态：', self.ser)
            self.buttonComSw.configure(text='打开串口')
            self.boxPort['state'] = ACTIVE
            self.boxBaud['state'] = ACTIVE
            self.threadReadDataFlag.clear()  # threadReadData线程设置为阻塞
            self.threadTimingFlag.clear()

    def set_baudrate(self):
        self.comPort = self.portVal.get()
        self.comBaudrate = self.baudRateVal.get()
        self.ser.setPort(self.comPort)
        self.ser.baudrate = self.comBaudrate
        self.ser.timeout = self.serTimeOut

    def read_com_data(self):
        while True:
            #print('读数据线程阻塞中...')
            self.threadReadDataFlag.wait()  # 阻塞线程，直到threadReadDataFlag为true
            # print('读数据线程解除阻塞！')
            while self.comAlive:
                '''
                try:
                    data_size = self.ser.in_waiting
                except OSError:  # 串口已经关闭，退出读数据操作！
                    continue
                if data_size <= 0:
                    continue
                self.comData = self.ser.read(data_size)
                '''
                try:
                    self.comData = self.ser.readline()
                except Exception as e:
                    # logging.exception(e)
                    continue

                if not self.comData:
                    continue  # 空数据直接返回

                # print('原始数据：', self.comData)
                if self.enHexRecvVar.get() == 1:  # 判断是否需要16进制显示
                    self.comData = self.comData.hex()
                    self.boxOutRaw.insert(END, self.comData + '\n')
                else:
                    try:
                        self.comData = self.comData.decode('gbk')
                    except Exception as e:  # 无法按gbk解码时，直接转为16进制输出
                        # logging.exception(e)
                        self.comData = self.comData.hex()
                    self.boxOutRaw.insert(END, self.comData)

                self.save_log(is_raw_data=True)

                # print('HEX数据：', hex_data)
                # self.boxOutRaw.insert(END, self.comData)
                # 设置Y轴滚动条位置
                comTool.scrollbar_auto()

                self.mcu.fetch_aa55()
                gb19056.fetch_19056(self.comData)

                # 屏幕可显示字符数
                self.auto_clear(self.comData)

    def write_com_data(self, event=None):
        if self.comAlive:
            if event is None or event.keycode == 13:  # 13:回车

                if self.enHexSendVar.get() == 1:  # 判断是否需要16进制发送
                    self.inputData = re.sub('\s', '', self.boxInput.get('0.0', 'end'))
                    self.inputDataHistory = self.inputData

                    # 19056协议发送数据自动添加效验码
                    if self.inputData[:4].lower() == 'aa75':
                        xor_value = function_lib.xor_calc(self.inputData)
                        self.inputData += xor_value

                    try:
                        self.inputData = bytes().fromhex(self.inputData)  # 将16进制字符串转字节型
                        # 统计下发数据的包数，上条语句出现异常则不执行统计
                        input_data_s = re.sub('\s', '', self.boxInputRData.get('0.0', 'end'))
                        self.packageNumS = self.packageNumS + self.inputDataHistory.count(input_data_s)
                        self.labelCalcS.config(text=self.packageNumS)
                    except Exception as e:
                        logging.exception(e)
                        function_lib.print_colorfont('出现非16进制数据，按照utf-8发送！')
                        self.inputData = self.inputData.encode('utf-8')  # 解决非16进制字符串转换问题
                else:
                    self.inputData = self.boxInput.get('0.0', 'end')
                    self.inputDataHistory = self.inputData
                    self.inputData= (self.inputData + '\n').encode('utf-8')

                input_data_length = len(self.inputData)
                split_line = '\n===>>{0}, 发送数据({1}B)：'.format(function_lib.get_time('ms'), input_data_length)
                self.boxOutRaw.insert(END, split_line + '\n【' + self.inputDataHistory + '】\n')

                self.ser.write(self.inputData)

                # 设置Y轴滚动条位置
                comTool.scrollbar_auto()

            elif event.keycode == 38:  # 38:上键
                print('self.inputDataHistory: ', self.inputDataHistory)
                self.boxInput.delete('0.0', END)
                self.boxInput.insert('0.0', self.inputDataHistory)
            else:
                pass
        else:
            print('串口未打开，无法写入数据')

    def timing_send(self):
        while True:
            print('定时发送线程阻塞中...')
            self.threadTimingFlag.wait()
            print('定时发送线程解除阻塞！')
            while self.enTimingSend.get() and self.comAlive:
                # print('sleep: ', self.boxTiming.get('0.0', 'end'))
                try:
                    time_ms = int(self.boxTiming.get('0.0', 'end')) / 1000  # 毫秒转化为秒单位
                except Exception as e:
                    logging.exception(e)
                    function_lib.print_colorfont('定时参数非法！强制为默认值：1 s')
                    self.boxTiming.delete('0.0', END)
                    self.boxTiming.insert('0.0', '1000')
                    continue
                # print('time_ms: ', time_ms)
                time.sleep(time_ms)
                self.write_com_data()

    def timing_switch(self):
        if self.enTimingSend.get():
            self.threadTimingFlag.set()
            print('设置threadTimingFlag设置为非阻塞')
        else:
            self.threadTimingFlag.clear()
            print('设置threadTimingFlag设置为阻塞')

    def clear_calc(self, type):
        if type == 'calcS':
            self.packageNumS = 0
            self.labelCalcS.config(text=0)
        else:
            self.packageNumR = 0
            self.labelCalcR.config(text=0)
            self.matchCmdNum = 0
            self.labelMatchCmdNum.config(text=0)

    def compare(self, recvSData):
        inputSData = re.sub('\s', '',self.boxInputSData.get('0.0', 'end'))
        if recvSData == inputSData:
            self.packageNumR = self.packageNumR + 1
            self.labelCalcR.config(text=self.packageNumR)
        else:
            pass

    def scrollbar_auto(self):
        if self.scrollbar_y_raw.get()[1] > 0.9:  # 当滚动条在底部附近则自动保持最底部
            self.boxOutRaw.see(END)
        if self.scrollbar_y_parse.get()[1] > 0.9:  # 当滚动条在底部附近则自动保持最底部
            self.boxOutParse.see(END)

    def auto_clear(self, data, target='raw'):
        if target == 'raw':
            # 屏幕可显示字符数
            if self.boxOutRawDataSize > self.boxOutRawBuff:
                self.boxOutRawDataSize = 0
                self.boxOutRaw.delete('0.0', END)
            else:
                self.boxOutRawDataSize += len(data)
        else:
            if self.boxOutParseDataSize > self.boxOutParseBuff:
                self.boxOutParseDataSize = 0
                self.boxOutParse.delete('0.0', END)
            else:
                self.boxOutParseDataSize += len(data)


class Gb19056(object):
    err_msg = ''
    parse_msg = ''
    hex_str = ''
    dict_19056 = {}
    dict_cmd_id = {'00': '采集记录仪执行标准版本', '01': '采集当前驾驶人信息', '02': '采集记录仪实时时间',
                   '03': '采集累计行驶里程', '04': '采集记录仪脉冲系数', '05': '采集车辆信息',
                   '06': '采集记录仪状态信号配置信息', '07': '采集记录仪唯一性编号',
                   '08': '采集指定行驶速度记录', '09': '采集指定位置信息记录', '10': '采集指定的事故疑点记录',}

    # 数据合法性检测
    def check_hex_str(self):
        if re.search('[^0-9a-f]', self.hex_str):
            self.err_msg = '检测到非16进制字符'
            comTool.boxOutParse.insert(END, self.hex_str + ' --> ' + self.err_msg + '\n')
            return 1
        if len(self.hex_str) % 2:
            self.err_msg = '字符数为奇数'
            comTool.boxOutParse.insert(END, self.hex_str + ' --> ' + self.err_msg + '\n')
            return 1

    def fetch_19056(self, hex_str):
        self.hex_str = re.sub('\s', '', hex_str).lower()
        if self.hex_str[:4] in ['aa75', '557a']:
            if self.check_hex_str():
                return
            self.judge_flag()
            if self.parse_msg != '':
                comTool.boxOutParse.insert(END, self.hex_str + ' --> ' + self.parse_msg + '\n\n')

    def data_struct(self):
        if self.hex_str[:6] in ['557afa', '557af0']:
            self.err_msg = '采集或设置出现错误！'
        else:
            self.dict_19056['flag'] = self.hex_str[:4]
            self.dict_19056['cmd_id'] = self.hex_str[4:6]
            self.dict_19056['length'] = self.hex_str[6:10]
            length = (int(self.dict_19056['length'], 16)) * 2
            self.dict_19056['keep'] = self.hex_str[10:12]
            self.dict_19056['data'] = self.hex_str[12:length + 12]
            self.dict_19056['checksum'] = self.hex_str[-2:]

    def judge_flag(self):
        self.data_struct()
        if self.dict_19056['flag'] == 'aa75':
            self.parse_aa75()
        else:
            self.parse_557a()

    def parse_aa75(self):
        cmd_id = self.dict_19056['cmd_id']
        self.parse_msg = '\n【send】' + self.dict_cmd_id[cmd_id] + '\n'
        if cmd_id in ['00', '01', '02', '03', '04', '05', '06', '07']:
            pass
        elif cmd_id in ['08', '09']:
            s_time = function_lib.change_time_format(self.dict_19056['data'][:12])
            e_time = function_lib.change_time_format(self.dict_19056['data'][12:24])
            block_num = self.dict_19056['data'][24:]
            self.parse_msg += '开始：{}，时间：{}，最大单位数据块个数：{}'.format(s_time, e_time, block_num)

    def parse_557a(self):
        cmd_id = self.dict_19056['cmd_id']
        if cmd_id == '00':
            self.parse_msg = '【recv】\n' + '版本年号：{}，修改单号：{}'\
                .format(self.dict_19056['data'][:2], self.dict_19056['data'][2:])
        elif cmd_id == '01':
            number = function_lib.hexstr_2_gbk_bytes(self.dict_19056['data'])
            self.parse_msg = '【recv】\n' + '驾驶证号码：{}'.format(number)
        elif cmd_id == '02':
            cur_time = function_lib.change_time_format(self.dict_19056['data'])
            self.parse_msg = '【recv】\n' + '记录仪实时时间：{}'.format(cur_time)
        elif cmd_id == '03':
            cur_time = function_lib.change_time_format(self.dict_19056['data'][:12])
            init_time = function_lib.change_time_format(self.dict_19056['data'][12:24])
            init_mile = self.dict_19056['data'][24:32]
            total_mile = self.dict_19056['data'][32:]
            self.parse_msg = '【recv】\n' + '记录仪实时时间：{} \n初次的安装时间：{}\n初始里程：{}\n累计里程：{}'\
                .format(cur_time, init_time, init_mile, total_mile)
        elif cmd_id == '04':
            cur_time = function_lib.change_time_format(self.dict_19056['data'][:12])
            pulse_factor = int(self.dict_19056['data'][12:], 16)
            self.parse_msg = '【recv】\n' + '记录仪实时时间：{}，脉冲系数：{}'.format(cur_time, pulse_factor)
        elif cmd_id == '05':
            identify_num = function_lib.hexstr_2_gbk_bytes(self.dict_19056['data'][:34])
            car_num = function_lib.hexstr_2_gbk_bytes(self.dict_19056['data'][34:56])
            car_num_type = function_lib.hexstr_2_gbk_bytes(self.dict_19056['data'][56:])
            pulse_factor = int(self.dict_19056['data'][12:], 16)
            self.parse_msg = '【recv】\n' + '车辆识别代号：{}，车牌号码：{}，车牌类别：{}'\
                .format(identify_num, car_num, car_num_type)
        elif cmd_id == '06':
            cur_time = function_lib.change_time_format(self.dict_19056['data'][:12])
            status_val = self.get_status_item(self.dict_19056['data'][12:14])
            status_name = self.dict_19056['data'][14:]
            self.parse_msg = '【recv】\n' + '记录仪实时时间：{}\n状态信号：{}\n信号名：{}'\
                .format(cur_time, status_val, status_name)
        elif cmd_id == '07':
            ccc_code = function_lib.hexstr_2_gbk_bytes(self.dict_19056['data'][:14])
            device_type = function_lib.hexstr_2_gbk_bytes(self.dict_19056['data'][14:46])
            date = self.dict_19056['data'][46:52]
            serial_num = int(self.dict_19056['data'][52:60], 16)
            keep = self.dict_19056['data'][60:]
            self.parse_msg = '【recv】\n' + 'ccc认证代码：{}\n认证产品型号：{}\n生产日期年月日：{}\n' \
                                          '生产流水号：{}\n备用：{}'\
                .format(ccc_code, device_type, date, serial_num, keep)
        elif cmd_id == '08':
            self.parse_msg = self.parse_speed(self.dict_19056['data'])
        elif cmd_id == '09':
            self.parse_msg = self.parse_speed(self.dict_19056['data'], (1332, 22))  # 22为位置+速度字节占用的字符位数
        elif cmd_id == '10':
            self.parse_msg = self.parse_speed(self.dict_19056['data'], (468, 4), True)

    def parse_speed(self, data, len_bit=(252, 4), isYdData=False):
        return_val = ''
        yd_time = 0.0
        list_speed_min = re.findall('\w{%d}' %len_bit[0], data)
        for speed_min in list_speed_min:
            if not isYdData:
                return_val += '\n\n开始时间：{}-->\n'.format(function_lib.change_time_format(speed_min[:12]))
                list_speed_sec = re.findall('\w{%d}' %len_bit[1], speed_min[12:])
            else:
                return_val += '\n\n结束时间：{}-->\n'.format(function_lib.change_time_format(speed_min[:12]))
                return_val += function_lib.hexstr_2_gbk_bytes(speed_min[12:48])
                list_speed_sec = re.findall('\w{%d}' % len_bit[1], speed_min[48:])
            for index, speed_sec in enumerate(list_speed_sec):
                if len_bit[1] == 4:
                    speed_val = int(speed_sec[:2], 16)
                    if speed_val == 255: continue
                    status = self.get_status_item(speed_sec[2:], type=1)
                    if not isYdData:
                        return_val += '-第{}秒：{}KM/H，{}'.format(index + 1, speed_val, status)
                    else:
                        yd_time = round(yd_time + 0.2, 1)  # 浮点数精度控制在小数点后一位
                        return_val += '-第{}秒：{}KM/H，{}'.format(yd_time, speed_val, status)
                else:
                    positional = speed_sec[:20]
                    speed_val = int(speed_sec[20:], 16)
                    if speed_val == 255: continue
                    return_val += '-第{}分钟：{}KM/H，{}'.format(index + 1, speed_val, positional)
            return return_val

    @staticmethod
    def get_status_item(data, byte_len=1, type=0):
        dict_status_item = {0: '自定义', 1: '自定义', 2: '自定义', 3: '近光灯', 4: '远光灯', 5: '右转向',
                            6: '左转向', 7: '制动（刹车）'}
        bin_data = function_lib.hex_2_bin(data, byte_len)
        # 使用列表生成器
        if type == 0:
            status = ['{}：{}'.format(dict_status_item[index], value) for index, value in enumerate(reversed(bin_data))]
        else:
            status = [dict_status_item[index] for index, value in enumerate(reversed(bin_data)) if value == '1']
        return '，'.join(status)


class Mcu(object):
    tree_his = None
    tree_arm = None
    comDataOld = ''
    comDataOldList = None
    value_his_old = ''
    value_arm_old = ''
    hisDataIsDiff = False
    armDataIsDiff = False
    re_aa55 = re.compile('(aa ?55.*?0a)', re.S)  # 支持aa 55之间存在0/1个空格
    dict_cmd = {'01': 'ARM心跳',
                     '02': 'ARM请求海思状态',
                     '03': 'ARM请求操作3G',
                     '04': 'ARM请求校时',
                     '05': 'ARM请求关闭海思',
                     '06': 'ARM请求设置海思参数',
                     '07': 'ARM请求音视频操作',
                     '08': 'ARM透传调试信息',
                     '0b': 'ARM请求操作海思USB',
                     '0c': '平台文本透传',
                     '0d': '国标视频协议透传',
                     '0e': '透传口透传',
                     '0f': '平台命令透传',
                     '10': 'ARM应答海思请求',
                     '12': '短信透传',
                     '20': '主IP数据上行透传',
                     '30': '副IP数据上行透传',
                     '32': '发送AGPS数据',
                     '33': '接收到AGPS数据',
                     '34': 'ARM应答运维宝请求',
                     '81': '海思心跳',
                     '82': '应答ARM请求海思状态',
                     '83': '应答ARM请求操作3G',
                     '84': '应答ARM请求校时',
                     '85': '应答ARM请求关闭海思',
                     '86': '应答ARM请求设置海思参数',
                     '87': '应答ARM请求音视频操作',
                     '8b': '应答ARM请求操作海思USB',
                     '8d': '应答国标视频协议透传',
                     '8f': '应答平台命令透传',
                     '90': '海思主动请求ARM信息',
                     '92': '应答短信透传',
                     'a0': '应答主IP数据透传',
                     'a1': '主IP数据下行透传',
                     'b0': '应答副IP数据透传',
                     'b1': '副IP数据下行透传',
                     'b2': '应答发送AGPS数据',
                     'b4': '博实结运维宝请求arm数据'}

    def create_his_ui(self):

        def win_close():
            print('海思数据解析窗口关闭！')
            hisHeart.destroy()
            comTool.hisUiWindowIsOpen = False
            comTool.threadRefreshHisFlag.clear()
            print('hisUiWindowIsOpen:{0}, threadRefreshHisFlag:{1}'
                  .format(comTool.hisUiWindowIsOpen, comTool.threadRefreshHisFlag.is_set()))

        hisHeart = Toplevel()

        hisHeart.title('海思心跳解析')
        hisHeart.geometry()
        hisHeart.resizable(width=False, height=True)

        self.tree_his = ttk.Treeview(hisHeart, show='headings', height=22, columns=('a', 'b', 'c'))

        # 表格标题
        self.tree_his.column('a', width=60, anchor='center')
        self.tree_his.column('b', width=80, anchor='center')
        self.tree_his.column('c', width=151, anchor='center')
        self.tree_his.heading('a', text='项')
        self.tree_his.heading('b', text='源数据')
        self.tree_his.heading('c', text='数据解析')
        vbar = ttk.Scrollbar(hisHeart, orient=VERTICAL, command=self.tree_his.yview)
        self.tree_his.configure(yscrollcommand=vbar.set)

        vbar.pack(fill='y', expand=True, side='right')
        self.tree_his.pack(fill='y', expand=True, side='right')


        self.value_his_old = ''  # 保证每次开启窗口后会刷新一次数据
        comTool.hisUiWindowIsOpen = True
        comTool.threadRefreshHisFlag.set()
        hisHeart.protocol('WM_DELETE_WINDOW', win_close)
        hisHeart.mainloop()

    def create_arm_ui(self):

        def win_close():
            print('ARM数据解析窗口关闭！')
            armHeart.destroy()
            comTool.armUiWindowIsOpen = False
            comTool.threadRefreshArmFlag.clear()
            print('armUiWindowIsOpen:{0}, threadRefreshArmFlag:{1}'
                  .format(comTool.armUiWindowIsOpen, comTool.threadRefreshArmFlag.is_set()))

        armHeart = Tk()

        armHeart.title('ARM心跳解析')
        armHeart.geometry()
        armHeart.resizable(width=False, height=True)

        self.tree_arm = ttk.Treeview(armHeart, show='headings', height=22, columns=('a', 'b', 'c'))

        # 表格标题
        self.tree_arm.column('a', width=60, anchor='center')
        self.tree_arm.column('b', width=120, anchor='center')
        self.tree_arm.column('c', width=200, anchor='center')
        self.tree_arm.heading('a', text='项')
        self.tree_arm.heading('b', text='解析')
        self.tree_arm.heading('c', text='源数据')
        vbar = ttk.Scrollbar(armHeart, orient=VERTICAL, command=self.tree_arm.yview)
        self.tree_arm.configure(yscrollcommand=vbar.set)

        vbar.pack(fill='y', expand=True, side='right')
        self.tree_arm.pack(fill='y', expand=True, side='right')

        comTool.armUiWindowIsOpen = True
        comTool.threadRefreshArmFlag.set()
        armHeart.protocol('WM_DELETE_WINDOW', win_close)
        armHeart.mainloop()

    def fetch_aa55(self):
        if comTool.enParseVar.get():
            comTool.comData = re.sub('\s', '', comTool.comData)  # 先去掉所有空格
            if re.search('[^0-9a-f]', comTool.comData):
                # print('当前行数据含有非16进制数据，return！【{0}】'.format(comTool.comData))
                return

            # 定义历史数据变量，解决aa55数据分布在多行问题
            self.comDataOld = self.comDataOld + comTool.comData

            # 单字节间增加空格，防止误匹配0a
            self.comDataOld = ' '.join(re.findall('\w{2}', self.comDataOld))

            # 使用正则表达式(aa ?55.*?0a)分割数据
            self.comDataOldList = self.re_aa55.split(self.comDataOld)

            # 去除所有空格
            for i, v in enumerate(self.comDataOldList):
                self.comDataOldList[i] = re.sub('\s', '', v)

            if len(self.comDataOldList) > 1:  # 判断是否匹配到aa55数据
                # print('列表中出现aa55数据：', self.comDataOldList)
                for index, value in enumerate(self.comDataOldList):
                    if self.re_aa55.findall(value):
                        self.dispose_aa55(index, value)
                    else:
                        pass  # 非AA55数据不处理

                # 保存删除aa55.*？0a后的数据
                self.comDataOld = ''.join(self.comDataOldList)

                # 避免列表无限扩张
                if 'aa55' not in self.comDataOld:
                    self.comDataOld = ''
                    # print('comDataOld中无aa55数据，清空！', self.comDataOldList)
        else:
            # print('无指定数据需要提取')
            pass

    def dispose_aa55(self, index, value):
        # 处理aa55-0a之间出现0a的情况
        length_aa55 = int(value[6:10], 16)

        if length_aa55 > 1200:  # 暂时定长度不能超过1200个字节
            print('数据{}长度({}B)大于1200字节，删除此条aa55数据！{}'.format(value[6:10], length_aa55, self.comDataOldList))
            self.comDataOldList[index] = ''
            return 'len_error'

        if length_aa55 != len(value[10:]) // 2:
            if length_aa55 > len(value[10:]) // 2:
                fetch_len = length_aa55 - len(value[10:]) // 2
                # print('提取列表下一个索引中数据长度:{}B '.format(fetch_len))
                # print('长度大于实际长度！{}B,{}B: {}'.format(length_aa55, len(value[10:]) // 2, value))
                # print('合并下个索引{}中数据:{}'.format(index + 1, self.comDataOldList))
                try:
                    value = value + self.comDataOldList[index + 1][:(fetch_len * 2)]
                except Exception as e:
                    logging.exception(e)
                    print('合并下个索引{}中数据:{}'.format(index + 1, self.comDataOldList))

                # 如果长度依然错误，则将处理后的数据存入comDataOld，进行下一轮处理
                # length_aa55 = int(value[6:10], 16)
                if length_aa55 > len(value[10:]) // 2:
                    '''print('长度依然大于实际长度！{}B,{}B，存入comDataOld，继续接收新的串口数据'
                          .format(length_aa55, len(value[10:]) // 2))'''
                    self.comDataOld = value
                    return 'len_error'
                else:  # 长度与实际长度匹配的情况，将当前value赋值到列表当前index下，下个索引数据去掉当前value部分
                    # print('长度OK！{}B,{}B'.format(length_aa55, len(value[10:]) // 2))
                    # print('comDataOldList处理前:{}'.format(self.comDataOldList))
                    self.comDataOldList[index] = value
                    self.comDataOldList[index + 1] = self.comDataOldList[index + 1][(fetch_len * 2):]
                    # print('comDataOldList处理后:{}\n{}'.format(self.comDataOldList, '-' * 70 + '处理完毕！' + '-' * 70))

            elif length_aa55 < len(value[10:]) // 2:
                # print('长度小于实际长度！{}B,{}B 删除: {}'.format(length_aa55, len(value[10:]) // 2, value))
                # print('comDataOldList删除前: ', self.comDataOldList)
                self.comDataOldList[index] = ''
                # print('comDataOldList删除后: ', self.comDataOldList)
                return 'len_error'

        # print('value: ', value)
        cmd_value = value[12:14]
        if cmd_value == comTool.boxInputSData.get('0.0', 'end').strip()[12:14]:
            comTool.compare(value)  # 比较输入的数据和接收到的数据是否一样，并打印包数

        if cmd_value == comTool.boxInputCmdId.get('0.0', 'end').strip():
            # print('检测到有需要匹配的CMD!', cmd_value)
            comTool.matchCmdNum = comTool.matchCmdNum + 1
            comTool.labelMatchCmdNum.config(text=comTool.matchCmdNum)

        self.output_filter(cmd_value, value)

        # 设置Y轴滚动条位置
        comTool.scrollbar_auto()

        # aa55数据处理完后，删除comDataOldList列表中对应数据
        self.comDataOldList[index] = ''

        if function_lib.xor_calc(value[:-4]) != value[-4:-2]:
            function_lib.print_colorfont('异或校验失败！{},【{}, {}】'.format(value, function_lib.xor_calc(value[:-4]), value[-4:-2]))

        if comTool.hisUiWindowIsOpen and cmd_value == '81':
            dataStruct.mcu_heart_his(value)
            if value != self.value_his_old:

                # 计算数据的异或值，如果异常则不进行
                if function_lib.xor_calc(value[:-4]) != value[-4:-2]:
                    print('cmd81异或校验失败！{},{}, {}'.format(value, function_lib.xor_calc(value[:-4]), value[-4:-2]))
                    self.hisDataIsDiff = False
                    return

                self.hisDataIsDiff = True
                self.value_his_old = value
            else:
                self.hisDataIsDiff = False
        if comTool.armUiWindowIsOpen and cmd_value == '01':
            dataStruct.mcu_heart_arm(value)
            if value != self.value_arm_old:

                # 计算数据的异或值
                if function_lib.xor_calc(value[:-4]) != value[-4:-2]:
                    print('cmd01异或校验失败！{},{}, {}'.format(value, function_lib.xor_calc(value[:-4]), value[-4:-2]))
                    self.armDataIsDiff = False
                    return

                self.armDataIsDiff = True
                self.value_arm_old = value
            else:
                self.armDataIsDiff = False

    def output_filter(self, cmd_value, value):
        def _output(data=value):
            split_line = '\n===>>{0}, cmd={1} [{2}]\n'.format(function_lib.get_time('ms'), cmd_value,
                                                              self.dict_cmd.get(cmd_value, '未知cmd类型'))
            comTool.boxOutParse.insert(END, split_line + value)
            comTool.save_log(data=split_line + value)

            # 清空屏幕
            comTool.auto_clear(split_line + value, 'parse')

        input_cmd = comTool.boxInputCmd.get('0.0', 'end').strip()
        input_cmd_list = input_cmd.split()
        if len(input_cmd_list):  # 判断是否有输入需要匹配的数据
            comTool.labelFilterItem.config(text='正在匹配-->' + ','.join(input_cmd_list), fg='green')
            if cmd_value in input_cmd_list:
                _output()
                if cmd_value == '10':
                    parse_result = function_lib.hexstr_2_gbk_bytes(value[24:-4], 'gbk_code')
                    _output(value=parse_result)
        else:  # 无限制情况下，AA55所有类型数据均输出
            comTool.labelFilterItem.config(text='')
            _output()

    def refresh_his(self):
        print('refresh_his线程启动成功！')
        while True:
            # print('His心跳刷新线程阻塞中...')
            comTool.threadRefreshHisFlag.wait()
            # print('His心跳刷新线程解除阻塞！')
            time.sleep(1)
            # print('海思数据刷新条件', comTool.hisUiWindowIsOpen, comTool.comAlive, self.hisDataIsDiff)
            while comTool.hisUiWindowIsOpen and comTool.comAlive and self.hisDataIsDiff:
                # print('海思数据刷新中...', comTool.hisUiWindowIsOpen, comTool.comAlive, self.hisDataIsDiff)
                tree_val = self.parse_mcu_his()
                try:
                    # print('删除children前: ', self.tree_his.get_children(''))
                    for _ in map(self.tree_his.delete, self.tree_his.get_children('')):
                        pass
                    # print('删除children后: ', self.tree_his.get_children(''))
                    for index, value in enumerate(tree_val):
                        self.tree_his.insert('', index, values=value)
                except TclError as e:  # 用来解决create_parse_his_ui窗口异常关闭问题
                    function_lib.print_colorfont(e)
                    comTool.hisUiWindowIsOpen = False
                    comTool.threadRefreshHisFlag.clear()
                    break
                time.sleep(3)

    def refresh_arm(self):
        print('refresh_arm线程启动成功！')
        while True:
            # print('ARM心跳刷新线程阻塞中...')
            comTool.threadRefreshArmFlag.wait()
            # print('ARM心跳刷新线程解除阻塞！')
            time.sleep(1)
            # print('armUiWindowIsOpen: ', comTool.armUiWindowIsOpen, comTool.comAlive, self.armDataIsDiff)
            while comTool.armUiWindowIsOpen and comTool.comAlive and self.armDataIsDiff:
                tree_val = self.parse_mcu_arm()
                try:
                    '''for index, value in enumerate(ParseMcuArmUi().get_label_list()):
                        value.config(text=tree_val[index], fg='green')'''
                    for _ in map(self.tree_arm.delete, self.tree_arm.get_children('')):
                        pass
                    # print('删除children后: ', comTool.parse_his_ui.self.tree_arm.get_children(''))
                    for index, value in enumerate(tree_val):
                        self.tree_arm.insert('', index, values=value)
                except TclError as e:  # 用来解决create_parse_his_ui窗口异常关闭问题
                    logging.exception(e)
                    comTool.armUiWindowIsOpen = False
                    comTool.threadRefreshArmFlag.clear()
                    break
                time.sleep(3)

    def parse_mcu_his(self):
        def get_parse_result(item, value):
            if item == 'modStat':
                return {'00': '不在线', '01': '拨号中', '80': '拨号成功', '90': '断开连接', 'ff': '未初始化'}\
                    .get(value, 'None')
            elif item == 'talkRequest':
                return {'00': '无', '01': '设备请求对讲'}.get(value, 'None')
            elif item in ['videoTStat', 'downloadStat', 'cameraStat', 'chCover', 'backupRec', 'urgentRec']:
                return function_lib.hex_2_bin(value, 1)
            elif item == 'talkStat':
                return {'00': '未发起', '01': '正在对讲'}.get(value, 'None')
            elif item in ['mainIp', 'subIp']:
                return {'00': '未连接', '01': '连接中', '02': '连接正常'}.get(value, 'None')
            elif item in ['sd1Stat', 'sd2Stat', 'hddStat', 'uDiskStat', 'eMMc']:
                return {'00': '不存在', '01': '存在', 'ff': '故障'}.get(value, 'None')
            elif item == 'workDisk':
                return {'00': 'SD1', '01': 'SD2', '02': '硬盘', 'ff': '无'}.get(value, 'None')
            elif item in ['ch1Rec', 'ch2Rec', 'ch3Rec', 'ch4Rec', 'ch5Rec', 'ch6Rec', 'ch7Rec', 'ch8Rec']:
                return {'00': '未录像', '01': '定时录像', '02': '手动录像', '03': '报警录像'}.get(value, 'None')
            elif item == 'initStat':
                return {'00': '未初始化', '01': '磁盘已初始化', '02': '通讯模块已初始化',
                        '03': '磁盘和通讯模块均已初始化'}.get(value, 'None')
            elif item in ['authStat']:
                return {'00': '正常', '01': '升级中', 'ff': '未授权'}.get(value, 'None')
            else:
                return value

        list_tree = []
        for key, value in dataStruct.his_item_py.items():
            list_tree.append((value, dataStruct.dict_heart_his[key],
                              get_parse_result(key, dataStruct.dict_heart_his[key])))
        return list_tree

    def parse_mcu_arm(self):
        def get_parse_result(name, item, value):
            # print('parse_mcu_arm value: ', value)
            if item == 'time':
                return '{0}-{1}-{2} {3}:{4}:{5}'\
                    .format(value[:2], value[2:4], value[4:6], value[6:8], value[8:10], value[10:12])
            elif item == 'speed':
                return str(int(value)) + 'KM/H'
            elif item in ['gps_power']:
                byte_gps_power = function_lib.hex_2_bin(value, 1)
                if name == '定位状态':
                    return {'0': '不定位', '1': '已定位'}.get(byte_gps_power[0], 'None')
                elif name == '定位天线':
                    return {'00': '故障', '01': '开路', '10': '短路', '11': '正常'}.get(byte_gps_power[1:3], 'None')
                elif name == '电源':
                    return {'00': '故障', '01': '开路', '10': '短路', '11': '正常'}.get(byte_gps_power[3:5], 'None')
            elif item in ['car_parts', 'car_status']:
                byte_car_parts = function_lib.hex_2_bin(value, 2)
                trigger_p = {'0': '触发', '1': '未触发'}
                oil_status = {'0': '油路断开', '1': '油路正常'}
                byte_car_status = function_lib.hex_2_bin(value, 1)
                trigger_s = {'0': '未触发', '1': '触发'}
                if name == '高一':
                    return trigger_p.get(byte_car_parts[1], 'None')
                elif name == '高二':
                    return trigger_p.get(byte_car_parts[2], 'None')
                elif name == '低一':
                    return trigger_p.get(byte_car_parts[3], 'None')
                elif name == '低二':
                    return trigger_p.get(byte_car_parts[4], 'None')
                elif name == '油路':
                    return oil_status.get(byte_car_parts[7], 'None')
                elif name == '劫警':
                    return trigger_p.get(byte_car_parts[8], 'None')

                elif name == '刹车':
                    return trigger_s.get(byte_car_status[3], 'None')
                elif name == '远光灯':
                    return trigger_s.get(byte_car_status[5], 'None')
                elif name == '近光灯':
                    return trigger_s.get(byte_car_status[2], 'None')
                elif name == '右转向':
                    return trigger_s.get(byte_car_status[6], 'None')
                elif name == '左转向':
                    return trigger_s.get(byte_car_status[7], 'None')
            elif item == 'accStat':
                return {'00': 'ACC关', '01': 'ACC开'}.get(value, 'None')
            elif item in ['simId', 'carNum']:
                return function_lib.hexstr_2_gbk_bytes(value, 'gbk_code')
            elif item in ['modControl']:
                return {'00': '单片机', '01': '海思', 'ff': 'ff'}.get(value, 'None')

        list_tree = []
        dict_arm = {'时间': 'time',
                    '速度': 'speed',
                    '定位状态': 'gps_power',
                    '定位天线': 'gps_power',
                    '电源': 'gps_power',
                    '高一': 'car_parts',
                    '高二': 'car_parts',
                    '低一': 'car_parts',
                    '低二': 'car_parts',
                    '油路': 'car_parts',
                    '劫警': 'car_parts',
                    '刹车': 'car_status',
                    '远光灯': 'car_status',
                    '近光灯': 'car_status',
                    '右转向': 'car_status',
                    '左转向': 'car_status',
                    'ACC': 'accStat',
                    '本机号': 'simId',
                    '车牌': 'carNum',
                    '模块控制': 'modControl'}
        for key, value in dict_arm.items():
            list_tree.append((key, get_parse_result(key, value, dataStruct.dict_heart_arm[value]),
                              dataStruct.dict_heart_arm[value]))
        return list_tree


class DataStruct(object):
    dict_heart_his = {}
    dict_heart_arm = {}
    his_item_py = {'modStat': '通讯模块', 'totalChNum': '总通道数', 'talkRequest': '对讲请求',
                   'videoTStat': '实时视频', 'talkStat': '对讲状态', 'downloadStat': '回放状态',
                   'mainIp': '主IP', 'subIp': '副IP', 'sd1Stat': 'SD1状态', 'sd2Stat': 'SD2状态',
                   'hddStat': '硬盘状态', 'uDiskStat': 'U盘状态', 'eMMc': 'eMMC状态', 'workDisk': '工作磁盘',
                   'cameraStat': '摄像头', 'chCover': '遮挡状态', 'ch1Rec': 'ch1录像', 'ch2Rec': 'ch2录像',
                   'ch3Rec': 'ch3录像', 'ch4Rec': 'ch4录像', 'ch5Rec': 'ch5录像', 'ch6Rec': 'ch6录像',
                   'ch7Rec': 'ch7录像', 'ch8Rec': 'ch8录像', 'backupRec': '备份录像', 'urgentRec': '紧急录像',
                   'voMode': '画面预览', 'none': '预留', 'none': '预留', 'none': '预留', 'initStat': '初始化',
                   'authStat': '授权状态'}

    def _import(self, dict_name, list_name, data, init_value, step_len):
        for item in list_name:
            dict_name[item] = data[init_value:(init_value + step_len)]
            init_value = init_value + step_len

    def mcu_heart_his(self, data):
        self.dict_heart_his['headFlag'] = data[:4]
        self.dict_heart_his['mainCmd'] = data[4:6]
        self.dict_heart_his['mainLength'] = data[6:10]
        self.dict_heart_his['answerType'] = data[10:12]
        self.dict_heart_his['cmdId'] = data[12:14]
        self.dict_heart_his['cmdLength'] = data[14:18]

        # 32字节状态
        self._import(self.dict_heart_his, self.his_item_py, data, 18, 2)

        self.dict_heart_his['checkSum'] = data[-4:-2]
        self.dict_heart_his['endFlag'] = data[-2:]

    def mcu_heart_arm(self, data):
        self.dict_heart_arm['headFlag'] = data[:4]
        self.dict_heart_arm['mainCmd'] = data[4:6]
        self.dict_heart_arm['mainLength'] = data[6:10]
        self.dict_heart_arm['answerType'] = data[10:12]
        self.dict_heart_arm['cmdId'] = data[12:14]
        self.dict_heart_arm['cmdLength'] = data[14:18]
        self.dict_heart_arm['time'] = data[18:30]
        self.dict_heart_arm['longitude'] = data[30:38]
        self.dict_heart_arm['latitude'] = data[38:46]
        self.dict_heart_arm['speed'] = data[46:50]
        self.dict_heart_arm['direction'] = data[50:54]

        # 状态信息16个字节
        self.dict_heart_arm['stat'] = data[54:86]
        self.dict_heart_arm['gps_power'] = data[54:56]
        self.dict_heart_arm['mileage'] = data[56:62]
        self.dict_heart_arm['car_parts'] = data[62:66]
        self.dict_heart_arm['car_status'] = data[78:80]

        self.dict_heart_arm['accStat'] = data[86:88]
        self.dict_heart_arm['simId'] = data[88:110]
        self.dict_heart_arm['carNum'] = data[120:144]
        self.dict_heart_arm['modControl'] = data[144:146]


if __name__ == '__main__':
    # 创建类实例
    comTool = ComUi()
    dataStruct = DataStruct()
    gb19056 = Gb19056()

    # 线程启动
    comTool.threadRefreshHis.start()
    comTool.threadRefreshArm.start()

    comTool.master.title('STool v1.1')
    comTool.master.geometry('1000x720')
    comTool.master.resizable(width=True, height=True)
    comTool.mainloop()
