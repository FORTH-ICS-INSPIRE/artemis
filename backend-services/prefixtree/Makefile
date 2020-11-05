PYTHONVERSION := $(shell python -c "import sys;t='{v[0]}.{v[1]}'.format(v=list(sys.version_info[:2]));sys.stdout.write(t)")
CFLAGS := $(shell python$(PYTHONVERSION)m-config --cflags)
LDFLAGS := $(shell python$(PYTHONVERSION)m-config --ldflags)
FLAGS := -Os -shared -fPIC
CC := gcc
CPY := cython
PROJDIRS := core/
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
