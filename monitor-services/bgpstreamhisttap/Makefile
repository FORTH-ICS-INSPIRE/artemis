CFLAGS := $(shell python3.7m-config --cflags)
LDFLAGS := $(shell python3.7m-config --ldflags)
FLAGS := -Os -shared -fPIC
CC := gcc
CPY := cython
PROJDIRS := core/
SRCFILES := $(shell find $(PROJDIRS) -maxdepth 2 -type f -name "*.py")
OBJFILES := $(patsubst %.py,%.so,$(SRCFILES))

all: $(OBJFILES)

%.c: %.py
	$(CPY) -3 --embed $< -o $@

%.so: %.c
	$(CC) $(FLAGS) $(CFLAGS) $(LDFLAGS) $< -o $@

clean:
	rm -rf $(CFILES) $(OBJFILES)
