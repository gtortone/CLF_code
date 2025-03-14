#!/usr/bin/env python3
# coding=utf-8

import argparse
import os
import time
import sys
import cmd2
import functools
import getpass
import numpy as np
from cmd2.table_creator import (
    Column,
    SimpleTable,
    HorizontalAlignment
)
from typing import (
    List,
)

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.RPC import RPCDevice
from lib.Centurion import Centurion
from lib.Configuration import Configuration
from lib.DeviceCollection import DeviceCollection
from lib.Radiometer import Radiometer3700, RadiometerOphir

cfg = Configuration()
cfg.read()

dc = DeviceCollection()

class CLF_app(cmd2.Cmd):

    def __init__(self, mode, param):
        super().__init__(allow_cli_args=False)
        del cmd2.Cmd.do_edit
        del cmd2.Cmd.do_macro
        del cmd2.Cmd.do_run_pyscript
        del cmd2.Cmd.do_shell
        del cmd2.Cmd.do_shortcuts

        self.param = param
        self.port = self.param.port
        self.prompt=  "clf> "
        #self.prompt = self.bright_black(f'CLF:{self.param.mode} > ')

            # Move text styles here
        # self.bright_black = functools.partial(cmd2.ansi.style, fg=cmd2.ansi.fg.bright_black)
        # self.bright_yellow = functools.partial(cmd2.ansi.style, fg=cmd2.ansi.fg.bright_yellow)
        # self.bright_green = functools.partial(cmd2.ansi.style, fg=cmd2.ansi.fg.bright_green)
        # self.bright_red = functools.partial(cmd2.ansi.style, fg=cmd2.ansi.fg.bright_red)
        # self.bright_cyan = functools.partial(cmd2.ansi.style, fg=cmd2.ansi.fg.bright_cyan)
        # self.bright_blue = functools.partial(cmd2.ansi.style, fg=cmd2.ansi.fg.bright_blue)
        # self.yellow = functools.partial(cmd2.ansi.style, fg=cmd2.ansi.fg.yellow)
        # self.blue = functools.partial(cmd2.ansi.style, fg=cmd2.ansi.fg.bright_blue)
        # self.alarm_red = functools.partial(cmd2.ansi.style, fg=cmd2.ansi.fg.bright_white, bg=cmd2.ansi.bg.bright_red)

        # self.allow_style = cmd2.ansi.allow_style
        # self.prompt = self.bright_black(f'CLF: > ')

        cmd2.categorize(
            (cmd2.Cmd.do_alias, cmd2.Cmd.do_help, cmd2.Cmd.do_history, cmd2.Cmd.do_quit, cmd2.Cmd.do_set, cmd2.Cmd.do_run_script),
            "General commands" 
        )

    
    ########add functions##############

    ##### RPC Functions ############
    plugs=[]
    @cmd2.with_category("Instruments command")
    def do_rpc_init(self, args: argparse.Namespace) -> None:
        for oname, oparams in cfg.outlets.items():
            port_params = cfg.get_port_params(oparams['port'])
            dc.add_outlet(oparams['id'], oname,
                port=port_params['port'],
                speed=port_params['speed'],
                bytesize=port_params['bytesize'],
                parity=port_params['parity'],
                stopbits=port_params['stopbits'],
                timeout=port_params['timeout']
            )
            self.plugs.append(oname)
        

    rpc_parser = argparse.ArgumentParser()
    rpc_parser.add_argument('value', type=str, help='name of plug', choices=plugs)
    rpc_parser.add_argument('status', type=str, help='status of the plug on off', choices=['on','off'])

    @cmd2.with_argparser(rpc_parser)
    @cmd2.with_category("Instruments command")
    def do_rpc(self, args: argparse.Namespace) -> None:
        
        if args.status == 'on':
            print('on to plug ' + args.value)
            ind=self.plugs.index(args.value)
            dc.get_outlet(str(self.plugs[ind])).on() 
            
        else:
            print('off to plug ' + args.value )
            ind=self.plugs.index(args.value)
            dc.get_outlet(str(self.plugs[ind])).off() 

    ######### LASER FUNCTIONS ##################
    @cmd2.with_category("laser command")
    def do_lsr_connect(self, args: argparse.Namespace) -> None:
        self.laser = Centurion("/dev/ttyr01")

    @cmd2.with_category("laser command")
    def do_lsr_close_conn(self, args: argparse.Namespace) -> None:
        del self.laser 

    @cmd2.with_category("laser command")
    def do_lsr_init(self, args: argparse.Namespace) -> None:
        self.laser.set_mode(100, 1, 1, 1, 1, 1, dpw = 140, qsdelay = 145)

    @cmd2.with_category("laser command")
    def do_lsr_fire(self, args: argparse.Namespace) -> None:
        self.laser.fire()

    lsr_energy_parser = argparse.ArgumentParser()
    lsr_energy_parser.add_argument('value', type=int, help='energy of the laser shot in us')
    @cmd2.with_argparser(lsr_energy_parser)
    @cmd2.with_category("laser command")
    def do_lsr_energy(self, args: argparse.Namespace) -> None:
        self.laser.set_pwdth(args.value)
    
    @cmd2.with_category("laser command")
    def do_lsr_checktemps(self, args: argparse.Namespace) -> None:
        self.laser.check_temps()
    
    @cmd2.with_category("laser command")
    def do_lsr_warmup(self, args: argparse.Namespace) -> None:
        self.laser.warmup()

    ######### RADIOMETER FUNCTIONS ##################
    @cmd2.with_category("radiometer command")
    def do_rad1_connect(self, args: argparse.Namespace) -> None:
        rad1= Radiometer3700("/dev/ttyr02")
        rad1.info()
        rad1.setup()
    
    @cmd2.with_category("radiometer command")
    def do_rad2_connect(self, args: argparse.Namespace) -> None:
        rad2= Radiometer3700("/dev/ttyr04")
        rad2.info()
        rad2.setup()

    @cmd2.with_category("radiometer command")
    def do_rad3_connect(self, args: argparse.Namespace) -> None:
        rad3= RadiometerOphir("/dev/ttyr05")
        rad3.info()
        rad3.set("$DU", 1)


    ######### MOTOR FUNCTIONS ##################
    motors=[]
    @cmd2.with_category("VXM commands")
    def do_VXM_init(self, args: argparse.Namespace) -> None:
        for mname, mparams in cfg.motors.items():
            port_params = cfg.get_port_params(mparams['port'])
            dc.add_motor(mparams['id'], mname,
                port=port_params['port'],
                speed=port_params['speed'],
                bytesize=port_params['bytesize'],
                parity=port_params['parity'],
                stopbits=port_params['stopbits'],
                timeout=port_params['timeout']
            )
            self.motors.append(mname)
        print(self.motors)

    @cmd2.with_category("VXM commands")
    def do_VXM_config(self, args: argparse.Namespace) -> None:
        dc.get_motor("UpNorthSouth").set_model(1)
        dc.get_motor("UpNorthSouth").set_acc(2000)
        dc.get_motor("UpEastWest").set_model(1)
        dc.get_motor("UpEastWest").set_acc(2000)
        dc.get_motor("LwNorthSouth").set_model(1)
        dc.get_motor("LwNorthSouth").set_acc(2000)
        dc.get_motor("LwPolarizer").set_model(1)
        dc.get_motor("LwPolarizer").set_acc(2000)

    @cmd2.with_category("VXM commands")
    def do_VXM_ECAL_RAD3(self, args: argparse.Namespace) -> None:
        dc.get_motor("UpNorthSouth").move_ABS(33250)
        dc.get_motor("UpEastWest").move_ABS(4470)
    
    @cmd2.with_category("VXM commands")
    def do_VXM_home_UP(self, args: argparse.Namespace) -> None:
        dc.get_motor("UpNorthSouth").move_ABS0()
        dc.get_motor("UpEastWest").move_ABS0()

if __name__ == '__main__':
   parser = argparse.ArgumentParser()
   parser.add_argument('--mode', default='rtu', const='rtu', nargs='?', choices=['rtu', 'tcp'], help='set modbus interface (default: %(default)s)')
   parser.add_argument('--port', action='store', type=str, help='serial port device (default: /dev/ttyPS2)', default='/dev/ttyPS2')
   parser.add_argument('--host', action='store', type=str, help='mbusd hostname (default: localhost)', default='localhost')
   args = parser.parse_args()

   app = CLF_app(args.mode,args)
   app.cmdloop()

