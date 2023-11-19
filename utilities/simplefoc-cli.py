#
# SimpleFOC Command Line Inteface
#
# Interact with the SimpleFOC library using the command line.
# Supports all three protocol types: commander, binary, and ascii.
#
# Usage:
#   python simplefoc-cli.py --help
#


import argparse, time
import simplefoc.packets as packets
import simplefoc.commander as commander


parser = argparse.ArgumentParser(description='PySimpleFOC Command Line Interface')
parser.add_argument('-b','--baud', type=int, default=115200, help='Baud rate')
parser.add_argument('-m','--motorid', type=str, default='M', help='Motor ID (a number for binary or ascii protocol types, a letter for commander protocol type), default is M')
parser.add_argument('-v','--verbose', action='store_true', help='Verbose output')
parser.add_argument('-t','--type', choices=['commander', 'binary', 'ascii'], type=str, default='commander', help='Protocol type, default is commander')
parser.add_argument('port', type=str, help='Serial port to use')
parser.add_argument('commands', type=str, nargs='+', help='One or more commands or register=value pairs, separated by spaces')
# TODO add --silent option and implement response output
args = parser.parse_args()


motors = None
motor = None
match args.type:
    case 'commander':
        motors = commander.serial(args.port, args.baud)
        motor = motors.full_control(args.motorid)
    case 'binary':
        if args.motorid=='M': 
            args.motorid = 0
        motors = packets.serial(args.port, args.baud)
        motor = motors.motor(int(args.motorid))
    case 'ascii':
        if args.motorid=='M': 
            args.motorid = 0
        motors = packets.serial(args.port, args.baud, protocol=packets.ProtocolType.ascii)
        motor = motors.motor(int(args.motorid))

motors.console().subscribe(print)

motors.connect()
if args.verbose:
    print(f"Connected to {args.port} at {args.baud} baud.")

for command in args.commands:
    if (command.startswith('sleep=')):
        if args.verbose:
            print(f"Sleeping for {command[6:]} seconds...")
        time.sleep(float(command[6:]))
        continue
    if args.verbose:
        print(f"Sending command: {command}")
    match args.type:
        case 'commander':   # commander
            motors.send_command(command)
        case _:             # ascii or binary
            (reg, values) = packets.parse_register_and_values(command)
            motor.set_register(reg, values)

if args.verbose:
    print("Disconnecting...")

motors.disconnect()

if args.verbose:
    print("Done.")