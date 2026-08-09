# PAM-4 SiGe HBT driver — flow entry points.
# All Python runs through the uv-managed env (see pyproject.toml / uv.lock).
#
#   make sync       install/update the Python environment
#   make verify     schematic verification benches (results/*.yaml)
#   make eye        PAM-4 eye simulation (results/pam4_eye*.{yaml,png})
#   make signoff    layout DRC + LVS on all three DUTs
#   make notebooks  execute all three notebooks (.py -> .ipynb via jupytext)
#   make all        verify + eye + signoff + notebooks

# Machine-specific tool locations live in an untracked local.mk
# (PDK_ROOT, and optionally KPEX / KPEX_KLAYOUT_EXE) — see README
# "EDA tool setup". Nothing personal belongs in this Makefile.
-include local.mk

PDK      ?= ihp-sg13g2
PDK_ROOT ?= $(error PDK_ROOT is not set — export it or put it in local.mk, \
see README "EDA tool setup")
ENV       = PDK_ROOT=$(PDK_ROOT) PDK=$(PDK) \
            $(if $(KPEX),KPEX=$(KPEX)) \
            $(if $(KPEX_KLAYOUT_EXE),KPEX_KLAYOUT_EXE=$(KPEX_KLAYOUT_EXE))
RUN       = $(ENV) uv run

# notebook 02's optimizer budget (trials through gen_layout -> DRC/LVS ->
# kpex -> ngspice); the committed result used the default of 8.
NB_BUDGET ?= 8

.PHONY: all sync verify eye signoff notebooks nb01 nb02 nb03 clean

all: verify eye signoff notebooks

sync:
	uv sync

verify:
	cd testbenches && $(RUN) python run_verify.py all

eye:
	cd testbenches && $(RUN) python run_eye.py

signoff:
	cd layout && $(RUN) python signoff.py

notebooks: nb01 nb02 nb03

nb01:
	cd notebooks && $(RUN) jupytext --to notebook --execute 01_schematic_sizing.py

nb02:
	cd notebooks && $(ENV) NB_BUDGET=$(NB_BUDGET) uv run jupytext --to notebook --execute 02_layout_in_the_loop.py

nb03:
	cd notebooks && $(RUN) jupytext --to notebook --execute 03_signoff.py

clean:
	rm -rf notebooks/nb_opt notebooks/*.ipynb layout/out/signoff
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
