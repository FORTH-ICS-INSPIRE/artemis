CFLAGS := $(shell python3m-config --cflags)
LDFLAGS := $(shell python3m-config --ldflags)
FLAGS := -Os -shared -fPIC
CC := gcc
CPY := cython
PROJDIRS := core/ core/utils
SRCFILES := $(shell find $(PROJDIRS) -maxdepth 1 -type f -name "*.py")
OBJFILES := $(patsubst %.py,%.so,$(SRCFILES))
PYTEST := $(shell command -v pytest 2> /dev/null)

all: $(OBJFILES)

%.c: %.py
	$(CPY) -3 --embed $< -o $@

%.so: %.c
	$(CC) $(FLAGS) $(CFLAGS) $(LDFLAGS) $< -o $@

test:
ifndef PYTEST
	$(error "pytest is not installed.. please run: pip install pytest")
endif
	PYTHONPATH=./core pytest

clean:
	rm -rf $(CFILES) $(OBJFILES)
