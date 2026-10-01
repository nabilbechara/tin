SELF = lib/std.tin selfhost/util.tin selfhost/lex.tin selfhost/types.tin selfhost/parse.tin \
       selfhost/check.tin selfhost/lower.tin selfhost/generics.tin selfhost/region.tin selfhost/inline.tin selfhost/opt.tin selfhost/asm.tin selfhost/gen.tin selfhost/asm_x64.tin selfhost/gen_x64.tin \
       selfhost/sha256.tin selfhost/macho.tin selfhost/elf.tin selfhost/elf_x64.tin selfhost/main.tin \
       selfhost/host_$(HOST_OS).tin

.PHONY: all bootstrap seed test bench clean install linux-bootstrap linux-test

HOST_OS := $(shell uname -s | tr A-Z a-z)
# Where `make install` links tin: Homebrew's prefix on a Mac that has one, /usr/local elsewhere.
PREFIX ?= $(if $(and $(filter darwin,$(HOST_OS)),$(wildcard /opt/homebrew/bin)),/opt/homebrew,/usr/local)
SEED := seed/tinc-$(HOST_OS)-$(shell uname -m | sed 's/x86_64/amd64/; s/aarch64/arm64/')
# Sources of a compiler for the other OS (cross builds).
SELF_LINUX = $(filter-out selfhost/host_darwin.tin selfhost/host_linux.tin,$(SELF)) selfhost/host_linux.tin

all: bin/tinc

# The compiler, built by the checked-in seed compiler: no Go, no cc.
bin/tinc: $(SEED) $(SELF)
	@mkdir -p bin
	$(SEED) -o $@ $(SELF)

# Rebuild tinc with itself twice; the two binaries must be byte-identical.
bootstrap: bin/tinc
	@mkdir -p bin/s2 bin/s3
	bin/tinc -o bin/s2/tinc $(SELF)
	bin/s2/tinc -o bin/s3/tinc $(SELF)
	cmp bin/s2/tinc bin/s3/tinc
	@echo "fixed point: tinc compiles itself to an identical binary"

# Refresh the seed after changing the compiler.
seed: bootstrap
	cp bin/s3/tinc $(SEED)

# Stage 0, the original Go compiler: kept for history and the test harness.
bin/tinc0: $(wildcard bootstrap/*.go)
	go build -o $@ ./bootstrap

test: bin/tinc0 bin/tinc
	tools/v2test.sh bin/tinc
	go test -count=1 ./bootstrap
	TINC=$(CURDIR)/bin/tinc go test -count=1 ./bootstrap
	TINC=$(CURDIR)/bin/tinc TINC_ASM=1 go test -count=1 ./bootstrap

bench: bin/tinc
	bench/run.py

# Put `tin` on the PATH (a symlink: the tree stays where it is); a leading ~/ in PREFIX means $HOME.
INSTALL_BIN = $(patsubst ~/%,$(HOME)/%,$(PREFIX))/bin
install: bin/tinc
	mkdir -p "$(INSTALL_BIN)"
	ln -sf "$(CURDIR)/tin" "$(INSTALL_BIN)/tin"

# A Linux arm64 compiler, cross-compiled from any host; check it in the container with
# `make linux-bootstrap` (it must rebuild itself to an identical binary there).
bin/linux/tinc: bin/tinc $(SELF_LINUX)
	@mkdir -p bin/linux
	bin/tinc -target linux-arm64 -o $@ $(SELF_LINUX)

linux-bootstrap: bin/linux/tinc
	docker run --rm -v $(CURDIR):/src -w /src $${TIN_LINUX_IMAGE:-tin-debian-arm64} sh -c '\
	  bin/linux/tinc -o /tmp/s2 $(SELF_LINUX) && /tmp/s2 -o /tmp/s3 $(SELF_LINUX) && cmp /tmp/s2 /tmp/s3 && \
	  cp /tmp/s3 seed/tinc-linux-arm64 && echo "linux fixed point: tinc compiles itself to an identical binary"'

linux-test: bin/tinc
	tools/linuxtest.sh bin/tinc

clean:
	rm -rf bin

# make print-SELF prints the compiler's source list (for scripts).
print-%:
	@echo $($*)
