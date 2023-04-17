

SELF=$(lastword $(MAKEFILE_LIST))
ROOT_DIR=$(abspath $(dir $(SELF))/..)
SKIP_DEPS=

outdir:=/var/tmp/copr-tmp-outdir
spec:=extras/python-sambacc.spec

.PHONY: srpm
srpm: sys_deps
	mkdir -p $(outdir)
	git fetch --tags
	SAMBACC_SRPM_ONLY=yes \
		SAMBACC_BUILD_DIR=$(ROOT_DIR) \
		SAMBACC_DIST_PREFIX=$(outdir)/.dist \
		SAMBACC_DISTNAME=copr \
		SAMBACC_BUILD_TASKS="task_py_build task_rpm_build" \
		 ./tests/container/build.sh
	cp $(outdir)/.dist/copr/SRPMS/*.rpm  $(outdir)


.PHONY: sys_deps
sys_deps:
ifeq ($(SKIP_DEPS),yes)
	@echo "Skipping sys deps"
else
	dnf install -y python3-pip git
endif
