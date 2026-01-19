from uctypes import BF_LEN, BF_POS, BFUINT32, UINT32, struct

# fmt: off
DMA_BASE = 0x50000000
DMA_CHAN_WIDTH = 0x40
DMA_CHAN_COUNT = 12

DMA_CTRL_TRIG_FIELDS = {
    "AHB_ERROR":   31 << BF_POS | 1 << BF_LEN | BFUINT32,
    "READ_ERROR":  30 << BF_POS | 1 << BF_LEN | BFUINT32,
    "WRITE_ERROR": 29 << BF_POS | 1 << BF_LEN | BFUINT32,
    "BUSY":        26 << BF_POS | 1 << BF_LEN | BFUINT32,
    "SNIFF_EN":    25 << BF_POS | 1 << BF_LEN | BFUINT32,
    "BSWAP":       24 << BF_POS | 1 << BF_LEN | BFUINT32,
    "IRQ_QUIET":   23 << BF_POS | 1 << BF_LEN | BFUINT32,
    "TREQ_SEL":    17 << BF_POS | 6 << BF_LEN | BFUINT32,
    "CHAIN_TO":    13 << BF_POS | 4 << BF_LEN | BFUINT32,
    "RING_SEL":    12 << BF_POS | 1 << BF_LEN | BFUINT32,
    "RING_SIZE":    8 << BF_POS | 4 << BF_LEN | BFUINT32,
    "INCR_WRITE_REV":7 << BF_POS | 1 << BF_LEN | BFUINT32,
    "INCR_WRITE":    6 << BF_POS | 1 << BF_LEN | BFUINT32,
    "INCR_READ_REV": 5 << BF_POS | 1 << BF_LEN | BFUINT32,
    "INCR_READ":     4 << BF_POS | 1 << BF_LEN | BFUINT32,
    "DATA_SIZE":     2 << BF_POS | 2 << BF_LEN | BFUINT32,
    "HIGH_PRIORITY": 1 << BF_POS | 1 << BF_LEN | BFUINT32,
    "EN":            0 << BF_POS | 1 << BF_LEN | BFUINT32
}

DMA_CHAN_REGS = {
    "READ_ADDR_REG":         0x00 | UINT32,
    "WRITE_ADDR_REG":        0x04 | UINT32,
    "TRANS_COUNT_REG":       0x08 | UINT32,
    "TRANS_COUNT_REG_TRIG":  0x1C | UINT32,            # will trigger!
    "CTRL_REG_TRIG":         0x0c | UINT32,            # will trigger!
    "CTRL_REG":          (0x10, DMA_CTRL_TRIG_FIELDS)  # 0x0C would cause trigger also. move to 0x10 to prebvent trigger at setup
}

DMA_REGS = {
    "INTR":               0x400 | UINT32,
    "INTE0":              0x404 | UINT32,
    "INTF0":              0x408 | UINT32,
    "INTS0":              0x40c | UINT32,
    "INTE1":              0x414 | UINT32,
    "INTF1":              0x418 | UINT32,
    "INTS1":              0x41c | UINT32,
    "TIMER0":             0x420 | UINT32,
    "TIMER1":             0x424 | UINT32,
    "TIMER2":             0x428 | UINT32,
    "TIMER3":             0x42c | UINT32,
    "MULTI_CHAN_TRIGGER": 0x430 | UINT32,
    "SNIFF_CTRL":         0x434 | UINT32,
    "SNIFF_DATA":         0x438 | UINT32,
    "FIFO_LEVELS":        0x440 | UINT32,
    "CHAN_ABORT":         0x444 | UINT32,
    "N_CHANNELS":         0x448 | UINT32,
    "CH0_DBG_CTDREQ":     0x800 | UINT32,
    "CH0_DBG_TCR":        0x804 | UINT32,
    "CH1_DBG_TCR":        0x844 | UINT32
}

# fmt: on
DREQ_PIO0_TX0, DREQ_PIO0_TX1, DREQ_PIO0_TX2, DREQ_PIO0_TX3 = 0, 1, 2, 3
DREQ_PIO0_RX0, DREQ_PIO0_RX1, DREQ_PIO0_RX2, DREQ_PIO0_RX3 = 4, 5, 6, 7

DREQ_PIO1_TX0, DREQ_PIO1_TX1, DREQ_PIO1_TX2, DREQ_PIO1_TX3 = 8, 9, 10, 11
DREQ_PIO1_RX0, DREQ_PIO1_RX1, DREQ_PIO1_RX2, DREQ_PIO1_RX3 = 12, 13, 14, 15


DMA_CHANS = [struct(DMA_BASE + n * DMA_CHAN_WIDTH, DMA_CHAN_REGS) for n in range(0, DMA_CHAN_COUNT)]
DMA_DEVICE = struct(DMA_BASE, DMA_REGS)
