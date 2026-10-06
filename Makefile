SELF = toolchain/compiler/entry.tin toolchain/compiler/records.tin toolchain/compiler/util.tin toolchain/compiler/lex.tin toolchain/compiler/types.tin toolchain/compiler/secret.tin toolchain/compiler/parse.tin \
       toolchain/compiler/check.tin toolchain/compiler/lower.tin toolchain/compiler/generics.tin toolchain/compiler/region.tin toolchain/compiler/inline.tin toolchain/compiler/opt.tin toolchain/compiler/asm.tin toolchain/compiler/gen.tin toolchain/compiler/asm_x64.tin toolchain/compiler/gen_x64.tin \
       toolchain/compiler/memory_fast.tin toolchain/compiler/syscall_fast.tin toolchain/compiler/sha256.tin toolchain/compiler/aes_hw.tin toolchain/compiler/macho.tin toolchain/compiler/elf.tin toolchain/compiler/elf_x64.tin toolchain/compiler/caps.tin toolchain/compiler/main.tin \
       toolchain/compiler/host_$(HOST_OS).tin

.PHONY: all bootstrap seed test bench clean install dist linux-bootstrap linux-amd64-bootstrap linux-test

HOST_OS := $(shell uname -s | tr A-Z a-z)
HOST_ARCH := $(shell uname -m | sed 's/x86_64/amd64/; s/aarch64/arm64/')
# Where `make install` links tin: Homebrew's prefix on a Mac that has one, /usr/local elsewhere.
PREFIX ?= $(if $(and $(filter darwin,$(HOST_OS)),$(wildcard /opt/homebrew/bin)),/opt/homebrew,/usr/local)
SEED := toolchain/seed/tinc-$(HOST_OS)-$(shell uname -m | sed 's/x86_64/amd64/; s/aarch64/arm64/')
# Sources of a compiler for the other OS (cross builds).
SELF_LINUX_COMMON = $(filter-out toolchain/compiler/host_darwin.tin toolchain/compiler/host_linux.tin,$(SELF)) toolchain/compiler/host_linux.tin
SELF_LINUX = $(SELF_LINUX_COMMON)
SELF_LINUX_AMD64 = $(SELF_LINUX_COMMON)

all: bin/tinc

# Native release archive. Build on each supported host; releases.yml collects all three.
DIST_TARGET ?= $(HOST_OS)-$(shell uname -m | sed 's/x86_64/amd64/; s/aarch64/arm64/')
dist: bin/tinc
	python3 tools/dev/dist.py --target $(DIST_TARGET)

# The compiler, built by the checked-in seed compiler: no Go, no cc.
bin/tinc: $(SEED) $(SELF)
	@mkdir -p bin
	TIN_ROOT=$(CURDIR) $(SEED) -o $@ $(SELF)

# Rebuild tinc with itself twice; the two binaries must be byte-identical.
bootstrap: bin/tinc
	@mkdir -p bin/s2 bin/s3
	TIN_ROOT=$(CURDIR) bin/tinc -o bin/s2/tinc $(SELF)
	TIN_ROOT=$(CURDIR) bin/s2/tinc -o bin/s3/tinc $(SELF)
	cmp bin/s2/tinc bin/s3/tinc
	@echo "fixed point: tinc compiles itself to an identical binary"

# Refresh the seed after changing the compiler.
seed: bootstrap
	cp bin/s3/tinc $(SEED)

test: bin/tinc
	tools/dev/v2test.sh bin/tinc

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
	docker run --rm -e TIN_ROOT=/src -v $(CURDIR):/src -w /src $${TIN_LINUX_IMAGE:-tin-debian-arm64} sh -c '\
	  bin/linux/tinc -o /tmp/s2 $(SELF_LINUX) && /tmp/s2 -o /tmp/s3 $(SELF_LINUX) && cmp /tmp/s2 /tmp/s3 && \
	  cp /tmp/s3 toolchain/seed/tinc-linux-arm64 && echo "linux fixed point: tinc compiles itself to an identical binary"'

# The same for linux-amd64, run in an (emulated on arm64 hosts) amd64 container; refreshes
# toolchain/seed/tinc-linux-amd64.
bin/linux-amd64/tinc: bin/tinc $(SELF_LINUX_AMD64)
	@mkdir -p bin/linux-amd64
	bin/tinc -target linux-amd64 -o $@ $(SELF_LINUX_AMD64)

linux-amd64-bootstrap: bin/linux-amd64/tinc
	docker run --rm --platform linux/amd64 -e TIN_ROOT=/src -v $(CURDIR):/src -w /src $${TIN_LINUX_AMD64_IMAGE:-tin-debian-amd64} sh -c '\
	  bin/linux-amd64/tinc -o /tmp/s2 $(SELF_LINUX_AMD64) && /tmp/s2 -o /tmp/s3 $(SELF_LINUX_AMD64) && cmp /tmp/s2 /tmp/s3 && \
	  cp /tmp/s3 toolchain/seed/tinc-linux-amd64 && echo "linux-amd64 fixed point: tinc compiles itself to an identical binary"'

linux-test: bin/tinc
	tools/dev/linuxtest.sh bin/tinc

clean:
	rm -rf bin

# make print-SELF prints the compiler's source list (for scripts).
print-%:
	@echo $($*)
