# BitStreamFilter32: 32-bit, 16-deep zero-run filter with per-stage masks.
'''
this "filter" is setup to be super fast with full 32 parallel bit streams

after init setup the number of samples required for a score increment
and also the number of idle samples to reset for the next score (hold off)
'''

class BitStreamFilter32:
    MASK32 = 0xFFFFFFFF
    DEPTH  = 16
    IDXMSK = 0x0F  # pointer wrap around - 16 samples

    def __init__(self):
        """
        score_mask: list/tuple len=16 of 32-bit masks; bits set = channels to watch at that stage.
        reset_mask: list/tuple len=16 of 32-bit masks; bits set = channels to reset at that stage.
        Defaults to all zeros
        """
        iv = 0xFFFFFFFF
        self.buf = [iv] * self.DEPTH
        self.ptr = 1              # "last written" index
      
        self.score_mask = [0] * self.DEPTH
        self.reset_mask = [0] * self.DEPTH

        self.scoreState = 0xFFFFFFFF

    def set_stage_score_mask(self, channel, stage):
        """send the channel (bit number) and stage - or number of identical bits (0!) for a score to be registered"""
        #should be called for every active channel on intializaiton
        mask = 1 << channel
        for i in range(self.DEPTH):        
            self.score_mask[i] &= ~mask
        # Set the bit only in the specified stage
        self.score_mask[stage] |= mask

    def set_stage_reset_mask(self, channel, stage):
        """send the channel (bit number) and stage or number of samples (1!) for the state to be switched back to scoreable """
        mask = 1 << channel
        for i in range(self.DEPTH):
            self.reset_mask[i] &= ~mask
        self.reset_mask[stage] |= mask
  
    def process(self, new_word):
        """
        Ingest a new 32-bit sample and run the inverted-AND pipeline.
        Returns:
            score_hits: 32-bit mask OR of all stage score hits (fast check)
        """
        # Advance circular pointer, store sample
        self.ptr = (self.ptr + 1) & self.IDXMSK
        self.buf[self.ptr] = new_word

        score_hits = 0
        cumulative_low = ~self.buf[self.ptr] & self.MASK32

        # Precompute masks for speed
        scoreState = self.scoreState
        score_mask = self.score_mask

        # Score detection loop (depth reduced to 6 for speed, can be tuned)
        for i in range(1, 6):
            idx = (self.ptr - i) & self.IDXMSK
            cumulative_low &= ~self.buf[idx] & self.MASK32
            score_hits |= cumulative_low & scoreState & score_mask[i]

        return score_hits






# ------------------------ Example usage ------------------------
if __name__ == "__main__":
    f = BitStreamFilter32()

    f.set_stage_score_mask( 0, 1)
    f.set_stage_score_mask( 1, 1)
    f.set_stage_score_mask( 2, 1)
    f.set_stage_score_mask( 3, 1)

    f.set_stage_reset_mask( 0, 2)
    f.set_stage_reset_mask( 1, 7)
    f.set_stage_reset_mask( 2, 2)
    f.set_stage_reset_mask( 3, 2)

    # Feed some samples
    samples = [
        0xFFFFFFFF,  # lower 16 are zeros
        0xFFFFFFFE,
        0xFFFFFFFE,  # after 3 samples, stage 2 should hit for lower 16 bits
        0xFFFFFFFE,
        0xFFFFFFFE,
        0xFFFFFFFD,
        0xFFFFFFFD,
        0xFFFFFFFD,
        0xFFFFFFFF,
        0xFFFFFFFF,
        0xFFFFFFFF,
        0xFFFFFFFF,
        0xFFFFFFFD,  
        0xFFFFFFFD,  
        0xFFFFFFFF  

    ]

    for s in samples:
        any_hits = f.process(s)
        if any_hits:
            # Replace with your "score action" handling
            print("HIT any=", hex(any_hits))
