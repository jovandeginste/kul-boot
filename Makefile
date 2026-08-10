# Python executable used to run the generator script.
PYTHON ?= python3
# Path to the flicker frame generator script.
SCRIPT ?= generate_tl_flicker.py
# Path to the Plymouth theme converter script.
PLYMOUTH_SCRIPT ?= generate_plymouth_theme.py
# Input base image used for all output frames.
BASE ?= kuleuven-punk.png
# Grayscale mask image marking TL tube pixels.
MASK ?= kuleuven-punk-tl.png
# Grayscale mask image marking neon border pixels.
NEON_MASK ?= kuleuven-punk-neon-border.png
# Grayscale/alpha mask image marking neon logo pixels.
LOGO_MASK ?= kuleuven-punk-neon-logo.png
# Directory where generated frame PNG files are written.
OUTPUT_DIR ?= frames
# Number of frames to generate.
COUNT ?= 500
# Number of worker processes used for frame rendering.
JOBS ?= $(shell nproc)
# Frames per second for GIF encoding.
FPS ?= 25
# Output GIF filename.
GIF ?= tl-flicker.gif
# Player command used for local animation preview.
PREVIEW_PLAYER ?= ffplay
# Output directory where Plymouth theme files are written.
PLYMOUTH_OUTPUT_DIR ?= plymouth-theme-kuleuven-punk
# Plymouth theme name used for .script and .plymouth files.
PLYMOUTH_THEME_NAME ?= kuleuven-punk
# Background color used by Plymouth theme (hex RGB).
PLYMOUTH_BACKGROUND ?= 0x000000
# Optional RNG seed for reproducible flicker patterns.
SEED ?= 1425
# Mask threshold (0-255) above which pixels are treated as TL tubes.
THRESHOLD ?= 16
# Probability that a tube changes brightness each frame.
CHANGE_PROBABILITY ?= 0.005
# Maximum consecutive flicker frames per tube (1-9).
MAX_FLICKER_FRAMES ?= 9
# Feather margin in pixels around tube edges for smoother fading.
FEATHER_MARGIN ?= 4
# Threshold (0-255) above which pixels are treated as neon border.
NEON_THRESHOLD ?= 0
# Alpha threshold (0-255) for neon mask transparency filtering.
NEON_ALPHA_THRESHOLD ?= 1
# Feather margin in pixels around neon mask edges for smoother pulse blend.
NEON_FEATHER_MARGIN ?= 6
# Pulse period in frames for the neon glow animation.
NEON_PERIOD ?= 150
# Minimum brightness scale for neon pulse.
NEON_MIN_SCALE ?= 0.60
# Maximum brightness scale for neon pulse.
NEON_MAX_SCALE ?= 1.1
# Threshold (0-255) above which pixels are treated as neon logo.
LOGO_THRESHOLD ?= 0
# Alpha threshold (0-255) for logo mask transparency filtering.
LOGO_ALPHA_THRESHOLD ?= 1
# Feather margin in pixels around logo mask edges for outward glow blend.
LOGO_FEATHER_MARGIN ?= 6
# Probability that a logo flicker burst starts on a frame.
LOGO_FLICKER_PROBABILITY ?= 0.005
# Minimum length of a logo flicker burst in frames.
LOGO_MIN_FLICKER_FRAMES ?= 5
# Maximum length of a logo flicker burst in frames.
LOGO_MAX_FLICKER_FRAMES ?= 30
# Probability of logo being ON during a flicker burst frame.
LOGO_FLICKER_ON_PROBABILITY ?= 0.25

# Adds --seed only when SEED is set.
SEED_ARG := $(if $(SEED),--seed $(SEED),)

.PHONY: generate gif preview preview-sequence plymouth-theme clean

generate:
	$(PYTHON) $(SCRIPT) \
		--base $(BASE) \
		--mask $(MASK) \
		--neon-mask $(NEON_MASK) \
		--logo-mask $(LOGO_MASK) \
		--output-dir $(OUTPUT_DIR) \
		--count $(COUNT) \
		--jobs $(JOBS) \
		--threshold $(THRESHOLD) \
		--change-probability $(CHANGE_PROBABILITY) \
		--max-flicker-frames $(MAX_FLICKER_FRAMES) \
		--feather-margin $(FEATHER_MARGIN) \
		--neon-threshold $(NEON_THRESHOLD) \
		--neon-alpha-threshold $(NEON_ALPHA_THRESHOLD) \
		--neon-feather-margin $(NEON_FEATHER_MARGIN) \
		--neon-period $(NEON_PERIOD) \
		--neon-min-scale $(NEON_MIN_SCALE) \
		--neon-max-scale $(NEON_MAX_SCALE) \
		--logo-threshold $(LOGO_THRESHOLD) \
		--logo-alpha-threshold $(LOGO_ALPHA_THRESHOLD) \
		--logo-feather-margin $(LOGO_FEATHER_MARGIN) \
		--logo-flicker-probability $(LOGO_FLICKER_PROBABILITY) \
		--logo-min-flicker-frames $(LOGO_MIN_FLICKER_FRAMES) \
		--logo-max-flicker-frames $(LOGO_MAX_FLICKER_FRAMES) \
		--logo-flicker-on-probability $(LOGO_FLICKER_ON_PROBABILITY) \
		$(SEED_ARG)

gif:
	ffmpeg -y -framerate $(FPS) -i $(OUTPUT_DIR)/frame_%04d.png -vf "split[s0][s1];[s0]palettegen=reserve_transparent=0[p];[s1][p]paletteuse" $(GIF)

preview: gif
	$(PREVIEW_PLAYER) -fs -autoexit -loglevel warning $(GIF)

preview-plymouth:
	(sleep 50 && sudo plymouth --quit) &
	sudo bash -c '\
		plymouthd; \
		plymouth --show-splash; \
		plymouth ask-for-password --prompt "LUKS passphrase (test): "; \
		'

plymouth-theme:
	$(PYTHON) $(PLYMOUTH_SCRIPT) \
		--frames-dir $(OUTPUT_DIR) \
		--output-dir $(PLYMOUTH_OUTPUT_DIR) \
		--theme-name $(PLYMOUTH_THEME_NAME) \
		--fps $(FPS) \
		--background $(PLYMOUTH_BACKGROUND)

clean:
	rm -rf $(OUTPUT_DIR) $(PLYMOUTH_OUTPUT_DIR) $(GIF) __pycache__
