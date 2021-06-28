Nitro cores nMigen wrappers
===========================

This repository contains wrappers to allow to use some of the Nitro FPGA cores
in a nMigen environment.


Wrapped Cores
-------------

### `no2muacm`: USB CDC ACM core

This core is wrapped in 3 possible variants `no2nmigen.NitroMuAcmSync`,
`no2nmigen.NitroMuAcmAsync` and `no2nmigen.NitroMuAcmBuffered`.

Theses 3 variants expose the same kind of data interface, derived from
AXI-Stream. Refer to the python docstring for the details. The `Sync` variant
is meant to run entirely in one clock domain and it must be 48 MHz. The `Async`
variant uses a `usb_48` clock domain for the USB part but all user interfacing
is done in the `sync` domain and this can be anything. The `Buffered` variant
can use either clocking strategy (depending on `sync` parameter) but it adds
some FIFO to increase efficiency.

The `usb` resource given as the pads param must define the pads for `d_p`,
`d_n` and `pullup`.

Clocking wise, the core works at any `sync` frequency for its interface to
the SoC but needs a `usb_48` `ClockDomain` to be defined and running at
48 MHz for the USB SIE part.

The core also offers a `bootloader_req` that generates a pulse if the
hosts requests a reboot to bootloader using a `DFU_DETACH` request. This
should be tied to whatever logic you have to reboot your FPGA to its
bootloader (assuming there is one).

The common options available for the cores are :

 * `vid` / `pid`: Sets customs USB PID/VID for the core.

 * `vendor` / `product` / `serial`: Sets the corresponding string descriptors
   (length limited to 16).

 * `no_dfu_rt`: Disables the DFU runtime function of the core.


Limitations
-----------

Some of the cores have limited FPGA architecture supports and will only work
on some FPGA target. If you need support for another, adaptation is often not
too complex (mostly IO buffers / BRAM primitives), you can open an issue
on the appropriate core tracker.


License
-------

See LICENSE.md for the licenses of the various components in this repository
