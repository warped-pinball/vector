'''  bit filter for score track on EM games

    uses viper - so isolated from ScoreTrack
'''


@micropython.viper
def _viper_process(buf: ptr32, ptr: int, idxmsk: int, s_state: int, s_mask: ptr32, r_mask: ptr32) -> int:
    """
    fast 32 bit wide digital stream filter.
    set min width acceptable samples for ->1 and ->0 in s_mask (set mask) and r_mask(reset mask)
    """
    score_hits :int = 0
    reset_hits :int = 0

    # Score detection: stages 1..5 (unrolled for speed)
    idx :int =ptr
    cumulative_high = buf[idx]
    # stage 1
    idx = (idx -1) & idxmsk
    cumulative_high &= buf[idx]
    score_hits |= cumulative_high & s_mask[1]

    # stage 2
    idx = (idx -1) & idxmsk
    cumulative_high &= buf[idx]
    score_hits |= cumulative_high & s_mask[2]

    # stage 3
    idx = (idx -1) & idxmsk
    cumulative_high &= buf[idx]
    score_hits |= cumulative_high & s_mask[3]

    # stage 4
    idx = (idx -1) & idxmsk
    cumulative_high &= buf[idx]
    score_hits |= cumulative_high & s_mask[4]

    # stage 5
    idx = (idx -1) & idxmsk
    cumulative_high &= buf[idx]
    score_hits |= cumulative_high & s_mask[5]

    # stage 6
    idx = (idx -1) & idxmsk
    cumulative_high &= buf[idx]
    score_hits |= cumulative_high & s_mask[6]

    # stage 7
    idx = (idx -1) & idxmsk
    cumulative_high &= buf[idx]
    score_hits |= cumulative_high & s_mask[7]

    # stage 8
    idx = (idx -1) & idxmsk
    cumulative_high &= buf[idx]
    score_hits |= cumulative_high & s_mask[8]

    # stage 9
    idx = (idx -1) & idxmsk
    cumulative_high &= buf[idx]
    score_hits |= cumulative_high & s_mask[9]

    # stage 10
    idx = (idx -1) & idxmsk
    cumulative_high &= buf[idx]
    score_hits |= cumulative_high & s_mask[10]

    # set score bits that were hit  (enough 1's in a row means the s_state bit will be set)
    s_state = s_state | score_hits

    # Reset detection: stages 1..14 (range(1,15))
    # falling low when inactive, this is when it will be counted    
    idx :int = ptr
    cumulative_low = (~buf[idx]) & 0xFFFF
  
    idx = (idx -1) & idxmsk
    cumulative_low &= (~buf[idx]) & 0xFFFF
    reset_hits |= cumulative_low & r_mask[1]

    idx = (idx -1) & idxmsk
    cumulative_low &= (~buf[idx]) & 0xFFFF
    reset_hits |= cumulative_low & r_mask[2]

    idx = (idx -1) & idxmsk
    cumulative_low &= (~buf[idx]) & 0xFFFF
    reset_hits |= cumulative_low & r_mask[3]

    idx = (idx -1) & idxmsk
    cumulative_low &= (~buf[idx]) & 0xFFFF
    reset_hits |= cumulative_low & r_mask[4]

    idx = (idx -1) & idxmsk
    cumulative_low &= (~buf[idx]) & 0xFFFF
    reset_hits |= cumulative_low & r_mask[5]

    idx = (idx -1) & idxmsk
    cumulative_low &= (~buf[idx]) & 0xFFFF
    reset_hits |= cumulative_low & r_mask[6]

    idx = (idx -1) & idxmsk
    cumulative_low &= (~buf[idx]) & 0xFFFF
    reset_hits |= cumulative_low & r_mask[7]

    idx = (idx -1) & idxmsk
    cumulative_low &= (~buf[idx]) & 0xFFFF
    reset_hits |= cumulative_low & r_mask[8]

    idx = (idx -1) & idxmsk
    cumulative_low &= (~buf[idx]) & 0xFFFF
    reset_hits |= cumulative_low & r_mask[9]

    idx = (idx -1) & idxmsk
    cumulative_low &= (~buf[idx]) & 0xFFFF
    reset_hits |= cumulative_low & r_mask[10]

    idx = (idx -1) & idxmsk
    cumulative_low &= (~buf[idx]) & 0xFFFF
    reset_hits |= cumulative_low & r_mask[11]

    idx = (idx -1) & idxmsk
    cumulative_low &= (~buf[idx]) & 0xFFFF
    reset_hits |= cumulative_low & r_mask[12]

    idx = (idx -1) & idxmsk
    cumulative_low &= (~buf[idx]) & 0xFFFF
    reset_hits |= cumulative_low & r_mask[13]

    idx = (idx -1) & idxmsk
    cumulative_low &= (~buf[idx]) & 0xFFFF
    reset_hits |= cumulative_low & r_mask[14]

    idx = (idx -1) & idxmsk
    cumulative_low &= (~buf[idx]) & 0xFFFF
    reset_hits |= cumulative_low & r_mask[15]

    # set reset hits into state
    s_state &= (~reset_hits)
    
    # pack results into single int  
    return s_state

