# SPDX-License-Identifier: MIT
#SYZKALLER_BIN := ${GOPATH}/src/github.com/google/syzkaller/bin/
#PROG2C := ${SYZKALLER_BIN}/syz-prog2c

SYZKALLER_BIN := "../build/gopath/src/github.com/google/syzkaller/bin/"
PROG2C := ${SYZKALLER_BIN}/syz-prog2c

CFLAGS := -O2 -static

CORPUS := unpacked
BUILD := build

SRCS := $(wildcard $(CORPUS)/*.prog)
OBJS := $(SRCS:$(CORPUS)/%.prog=$(BUILD)/%.elf)

all: $(OBJS)

.SILENT:
$(BUILD)/%.elf: $(CORPUS)/%.prog
	-$(PROG2C) -prog $< -repeat=1 | $(CC) $(CFLAGS) -x c -o $@ -

#$(BUILD)/%.c: $(CORPUS)/%.prog
#	-$(PROG2C) -prog $< -repeat=1 > $@
#
#$(BUILD)/%.elf: $(BUILD)/%.c
#	-$(CC) $(CFLAGS) -o $@ $^


#.PRECIOUS: $(BUILD)/%.c

clean:

