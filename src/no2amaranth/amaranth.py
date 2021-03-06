#!/usr/bin/env python3

#
# Wrappers for various Nitro FPGA cores
#
# Copyright (C) 2021  Sylvain Munaut <tnt@246tNt.com>
# SPDX-License-Identifier: CERN-OHL-P-2.0
#

import importlib
import os
import pkg_resources
import tempfile

from amaranth import *
from amaranth.build import Platform
from amaranth.lib.cdc import FFSynchronizer, PulseSynchronizer
from amaranth.lib.fifo import SyncFIFOBuffered


__all__ = [ 'NitroMuAcmSync', 'NitroMuAcmAsync', 'NitroMuAcmBuffered' ]



class NitroMuAcmSync(Elaboratable):
	"""Wrapper for the Nitro FPGA μACM Core

	This core _needs_ to run at 48 MHz and all the interface signals are
	synchronous to this.

	Attributes
	----------

	in_data        : Signal(8), in
	in_last        : Signal(), in
	in_valid       : Signal(), in
	in_ready       : Signal(), out
	   AXI-Stream style data interface for chars going from FPGA to Host

	in_flush_now   : Signal(), in
	in_flush_time  : Signal(), in
	   Flush configuration signal. 'now' causes a flush ASAP. 'time'
	   enabled a timeout to make sure chars don't get stuck in the buffer
	   waiting to be packetized.

	out_data       : Signal(8), out
	out_last       : Signal(), out
	out_valid      : Signal(), out
	out_ready      : Signal(), in
	   AXI-Stream style data interface for chars going from Host to FPGA

	bootloader_req : Signal(), out
		Pulse signal when a DFU_DETACH request is received, requesting a reboot
		to bootloader mode
	"""

	def __init__(self, pads, **kwargs):
		# External signals
		self.in_data        = Signal(8)
		self.in_last        = Signal()
		self.in_valid       = Signal()
		self.in_ready       = Signal()
		self.in_flush_now   = Signal()
		self.in_flush_time  = Signal()

		self.out_data       = Signal(8)
		self.out_last       = Signal()
		self.out_valid      = Signal()
		self.out_ready      = Signal()

		self.bootloader_req = Signal()

		# Save pads
		self.pads = pads

		# Generate customized IP
		self.gen_customized_ip(**kwargs)

	def elaborate(self, platform: Platform) -> Module:
		m = Module()

		# Add source content from temp file directly
		platform.add_file('muacm.v', self.ip_file)

		# And instance
		m.submodules += Instance("muacm",
			io_usb_dp       = self.pads.d_p,
			io_usb_dn       = self.pads.d_n,
			o_usb_pu        = self.pads.pullup,
			i_in_data       = self.in_data,
			i_in_last       = self.in_last,
			i_in_valid      = self.in_valid,
			o_in_ready      = self.in_ready,
			i_in_flush_now  = self.in_flush_now,
			i_in_flush_time = self.in_flush_time,
			o_out_data      = self.out_data,
			o_out_last      = self.out_last,
			o_out_valid     = self.out_valid,
			i_out_ready     = self.out_ready,
			o_bootloader    = self.bootloader_req,
			i_clk           = ClockSignal(),
			i_rst           = ResetSignal()
		)

		return m

	def gen_customized_ip(self, **kwargs):
		# Load the customizer as module
		mod_spec = importlib.util.spec_from_file_location(
			'no2amaranth.no2muacm_customize',
			pkg_resources.resource_filename('no2amaranth', 'cores/no2muacm-bin/muacm_customize.py')
		)
		no2muacm_customize = importlib.util.module_from_spec(mod_spec)
		mod_spec.loader.exec_module(no2muacm_customize)

		# Load source
		sf = no2muacm_customize.MuAcmPatcher()
		sf.load(pkg_resources.resource_filename('no2amaranth', 'cores/no2muacm-bin/muacm.v'))

		# Apply requested customization
		if kwargs.get('vid') is not None:
			sf.set_vid(kwargs['vid'])

		if kwargs.get('pid') is not None:
			sf.set_pid(kwargs['pid'])

		if kwargs.get('vendor') is not None:
			sf.set_vendor(kwargs['vendor'])

		if kwargs.get('product') is not None:
			sf.set_product(kwargs['product'])

		if kwargs.get('serial') is not None:
			sf.set_serial(kwargs['serial'])

		if bool(kwargs.get('no_dfu_rt')) is True:
			sf.disable_dfu_rt()

		# Save to temporary file
		self.ip_file = tempfile.NamedTemporaryFile(suffix='.v')
		ip_file_name = os.path.abspath(self.ip_file.name)
		sf.save(ip_file_name)

		return ip_file_name


class NitroMuAcmXClk(Elaboratable):
	"""Lightweight clock crossing for the data interface of NitroMuAcmSync

	Use DomainRenamer to assign to the right domains.

	Attributes
	----------

	in_data   : Signal(8), in
	in_last   : Signal(), in
	in_valid  : Signal(), in
	in_ready  : Signal(), out
	   AXI-Stream style data interface (ingress, 'in_' clock domain)

	out_data  : Signal(8), out
	out_last  : Signal(), out
	out_valid : Signal(), out
	out_ready : Signal(), in
	   AXI-Stream style data interface (egress, 'out' clock domain)
	"""

	def __init__(self):
		# External signals
		self.in_data   = Signal(8)
		self.in_last   = Signal()
		self.in_valid  = Signal()
		self.in_ready  = Signal()

		self.out_data  = Signal(8)
		self.out_last  = Signal()
		self.out_valid = Signal()
		self.out_ready = Signal()

	def elaborate(self, platform: Platform) -> Module:
		m = Module()

		# Internal signals
		send_in        = Signal()
		send_sync_out  = Signal(2)

		ack_out        = Signal()
		ack_sync_in    = Signal(2)

		# Data is straight across
		m.d.comb += [
			self.out_data.eq  (self.in_data),
			self.out_last.eq  (self.in_last),
		]

		# Handshaking
		m.d.in_ += [
			send_in.eq( (send_in | (self.in_valid & ~self.in_ready) ) & ~ack_sync_in[0] ),
			ack_sync_in[1].eq( ack_sync_in[0] ),
			ack_sync_in[0].eq( ack_out ),
			self.in_ready.eq( ack_sync_in[0] & ~ack_sync_in[1] ),
		]

		m.d.out += [
			send_sync_out[1].eq( send_sync_out[0] ),
			send_sync_out[0].eq( send_in ),
			self.out_valid.eq( (self.out_valid & ~self.out_ready) | (send_sync_out[0] & ~send_sync_out[1]) ),
			ack_out.eq( (ack_out & send_sync_out[0]) | (self.out_valid & self.out_ready) ),
		]

		return m


class NitroMuAcmAsync(Elaboratable):
	"""Same interface as NitroMuAcmSync but the interface signal are not
	synchonous to the USB logic. The USB logic is clocked from a 'usb_48'
	domain and the external signals are in 'sync'.
	"""

	def __init__(self, pads, **kwargs):
		# External signals
		self.in_data        = Signal(8)
		self.in_last        = Signal()
		self.in_valid       = Signal()
		self.in_ready       = Signal()
		self.in_flush_now   = Signal()
		self.in_flush_time  = Signal()

		self.out_data       = Signal(8)
		self.out_last       = Signal()
		self.out_valid      = Signal()
		self.out_ready      = Signal()

		self.bootloader_req = Signal()

		# Create customized core
		self.core = NitroMuAcmSync(pads, **kwargs)

	def elaborate(self, platform: Platform) -> Module:
		m = Module()

		# Create cores
		m.submodules.core = core = DomainRenamer('usb_48')(self.core)
		m.submodules.xin  = xin  = DomainRenamer({"in_": "sync",   "out": "usb_48"})(NitroMuAcmXClk())
		m.submodules.xout = xout = DomainRenamer({"in_": "usb_48", "out": "sync"  })(NitroMuAcmXClk())

		# Wire stuff up
		m.d.comb += [
			xin.in_data.eq(self.in_data),
			xin.in_last.eq(self.in_last),
			xin.in_valid.eq(self.in_valid),
			self.in_ready.eq(xin.in_ready),

			core.in_data.eq(xin.out_data),
			core.in_last.eq(xin.out_last),
			core.in_valid.eq(xin.out_valid),
			xin.out_ready.eq(core.in_ready),

			xout.in_data.eq(core.out_data),
			xout.in_last.eq(core.out_last),
			xout.in_valid.eq(core.out_valid),
			core.out_ready.eq(xout.in_ready),

			self.out_data.eq(xout.out_data),
			self.out_last.eq(xout.out_last),
			self.out_valid.eq(xout.out_valid),
			xout.out_ready.eq(self.out_ready),
		]

		# X-clk for other signals
		m.submodules += [
			FFSynchronizer(self.in_flush_now,  core.in_flush_now),
			FFSynchronizer(self.in_flush_time, core.in_flush_time),
		]

		ps_boot = PulseSynchronizer("usb_48", "sync")
		m.submodules += ps_boot
		m.d.comb += [
			ps_boot.i.eq(core.bootloader_req),
			self.bootloader_req.eq(ps_boot.o),
		]

		return m


class NitroMuAcmBuffered(Elaboratable):
	"""Same interface as NitroMuAcmSync but with small FIFOs added to improve
	efficiency. Clocking scheme is either from NitroMuAcmSync (requiring 'sync'
	clock to be 48 MHz), or NitroMuAcmAsync (requiring a 'usb_48' domain but
	being flexibe on what the interface / 'sync' clock is)."""

	def __init__(self, pads, sync=False, fifo_depth=4, **kwargs):
		# External signals
		self.in_data        = Signal(8)
		self.in_last        = Signal()
		self.in_valid       = Signal()
		self.in_ready       = Signal()
		self.in_flush_now   = Signal()
		self.in_flush_time  = Signal()

		self.out_data       = Signal(8)
		self.out_last       = Signal()
		self.out_valid      = Signal()
		self.out_ready      = Signal()

		self.bootloader_req = Signal()

		# Config
		self.fifo_depth = fifo_depth

		# Create cores
		if sync:
			self.core = NitroMuAcmSync(pads, **kwargs)
		else:
			self.core = NitroMuAcmAsync(pads, **kwargs)

	def elaborate(self, platform: Platform) -> Module:
		m = Module()

		m.submodules.core     = core = self.core
		m.submodules.fifo_in  = fin  = SyncFIFOBuffered(width=9, depth=self.fifo_depth)
		m.submodules.fifo_out = fout = SyncFIFOBuffered(width=9, depth=self.fifo_depth)

		# Wire stuff up
		m.d.comb += [
			core.in_flush_now.eq(self.in_flush_now),
			core.in_flush_time.eq(self.in_flush_time),
			self.bootloader_req.eq(core.bootloader_req),

			fin.w_data[0:8].eq(self.in_data),
			fin.w_data[8].eq(self.in_last),
			fin.w_en.eq(self.in_valid),
			self.in_ready.eq(fin.w_rdy),

			core.in_data.eq(fin.r_data[0:8]),
			core.in_last.eq(fin.r_data[8]),
			core.in_valid.eq(fin.r_rdy),
			fin.r_en.eq(core.in_ready),

			fout.w_data[0:8].eq(core.out_data),
			fout.w_data[8].eq(core.out_last),
			fout.w_en.eq(core.out_valid),
			core.out_ready.eq(fout.w_rdy),

			self.out_data.eq(fout.r_data[0:8]),
			self.out_last.eq(fout.r_data[8]),
			self.out_valid.eq(fout.r_rdy),
			fout.r_en.eq(self.out_ready),
		]

		return m

