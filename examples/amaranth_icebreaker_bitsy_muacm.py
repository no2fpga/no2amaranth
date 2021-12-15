#!/usr/bin/env python3

from amaranth import *
from amaranth.build import *
from amaranth_boards.icebreaker_bitsy import *

from amaranth.lib.cdc import ResetSynchronizer


import no2amaranth


class LoopbackTest(Elaboratable):

	def __init__(self):
		pass

	def elaborate(self, platform: Platform) -> Module:
		m = Module()

		m.domains.sync   = ClockDomain()
		m.domains.por    = ClockDomain(async_reset=True)
		m.domains.usb_48 = ClockDomain()

		clk12   = platform.request("clk12", dir='-')
		rst_btn = platform.request("button")

		clk24 = Signal()
		clk48 = Signal()
		pll_locked = Signal()

		m.submodules.pll = Instance("SB_PLL40_2F_PAD",
			p_DIVR                  = 0,
			p_DIVF                  = 63,
			p_DIVQ                  = 4,
			p_FILTER_RANGE          = 1,
			p_FEEDBACK_PATH         = "SIMPLE",
			p_PLLOUT_SELECT_PORTA   = "GENCLK",
			p_PLLOUT_SELECT_PORTB   = "GENCLK_HALF",
			i_PACKAGEPIN            = clk12,
			o_PLLOUTGLOBALA         = clk48,
			o_PLLOUTGLOBALB         = clk24,
			i_RESETB                = ~rst_btn,
			o_LOCK                  = pll_locked,
		)

		por_count = Signal(8)
		por_rst   = Signal()

		m.d.comb += por_rst.eq(~por_count[-1])
		m.d.por += por_count.eq(por_count + ~por_count[-1])

		platform.add_clock_constraint(clk48, 48e6)
		platform.add_clock_constraint(clk24, 24e6)

		m.d.comb += [
			ClockSignal("usb_48") .eq(clk48),
			ClockSignal("sync")   .eq(clk24),
			ClockSignal("por")    .eq(clk24),
			ResetSignal("por")    .eq(~pll_locked),
		]

		m.submodules += [
			ResetSynchronizer(por_rst, domain="usb_48"),
			ResetSynchronizer(por_rst, domain="sync"),
		]

			# Request pads with no buffers
		usb_pads = platform.request("usb", dir={'d_p':'-','d_n':'-','pullup':'-'})

		m.submodules.muacm_core = muacm = no2amaranth.NitroMuAcmBuffered(usb_pads, fifo_depth=256, product="bitsy")

		m.d.comb += [
			muacm.in_data.eq(muacm.out_data),
			muacm.in_last.eq(0),
			muacm.in_valid.eq(muacm.out_valid),
			muacm.out_ready.eq(muacm.in_ready),
			muacm.in_flush_time.eq(1),
			muacm.in_flush_now.eq(0),
		]

		reboot = Signal()
		m.d.sync += reboot.eq(reboot | muacm.bootloader_req)

		m.submodules.wb = Instance("SB_WARMBOOT",
			i_S1   = 0,
			i_S0   = 1,
			i_BOOT = reboot,
		)

		return m

if __name__ == "__main__":
	plat = ICEBreakerBitsyPlatform()
	plat.build(LoopbackTest(), do_program=True, program_opts={"run_vid": "1d50", "run_pid": "6159"}, nextpnr_opts="--seed 1")
