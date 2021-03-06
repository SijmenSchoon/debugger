#!/usr/bin/env python3

# demonstrate use of headless debugger to count opcode frequency for an md5 calculation

import os
import sys
import struct
from collections import defaultdict
from binaryninja.binaryview import BinaryViewType

# open for analysis
fpath = sys.argv[1]
bv = BinaryViewType.get_view_of_file(fpath)
bv.update_analysis_and_wait()

from debugger import DebugAdapter, lldb

# create debug adapter
adapt = lldb.DebugAdapterLLDB()
adapt.exec(fpath, ['-sabcdefghijklmnopqrstuvwxyz'])

# sense aslr situation, resolve symbols
base = adapt.target_base()
base_bv = bv.start
delta = base - base_bv
print('analysis rooted at 0x%X, target in memory at 0x%X, delta 0x%X' % (base_bv, base, delta))
for f in bv.functions:
	if f.symbol.full_name == '_MD5Init': _MD5Init = f.start + delta
	if f.symbol.full_name == '_MD5Update': _MD5Update = f.start + delta
	if f.symbol.full_name == '_MD5Final': _MD5Final = f.start + delta
print('  _MD5Init: 0x%X' % _MD5Init)
print('_MD5Update: 0x%X' % _MD5Update)
print(' _MD5Final: 0x%X' % _MD5Final)

# go until MD5 starts
adapt.breakpoint_set(_MD5Init)
(reason, data) = adapt.go()
assert reason == DebugAdapter.STOP_REASON.BREAKPOINT
assert adapt.reg_read('rip') == _MD5Init
adapt.breakpoint_clear(_MD5Init)

print('at MD5Init()')

# step until MD5Final
tally = defaultdict(int)
while 1:
	(reason, data) = adapt.step_into()
	assert reason in [DebugAdapter.STOP_REASON.BREAKPOINT, DebugAdapter.STOP_REASON.SINGLE_STEP]
	rip = adapt.reg_read('rip')
	opc = bv.get_disassembly(rip - delta).split()[0]
	tally[opc] += 1
	#print('0x%X %s' % (rip, opc))
	if adapt.reg_read('rip') == _MD5Final:
		break

n_instrs = sum(tally.values())
print('at MD5Final(), %d instructions so far' % n_instrs)

# step until return to caller
rsp = adapt.reg_read('rsp')
stack = adapt.mem_read(rsp, 8)
caller = struct.unpack('<Q', stack)[0]
while 1:
	(reason, data) = adapt.step_into()
	assert reason in [DebugAdapter.STOP_REASON.BREAKPOINT, DebugAdapter.STOP_REASON.SINGLE_STEP]
	rip = adapt.reg_read('rip')
	opc = bv.get_disassembly(rip - delta).split()[0]
	tally[opc] += 1
	if adapt.reg_read('rip') == caller:
		break

n_instrs = sum(tally.values())
print('returned from MD5Final(), %d instructions' % n_instrs)

for opc in sorted(tally, key=lambda x: tally[x], reverse=True):
	print('%s: %d (%.1f%%)' % (opc.ljust(8), tally[opc], 100*(tally[opc]/n_instrs)))

(reason, data) = adapt.go()
assert reason == DebugAdapter.STOP_REASON.PROCESS_EXITED

