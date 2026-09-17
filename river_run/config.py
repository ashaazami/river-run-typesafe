"""Game constants. Distances are in pixels and times in frames (the game steps at a fixed 60 FPS)."""

WIDTH = 480
PLAY_HEIGHT = 560
HUD_HEIGHT = 80
HEIGHT = PLAY_HEIGHT + HUD_HEIGHT
FPS = 60

# Like the Atari original, the river is the same every game unless a different seed is given.
DEFAULT_SEED = 1982

# River layout. The river is built from horizontal slices grouped into sections;
# every section ends with a bridge, and destroying it moves the respawn point forward.
SLICE_H = 20
SECTION_SLICES = 72
SECTION_LEN = SLICE_H * SECTION_SLICES
BANK_MIN = 16
CHANNEL_LEFT = 184
CHANNEL_RIGHT = 296
START_SLICES = 8
FUNNEL_SLICES = 8
BRIDGE_CHANNEL_SLICES = 5
BRIDGE_SLICE = SECTION_SLICES - 3
BANK_SHIFT = 60
MIN_CHANNEL = 96
MIN_OVERLAP = 72
MIN_RUN, MAX_RUN = 4, 8

# Player
PLAYER_W = 24
PLAYER_H = 24
PLAYER_OFFSET = 60  # distance from the bottom of the play area
PLAYER_VX = 3.0
SPEED_SLOW, SPEED_NORMAL, SPEED_FAST = 1.0, 2.0, 4.0
SPEED_ACCEL = 0.08
START_LIVES = 3
EXTRA_LIFE_EVERY = 10_000
DEATH_FRAMES = 90

# Fuel
FUEL_MAX = 100.0
FUEL_DRAIN = 0.045
FUEL_REFILL = 0.7
LOW_FUEL = 40.0

# Missile
MISSILE_W = 3
MISSILE_H = 14
MISSILE_VY = 10.0

EXPLOSION_FRAMES = 30

SCORES = {"ship": 30, "helicopter": 60, "fuel": 80, "jet": 100, "bridge": 500}
SIZES = {
    "ship": (48, 16),
    "helicopter": (32, 18),
    "fuel": (26, 44),
    "jet": (34, 12),
    "bridge": (CHANNEL_RIGHT - CHANNEL_LEFT, 24),
}
